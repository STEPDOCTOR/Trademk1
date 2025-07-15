"""Tests for market data ingestion."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ingestor.binance_client import BinanceWebSocketClient
from app.services.ingestor.ingest_worker import IngestWorker
from app.services.ingestor.models import Exchange, Tick, TickType


@pytest.fixture
def mock_queue():
    """Create a mock queue for testing."""
    return asyncio.Queue()


@pytest.fixture
def binance_client(mock_queue):
    """Create a Binance client instance."""
    return BinanceWebSocketClient(mock_queue)


@pytest.fixture
def ingest_worker(mock_queue):
    """Create an ingest worker instance."""
    return IngestWorker(mock_queue, batch_size=2, batch_timeout=0.1)


@pytest.mark.asyncio
async def test_binance_parse_trade_message(binance_client):
    """Test parsing Binance trade message."""
    message = {
        "stream": "btcusdt@trade",
        "data": {
            "s": "BTCUSDT",
            "p": "50000.00",
            "q": "0.1",
            "T": 1234567890123
        }
    }
    
    tick = await binance_client.parse_message(message)
    
    assert tick is not None
    assert tick.symbol == "BTCUSDT"
    assert tick.exchange == Exchange.BINANCE
    assert tick.tick_type == TickType.TRADE
    assert tick.price == 50000.0
    assert tick.volume == 0.1
    assert tick.timestamp == datetime.fromtimestamp(1234567890.123)


@pytest.mark.asyncio
async def test_binance_parse_quote_message(binance_client):
    """Test parsing Binance quote message."""
    message = {
        "stream": "btcusdt@bookTicker",
        "data": {
            "s": "BTCUSDT",
            "b": "49900.00",
            "B": "1.5",
            "a": "50100.00",
            "A": "2.0",
            "E": 1234567890123
        }
    }
    
    tick = await binance_client.parse_message(message)
    
    assert tick is not None
    assert tick.symbol == "BTCUSDT"
    assert tick.exchange == Exchange.BINANCE
    assert tick.tick_type == TickType.QUOTE
    assert tick.price == 50000.0  # Mid price
    assert tick.bid_price == 49900.0
    assert tick.ask_price == 50100.0
    assert tick.bid_size == 1.5
    assert tick.ask_size == 2.0


@pytest.mark.asyncio
async def test_ingest_worker_batch_processing(ingest_worker):
    """Test ingest worker batch processing."""
    # Create mock ticks
    ticks = [
        Tick(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            tick_type=TickType.TRADE,
            timestamp=datetime.utcnow(),
            price=50000.0,
            volume=0.1
        ),
        Tick(
            symbol="ETHUSDT",
            exchange=Exchange.BINANCE,
            tick_type=TickType.TRADE,
            timestamp=datetime.utcnow(),
            price=3000.0,
            volume=1.0
        )
    ]
    
    # Mock execute_batch
    with patch("app.services.ingestor.ingest_worker.execute_batch") as mock_execute:
        mock_execute.return_value = None
        
        # Add ticks to queue
        for tick in ticks:
            await ingest_worker.queue.put(tick)
        
        # Run worker for a short time
        worker_task = asyncio.create_task(ingest_worker.run())
        await asyncio.sleep(0.2)
        await ingest_worker.stop()
        worker_task.cancel()
        
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        
        # Verify batch was executed
        mock_execute.assert_called()
        
        # Check stats
        stats = ingest_worker.get_stats()
        assert stats["total_ticks"] == 2
        assert stats["total_batches"] == 1


@pytest.mark.asyncio
async def test_binance_websocket_reconnection():
    """Test Binance WebSocket reconnection logic."""
    queue = asyncio.Queue()
    client = BinanceWebSocketClient(queue)
    
    # Mock websocket that fails on first connect
    connect_count = 0
    
    async def mock_connect(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            raise ConnectionError("Connection failed")
        
        # Return mock websocket
        mock_ws = AsyncMock()
        mock_ws.__aiter__.return_value = []
        return mock_ws
    
    with patch("websockets.connect", side_effect=mock_connect):
        # Run client for a short time
        client_task = asyncio.create_task(client.run())
        await asyncio.sleep(2.5)  # Allow time for reconnection
        await client.stop()
        client_task.cancel()
        
        try:
            await client_task
        except asyncio.CancelledError:
            pass
        
        # Verify reconnection happened
        assert connect_count >= 2
        assert client.reconnect_delay > 1.0  # Exponential backoff


@pytest.mark.asyncio
async def test_tick_to_dict():
    """Test Tick.to_dict() method."""
    timestamp = datetime.utcnow()
    tick = Tick(
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        tick_type=TickType.QUOTE,
        timestamp=timestamp,
        price=50000.0,
        bid_price=49900.0,
        ask_price=50100.0,
        bid_size=1.5,
        ask_size=2.0,
        volume=None
    )
    
    tick_dict = tick.to_dict()
    
    assert tick_dict["symbol"] == "BTCUSDT"
    assert tick_dict["exchange"] == "BINANCE"
    assert tick_dict["price"] == 50000.0
    assert tick_dict["bid_price"] == 49900.0
    assert tick_dict["ask_price"] == 50100.0
    assert tick_dict["bid_size"] == 1.5
    assert tick_dict["ask_size"] == 2.0
    assert tick_dict["volume"] is None
    assert tick_dict["timestamp"] == timestamp