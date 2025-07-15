"""Binance WebSocket client for cryptocurrency data."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.config.settings import settings
from app.services.ingestor.models import Exchange, Tick, TickType, TOP_15_CRYPTOS

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """WebSocket client for Binance market data streams."""
    
    def __init__(self, queue: asyncio.Queue):
        """Initialize Binance client.
        
        Args:
            queue: Queue to push parsed ticks
        """
        self.queue = queue
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.symbols = set(TOP_15_CRYPTOS)
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        
    async def connect(self) -> None:
        """Connect to Binance WebSocket."""
        # Build stream names for all symbols
        streams = []
        for symbol in self.symbols:
            symbol_lower = symbol.lower()
            streams.extend([
                f"{symbol_lower}@trade",      # Trade stream
                f"{symbol_lower}@bookTicker", # Best bid/ask stream
            ])
        
        # Construct WebSocket URL
        stream_param = "/".join(streams)
        url = f"{settings.BINANCE_API_URL}/stream?streams={stream_param}"
        
        logger.info(f"Connecting to Binance WebSocket: {url}")
        self.websocket = await websockets.connect(url)
        self.reconnect_delay = 1.0  # Reset delay on successful connection
        logger.info("Connected to Binance WebSocket")
        
    async def disconnect(self) -> None:
        """Disconnect from Binance WebSocket."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("Disconnected from Binance WebSocket")
            
    async def parse_message(self, message: dict) -> Optional[Tick]:
        """Parse Binance message into unified Tick.
        
        Args:
            message: Raw message from Binance
            
        Returns:
            Parsed Tick or None if parsing fails
        """
        try:
            data = message.get("data", {})
            stream = message.get("stream", "")
            
            if "@trade" in stream:
                # Parse trade data
                return Tick(
                    symbol=data["s"],
                    exchange=Exchange.BINANCE,
                    tick_type=TickType.TRADE,
                    timestamp=datetime.fromtimestamp(data["T"] / 1000),
                    price=float(data["p"]),
                    volume=float(data["q"]),
                )
            elif "@bookTicker" in stream:
                # Parse best bid/ask data
                return Tick(
                    symbol=data["s"],
                    exchange=Exchange.BINANCE,
                    tick_type=TickType.QUOTE,
                    timestamp=datetime.fromtimestamp(data["E"] / 1000),
                    price=(float(data["b"]) + float(data["a"])) / 2,  # Mid price
                    bid_price=float(data["b"]),
                    ask_price=float(data["a"]),
                    bid_size=float(data["B"]),
                    ask_size=float(data["A"]),
                )
        except Exception as e:
            logger.error(f"Failed to parse Binance message: {e}, message: {message}")
            return None
            
    async def run(self) -> None:
        """Run the WebSocket client with automatic reconnection."""
        self.running = True
        
        while self.running:
            try:
                # Connect to WebSocket
                await self.connect()
                
                # Receive and process messages
                async for message in self.websocket:
                    if not self.running:
                        break
                        
                    try:
                        data = json.loads(message)
                        tick = await self.parse_message(data)
                        if tick:
                            await self.queue.put(tick)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode Binance message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing Binance message: {e}")
                        
            except ConnectionClosed as e:
                logger.warning(f"Binance WebSocket connection closed: {e}")
            except WebSocketException as e:
                logger.error(f"Binance WebSocket error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in Binance client: {e}")
            finally:
                await self.disconnect()
                
            if self.running:
                # Exponential backoff for reconnection
                logger.info(f"Reconnecting to Binance in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, 
                    self.max_reconnect_delay
                )
                
    async def stop(self) -> None:
        """Stop the WebSocket client."""
        logger.info("Stopping Binance WebSocket client")
        self.running = False
        await self.disconnect()