"""Tests for Order Management System."""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import redis.asyncio as redis
from sqlalchemy import select

from app.models.order import Order, OrderSide, OrderType, OrderStatus
from app.models.position import Position
from app.models.config import Config
from app.services.trading.execution_engine import ExecutionEngine
from app.services.trading.position_manager import PositionManager


@pytest.mark.asyncio
async def test_trade_signal_api(async_client):
    """Test submitting a trade signal via API."""
    signal = {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 10,
        "reason": "Test signal"
    }
    
    with patch("redis.asyncio.from_url") as mock_redis:
        mock_redis_client = AsyncMock()
        mock_redis.return_value = mock_redis_client
        
        response = await async_client.post("/api/v1/trading/signal", json=signal)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["signal"]["symbol"] == "AAPL"
        
        # Verify Redis publish was called
        mock_redis_client.publish.assert_called_once()
        call_args = mock_redis_client.publish.call_args
        assert call_args[0][0] == "trade_signals"
        
        published_data = json.loads(call_args[0][1])
        assert published_data["symbol"] == "AAPL"
        assert published_data["side"] == "buy"
        assert published_data["qty"] == 10


@pytest.mark.asyncio
async def test_execution_engine_process_signal(test_db):
    """Test execution engine processing a trade signal."""
    # Add risk config
    config = Config(
        id=uuid4(),
        key="max_order_qty_stock",
        value="100",
        scope="risk",
        description="Max stock order qty"
    )
    test_db.add(config)
    await test_db.commit()
    
    engine = ExecutionEngine()
    
    # Mock Alpaca client
    with patch.object(engine, "alpaca_client") as mock_alpaca:
        mock_alpaca.submit_order = AsyncMock(return_value={
            "alpaca_id": "test-alpaca-123",
            "status": "submitted",
            "submitted_at": datetime.utcnow().isoformat(),
            "filled_qty": 0,
            "filled_price": None
        })
        
        # Mock market hours check
        with patch.object(engine, "_is_market_open", return_value=True):
            # Process signal
            signal = {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 10,
                "reason": "Test trade"
            }
            
            await engine._process_signal(signal)
            
            # Verify order was created
            result = await test_db.execute(
                select(Order).where(Order.symbol == "AAPL")
            )
            order = result.scalar_one()
            
            assert order.side == OrderSide.BUY
            assert order.qty == 10
            assert order.status == OrderStatus.SUBMITTED
            assert order.alpaca_id == "test-alpaca-123"
            assert order.reason == "Test trade"


@pytest.mark.asyncio
async def test_risk_check_quantity_limit(test_db):
    """Test risk check for quantity limits."""
    # Add risk configs
    configs = [
        Config(
            id=uuid4(),
            key="max_order_qty_crypto",
            value="1.0",
            scope="risk",
            description="Max crypto order qty"
        ),
        Config(
            id=uuid4(),
            key="max_order_qty_stock",
            value="100",
            scope="risk",
            description="Max stock order qty"
        )
    ]
    for config in configs:
        test_db.add(config)
    await test_db.commit()
    
    engine = ExecutionEngine()
    
    # Test crypto limit
    result = await engine._check_risk_limits(test_db, "BTCUSDT", "buy", 2.0)
    assert not result["allowed"]
    assert "exceeds crypto limit" in result["reason"]
    
    # Test stock limit
    result = await engine._check_risk_limits(test_db, "AAPL", "buy", 200)
    assert not result["allowed"]
    assert "exceeds stock limit" in result["reason"]
    
    # Test within limits
    result = await engine._check_risk_limits(test_db, "AAPL", "buy", 50)
    assert result["allowed"]


@pytest.mark.asyncio
async def test_position_update_on_fill(test_db):
    """Test position update when order is filled."""
    manager = PositionManager()
    
    # Test new position
    await manager.update_position_on_fill(
        test_db,
        symbol="AAPL",
        side="buy",
        qty=10,
        price=150.0
    )
    
    result = await test_db.execute(
        select(Position).where(Position.symbol == "AAPL")
    )
    position = result.scalar_one()
    
    assert position.qty == 10
    assert position.avg_price == 150.0
    assert position.cost_basis == 1500.0
    assert position.market_value == 1500.0
    
    # Test adding to position
    await manager.update_position_on_fill(
        test_db,
        symbol="AAPL",
        side="buy",
        qty=5,
        price=160.0
    )
    
    await test_db.refresh(position)
    assert position.qty == 15
    assert position.avg_price == 153.33  # (10*150 + 5*160) / 15
    assert position.cost_basis == 2300.0
    
    # Test partial sell
    await manager.update_position_on_fill(
        test_db,
        symbol="AAPL",
        side="sell",
        qty=5,
        price=170.0
    )
    
    await test_db.refresh(position)
    assert position.qty == 10
    assert position.realized_pnl == 83.35  # 5 * (170 - 153.33)


@pytest.mark.asyncio
async def test_order_update_from_alpaca(test_db):
    """Test handling order updates from Alpaca WebSocket."""
    # Create order
    order = Order(
        id=uuid4(),
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=10,
        type=OrderType.MARKET,
        status=OrderStatus.SUBMITTED,
        alpaca_id="test-alpaca-456"
    )
    test_db.add(order)
    await test_db.commit()
    
    engine = ExecutionEngine()
    
    # Mock position manager
    with patch.object(engine, "position_manager") as mock_pm:
        mock_pm.update_position_on_fill = AsyncMock()
        
        # Simulate fill update
        update = {
            "event": "fill",
            "order": {
                "id": "test-alpaca-456",
                "filled_avg_price": "155.50"
            }
        }
        
        await engine._handle_order_update(update)
        
        # Verify order was updated
        await test_db.refresh(order)
        assert order.status == OrderStatus.FILLED
        assert order.filled_price == 155.50
        assert order.filled_at is not None
        
        # Verify position update was called
        mock_pm.update_position_on_fill.assert_called_once()


@pytest.mark.asyncio
async def test_get_orders_api(async_client, test_db):
    """Test getting orders via API."""
    # Create test orders
    orders = [
        Order(
            id=uuid4(),
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=10,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            filled_price=150.0,
            reason="Test order 1"
        ),
        Order(
            id=uuid4(),
            symbol="GOOGL",
            side=OrderSide.SELL,
            qty=5,
            type=OrderType.LIMIT,
            status=OrderStatus.PENDING,
            price=2500.0,
            reason="Test order 2"
        )
    ]
    for order in orders:
        test_db.add(order)
    await test_db.commit()
    
    # Test get all orders
    response = await async_client.get("/api/v1/trading/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Test filter by symbol
    response = await async_client.get("/api/v1/trading/orders?symbol=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    
    # Test filter by status
    response = await async_client.get("/api/v1/trading/orders?status=filled")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_get_positions_api(async_client, test_db):
    """Test getting positions via API."""
    # Create test positions
    positions = [
        Position(
            id=uuid4(),
            symbol="AAPL",
            qty=10,
            avg_price=150.0,
            market_value=1600.0,
            cost_basis=1500.0,
            unrealized_pnl=100.0,
            realized_pnl=50.0,
            last_price=160.0
        ),
        Position(
            id=uuid4(),
            symbol="GOOGL",
            qty=0,  # Closed position
            avg_price=0,
            market_value=0,
            cost_basis=0,
            unrealized_pnl=0,
            realized_pnl=200.0
        )
    ]
    for pos in positions:
        test_db.add(pos)
    await test_db.commit()
    
    # Test get open positions only
    response = await async_client.get("/api/v1/trading/positions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    
    # Test include closed positions
    response = await async_client.get("/api/v1/trading/positions?include_closed=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_portfolio_snapshot(async_client, test_db):
    """Test getting portfolio snapshot."""
    # Create test positions
    positions = [
        Position(
            id=uuid4(),
            symbol="AAPL",
            qty=10,
            avg_price=150.0,
            market_value=1600.0,
            cost_basis=1500.0,
            unrealized_pnl=100.0,
            realized_pnl=50.0,
            last_price=160.0,
            last_price_updated=datetime.utcnow()
        ),
        Position(
            id=uuid4(),
            symbol="BTCUSDT",
            qty=0.5,
            avg_price=40000.0,
            market_value=21000.0,
            cost_basis=20000.0,
            unrealized_pnl=1000.0,
            realized_pnl=500.0,
            last_price=42000.0,
            last_price_updated=datetime.utcnow()
        )
    ]
    for pos in positions:
        test_db.add(pos)
    await test_db.commit()
    
    response = await async_client.get("/api/v1/trading/portfolio")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_value"] == 22600.0  # 1600 + 21000
    assert data["total_unrealized_pnl"] == 1100.0  # 100 + 1000
    assert data["total_realized_pnl"] == 550.0  # 50 + 500
    assert data["total_pnl"] == 1650.0  # 1100 + 550
    assert len(data["positions"]) == 2


@pytest.mark.asyncio
async def test_market_hours_check():
    """Test market hours validation."""
    engine = ExecutionEngine()
    
    # Mock datetime for testing
    with patch("app.services.trading.execution_engine.datetime") as mock_dt:
        # Test weekend (Saturday)
        mock_dt.utcnow.return_value.weekday.return_value = 5
        assert not engine._is_market_open()
        
        # Test weekday during market hours (2 PM UTC = 9 AM EST)
        mock_dt.utcnow.return_value.weekday.return_value = 1  # Tuesday
        mock_dt.utcnow.return_value.hour = 14
        mock_dt.utcnow.return_value.minute = 30
        assert engine._is_market_open()
        
        # Test weekday after hours (22 UTC = 5 PM EST)
        mock_dt.utcnow.return_value.hour = 22
        assert not engine._is_market_open()