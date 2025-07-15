"""Alpaca streaming client for US stock market data."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.config.settings import settings
from app.services.ingestor.models import Exchange, Tick, TickType, US_STOCKS

logger = logging.getLogger(__name__)


class AlpacaStreamingClient:
    """Streaming client for Alpaca market data."""
    
    def __init__(self, queue: asyncio.Queue):
        """Initialize Alpaca client.
        
        Args:
            queue: Queue to push parsed ticks
        """
        self.queue = queue
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.symbols = set(US_STOCKS)
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.authenticated = False
        
    async def connect(self) -> None:
        """Connect to Alpaca WebSocket."""
        # Use paper trading WebSocket URL
        url = "wss://stream.data.alpaca.markets/v2/iex"
        
        logger.info(f"Connecting to Alpaca WebSocket: {url}")
        self.websocket = await websockets.connect(url)
        self.reconnect_delay = 1.0  # Reset delay on successful connection
        logger.info("Connected to Alpaca WebSocket")
        
        # Authenticate
        await self.authenticate()
        
        # Subscribe to symbols
        await self.subscribe()
        
    async def authenticate(self) -> None:
        """Authenticate with Alpaca."""
        if not settings.ALPACA_API_KEY or not settings.ALPACA_API_SECRET:
            raise ValueError("Alpaca API credentials not configured")
            
        auth_message = {
            "action": "auth",
            "key": settings.ALPACA_API_KEY,
            "secret": settings.ALPACA_API_SECRET
        }
        
        await self.websocket.send(json.dumps(auth_message))
        
        # Wait for authentication response
        response = await self.websocket.recv()
        data = json.loads(response)
        
        if data[0]["msg"] == "authenticated":
            self.authenticated = True
            logger.info("Authenticated with Alpaca")
        else:
            raise ConnectionError(f"Alpaca authentication failed: {data}")
            
    async def subscribe(self) -> None:
        """Subscribe to market data streams."""
        # Subscribe to quotes and minute bars
        subscribe_message = {
            "action": "subscribe",
            "quotes": list(self.symbols),
            "bars": list(self.symbols)
        }
        
        await self.websocket.send(json.dumps(subscribe_message))
        logger.info(f"Subscribed to {len(self.symbols)} symbols on Alpaca")
        
    async def disconnect(self) -> None:
        """Disconnect from Alpaca WebSocket."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.authenticated = False
            logger.info("Disconnected from Alpaca WebSocket")
            
    async def parse_message(self, messages: list) -> list[Tick]:
        """Parse Alpaca messages into unified Ticks.
        
        Args:
            messages: List of messages from Alpaca
            
        Returns:
            List of parsed Ticks
        """
        ticks = []
        
        for message in messages:
            try:
                msg_type = message.get("T")
                
                if msg_type == "q":  # Quote
                    tick = Tick(
                        symbol=message["S"],
                        exchange=Exchange.ALPACA,
                        tick_type=TickType.QUOTE,
                        timestamp=datetime.fromisoformat(message["t"].replace("Z", "+00:00")),
                        price=(message["bp"] + message["ap"]) / 2,  # Mid price
                        bid_price=message["bp"],
                        ask_price=message["ap"],
                        bid_size=message["bs"],
                        ask_size=message["as"],
                    )
                    ticks.append(tick)
                    
                elif msg_type == "b":  # Bar (minute)
                    tick = Tick(
                        symbol=message["S"],
                        exchange=Exchange.ALPACA,
                        tick_type=TickType.BAR,
                        timestamp=datetime.fromisoformat(message["t"].replace("Z", "+00:00")),
                        price=message["c"],  # Close price
                        volume=message["v"],
                    )
                    ticks.append(tick)
                    
                elif msg_type == "error":
                    logger.error(f"Alpaca error message: {message}")
                    
            except Exception as e:
                logger.error(f"Failed to parse Alpaca message: {e}, message: {message}")
                
        return ticks
        
    async def run(self) -> None:
        """Run the streaming client with automatic reconnection."""
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
                        ticks = await self.parse_message(data)
                        for tick in ticks:
                            await self.queue.put(tick)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode Alpaca message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing Alpaca message: {e}")
                        
            except ConnectionClosed as e:
                logger.warning(f"Alpaca WebSocket connection closed: {e}")
            except WebSocketException as e:
                logger.error(f"Alpaca WebSocket error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in Alpaca client: {e}")
            finally:
                await self.disconnect()
                
            if self.running:
                # Exponential backoff for reconnection
                logger.info(f"Reconnecting to Alpaca in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, 
                    self.max_reconnect_delay
                )
                
    async def stop(self) -> None:
        """Stop the streaming client."""
        logger.info("Stopping Alpaca streaming client")
        self.running = False
        await self.disconnect()