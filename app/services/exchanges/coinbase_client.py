"""Coinbase Pro/Advanced Trade API client for market data and trading."""
import asyncio
import aiohttp
import json
import hmac
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from app.monitoring.logger import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class CoinbaseQuote:
    """Coinbase market quote."""
    symbol: str
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    last_price: float
    volume_24h: float
    timestamp: datetime


class CoinbaseClient:
    """Coinbase Advanced Trade API client."""
    
    def __init__(self):
        self.api_key = settings.COINBASE_API_KEY
        self.api_secret = settings.COINBASE_API_SECRET
        self.base_url = "https://api.coinbase.com/api/v3/brokerage"
        self.ws_url = "wss://advanced-trade-ws.coinbase.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.subscriptions: Dict[str, List[Callable]] = {}
        
    async def connect(self):
        """Initialize HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def disconnect(self):
        """Close connections."""
        if self.websocket:
            await self.websocket.close()
        if self.ws_session:
            await self.ws_session.close()
        if self.session:
            await self.session.close()
            
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for Coinbase API."""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
        
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make authenticated API request."""
        if not self.session:
            await self.connect()
            
        timestamp = str(int(time.time()))
        path = f"/api/v3/brokerage{endpoint}"
        body = json.dumps(data) if data else ""
        
        headers = {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-SIGN": self._generate_signature(timestamp, method, path, body),
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with self.session.request(method, url, headers=headers, data=body) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Coinbase API error: {response.status} - {error_text}")
            return await response.json()
            
    async def get_products(self) -> List[Dict[str, Any]]:
        """Get list of available trading pairs."""
        try:
            response = await self._request("GET", "/products")
            return response.get("products", [])
        except Exception as e:
            logger.error(f"Error getting Coinbase products: {e}")
            return []
            
    async def get_product_book(self, product_id: str, level: int = 2) -> Dict[str, Any]:
        """Get order book for a product."""
        try:
            params = f"?product_id={product_id}&level={level}"
            response = await self._request("GET", f"/product_book{params}")
            return response.get("pricebook", {})
        except Exception as e:
            logger.error(f"Error getting product book for {product_id}: {e}")
            return {}
            
    async def get_ticker(self, product_id: str) -> Optional[CoinbaseQuote]:
        """Get current ticker for a product."""
        try:
            # Get order book for best bid/ask
            book = await self.get_product_book(product_id, level=1)
            if not book:
                return None
                
            # Get product stats for 24h volume
            params = f"?product_id={product_id}"
            stats = await self._request("GET", f"/products/{product_id}")
            
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            if not bids or not asks:
                return None
                
            return CoinbaseQuote(
                symbol=product_id,
                bid=float(bids[0]["price"]),
                bid_size=float(bids[0]["size"]),
                ask=float(asks[0]["price"]),
                ask_size=float(asks[0]["size"]),
                last_price=float(stats.get("price", asks[0]["price"])),
                volume_24h=float(stats.get("volume_24h", 0)),
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error getting ticker for {product_id}: {e}")
            return None
            
    async def get_candles(
        self,
        product_id: str,
        start: datetime,
        end: datetime,
        granularity: str = "ONE_MINUTE"
    ) -> List[Dict[str, Any]]:
        """Get historical candle data."""
        try:
            params = {
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
                "granularity": granularity
            }
            
            response = await self._request(
                "GET",
                f"/products/{product_id}/candles?{self._encode_params(params)}"
            )
            
            return response.get("candles", [])
            
        except Exception as e:
            logger.error(f"Error getting candles for {product_id}: {e}")
            return []
            
    def _encode_params(self, params: Dict[str, Any]) -> str:
        """Encode parameters for URL."""
        return "&".join([f"{k}={v}" for k, v in params.items()])
        
    async def place_order(
        self,
        product_id: str,
        side: str,  # "BUY" or "SELL"
        size: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place an order."""
        try:
            order_config = {
                "product_id": product_id,
                "side": side.upper(),
                "order_configuration": {}
            }
            
            if client_order_id:
                order_config["client_order_id"] = client_order_id
                
            if order_type == "market":
                order_config["order_configuration"]["market_market_ioc"] = {
                    "quote_size": str(size) if side == "BUY" else None,
                    "base_size": str(size) if side == "SELL" else None
                }
            else:  # limit order
                order_config["order_configuration"]["limit_limit_gtc"] = {
                    "base_size": str(size),
                    "limit_price": str(limit_price)
                }
                
            response = await self._request("POST", "/orders", order_config)
            return response
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise
            
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        try:
            order_ids = {"order_ids": [order_id]}
            response = await self._request("POST", "/orders/batch_cancel", order_ids)
            return response
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            raise
            
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details."""
        try:
            response = await self._request("GET", f"/orders/historical/{order_id}")
            return response.get("order", {})
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return {}
            
    async def get_fills(self, order_id: Optional[str] = None, product_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get fills for orders."""
        try:
            params = {}
            if order_id:
                params["order_id"] = order_id
            if product_id:
                params["product_id"] = product_id
                
            endpoint = "/orders/historical/fills"
            if params:
                endpoint += f"?{self._encode_params(params)}"
                
            response = await self._request("GET", endpoint)
            return response.get("fills", [])
            
        except Exception as e:
            logger.error(f"Error getting fills: {e}")
            return []
            
    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get account information."""
        try:
            response = await self._request("GET", "/accounts")
            return response.get("accounts", [])
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
            
    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get specific account details."""
        try:
            response = await self._request("GET", f"/accounts/{account_id}")
            return response.get("account", {})
        except Exception as e:
            logger.error(f"Error getting account {account_id}: {e}")
            return {}
            
    # WebSocket Methods
    
    async def connect_websocket(self):
        """Connect to Coinbase WebSocket."""
        if self.websocket and not self.websocket.closed:
            return
            
        self.ws_session = aiohttp.ClientSession()
        
        try:
            self.websocket = await self.ws_session.ws_connect(self.ws_url)
            
            # Authenticate
            timestamp = str(int(time.time()))
            message = f"{timestamp}GET/users/self/verify"
            signature = hmac.new(
                self.api_secret.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            auth_message = {
                "type": "subscribe",
                "product_ids": [],
                "channel": "user",
                "api_key": self.api_key,
                "timestamp": timestamp,
                "signature": signature
            }
            
            await self.websocket.send_json(auth_message)
            
            # Start message handler
            asyncio.create_task(self._handle_messages())
            
            logger.info("Connected to Coinbase WebSocket")
            
        except Exception as e:
            logger.error(f"Error connecting to Coinbase WebSocket: {e}")
            if self.ws_session:
                await self.ws_session.close()
            raise
            
    async def subscribe_ticker(self, symbols: List[str], callback: Callable):
        """Subscribe to ticker updates."""
        await self.connect_websocket()
        
        # Store callback
        for symbol in symbols:
            if symbol not in self.subscriptions:
                self.subscriptions[symbol] = []
            self.subscriptions[symbol].append(callback)
            
        # Subscribe to ticker channel
        sub_message = {
            "type": "subscribe",
            "product_ids": symbols,
            "channels": ["ticker", "level2"]
        }
        
        await self.websocket.send_json(sub_message)
        logger.info(f"Subscribed to tickers: {symbols}")
        
    async def _handle_messages(self):
        """Handle incoming WebSocket messages."""
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._process_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.websocket.exception()}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
                    
        except Exception as e:
            logger.error(f"Error handling WebSocket messages: {e}")
            
    async def _process_message(self, data: Dict[str, Any]):
        """Process WebSocket message."""
        msg_type = data.get("type")
        
        if msg_type == "ticker":
            symbol = data.get("product_id")
            if symbol in self.subscriptions:
                quote = CoinbaseQuote(
                    symbol=symbol,
                    bid=float(data.get("best_bid", 0)),
                    bid_size=float(data.get("best_bid_size", 0)),
                    ask=float(data.get("best_ask", 0)),
                    ask_size=float(data.get("best_ask_size", 0)),
                    last_price=float(data.get("price", 0)),
                    volume_24h=float(data.get("volume_24h", 0)),
                    timestamp=datetime.fromisoformat(data.get("time", datetime.utcnow().isoformat()))
                )
                
                # Call all callbacks for this symbol
                for callback in self.subscriptions[symbol]:
                    try:
                        await callback(quote)
                    except Exception as e:
                        logger.error(f"Error in ticker callback: {e}")
                        
        elif msg_type == "error":
            logger.error(f"Coinbase WebSocket error: {data}")


# Global instance
coinbase_client = CoinbaseClient()