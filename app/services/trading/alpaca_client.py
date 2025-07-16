"""Alpaca trading client wrapper for paper trading."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from uuid import UUID

import aiohttp
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.live import StockDataStream
from alpaca.trading.stream import TradingStream

from app.config.settings import get_settings
from app.models.order import OrderStatus

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Async wrapper for Alpaca paper trading API."""
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_API_SECRET
        self.base_url = settings.ALPACA_BASE_URL or "https://paper-api.alpaca.markets"
        
        # Trading client for REST API
        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True
        )
        
        # WebSocket stream for order updates
        self.stream_client: Optional[TradingStream] = None
        self.order_update_handler: Optional[Callable] = None
        
        # WebSocket connection state
        self._ws_connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        
    async def initialize_stream(self, order_update_handler: Callable):
        """Initialize WebSocket stream for order updates."""
        self.order_update_handler = order_update_handler
        self.stream_client = TradingStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            raw_data=True
        )
        
        # Define handler for trade updates
        async def handle_trade_update(data):
            try:
                await self.order_update_handler(data)
            except Exception as e:
                logger.error(f"Error handling trade update: {e}")
        
        # Subscribe to trade updates
        self.stream_client.subscribe_trade_updates(handle_trade_update)
        
    async def connect_stream(self):
        """Connect to WebSocket stream with auto-reconnect."""
        if not self.stream_client:
            raise RuntimeError("Stream client not initialized")
            
        while True:
            try:
                logger.info("Connecting to Alpaca WebSocket stream...")
                self._ws_connected = True
                # Use _run_forever() instead of run() to work with existing event loop
                await self.stream_client._run_forever()
            except Exception as e:
                logger.error(f"Alpaca WebSocket disconnected: {e}")
                self._ws_connected = False
                await asyncio.sleep(5)  # Reconnect delay
                
    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """Submit an order to Alpaca."""
        try:
            # Convert symbol format if needed (BTCUSDT -> BTC/USD)
            if symbol.endswith("USDT"):
                alpaca_symbol = symbol[:-4] + "/USD"
            else:
                alpaca_symbol = symbol
                
            # Convert parameters
            alpaca_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            alpaca_tif = TimeInForce.DAY if time_in_force.lower() == "day" else TimeInForce.GTC
            
            # Create order request based on type
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif
                )
            elif order_type.lower() == "limit":
                if not limit_price:
                    raise ValueError("Limit price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=alpaca_symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    limit_price=limit_price
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            # Submit order
            order = self.trading_client.submit_order(order_request)
            
            return {
                "alpaca_id": order.id,
                "status": self._map_order_status(order.status),
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_price": float(order.filled_avg_price) if order.filled_avg_price else None
            }
            
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            raise
            
    async def cancel_order(self, alpaca_order_id: str) -> bool:
        """Cancel an order."""
        try:
            self.trading_client.cancel_order_by_id(alpaca_order_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {alpaca_order_id}: {e}")
            return False
            
    async def get_order(self, alpaca_order_id: str) -> Optional[Dict[str, Any]]:
        """Get order details."""
        try:
            order = self.trading_client.get_order_by_id(alpaca_order_id)
            return {
                "alpaca_id": order.id,
                "status": self._map_order_status(order.status),
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None
            }
        except Exception as e:
            logger.error(f"Error getting order {alpaca_order_id}: {e}")
            return None
            
    async def get_account(self) -> Dict[str, Any]:
        """Get account information."""
        try:
            account = self.trading_client.get_account()
            return {
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            raise
            
    async def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all positions."""
        try:
            positions = self.trading_client.get_all_positions()
            return {
                pos.symbol: {
                    "qty": float(pos.qty),
                    "avg_price": float(pos.avg_entry_price),
                    "market_value": float(pos.market_value),
                    "cost_basis": float(pos.cost_basis),
                    "unrealized_pnl": float(pos.unrealized_pl),
                    "current_price": float(pos.current_price) if pos.current_price else None
                }
                for pos in positions
            }
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {}
            
    def _map_order_status(self, alpaca_status: str) -> OrderStatus:
        """Map Alpaca order status to our OrderStatus enum."""
        status_map = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "partially_filled": OrderStatus.PARTIAL,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.EXPIRED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "replaced": OrderStatus.CANCELLED,
            "pending_cancel": OrderStatus.SUBMITTED,
            "pending_replace": OrderStatus.SUBMITTED,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.SUBMITTED,
            "calculated": OrderStatus.SUBMITTED
        }
        return status_map.get(alpaca_status.lower(), OrderStatus.PENDING)
        
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws_connected
        
    async def close(self):
        """Close all connections."""
        if self.stream_client:
            try:
                await self.stream_client.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
        self._ws_connected = False