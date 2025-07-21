"""Kraken API client for market data and trading."""
import asyncio
import aiohttp
import json
import hmac
import hashlib
import base64
import time
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from app.monitoring.logger import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class KrakenQuote:
    """Kraken market quote."""
    symbol: str
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    last_price: float
    volume_24h: float
    vwap_24h: float
    trades_24h: int
    low_24h: float
    high_24h: float
    timestamp: datetime


class KrakenClient:
    """Kraken API client."""
    
    def __init__(self):
        self.api_key = settings.KRAKEN_API_KEY
        self.api_secret = settings.KRAKEN_API_SECRET
        self.base_url = "https://api.kraken.com"
        self.ws_url = "wss://ws.kraken.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.subscriptions: Dict[str, List[Callable]] = {}
        self.ws_token: Optional[str] = None
        
        # Symbol mapping (Kraken uses different format)
        self.symbol_map = {
            "BTCUSD": "XXBTZUSD",
            "ETHUSD": "XETHZUSD",
            "LTCUSD": "XLTCZUSD",
            "XRPUSD": "XXRPZUSD",
            "ADAUSD": "ADAUSD",
            "DOTUSD": "DOTUSD",
            "LINKUSD": "LINKUSD",
            "MATICUSD": "MATICUSD",
            "SOLUSD": "SOLUSD",
            "UNIUSD": "UNIUSD"
        }
        
        # Reverse mapping
        self.reverse_symbol_map = {v: k for k, v in self.symbol_map.items()}
        
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
            
    def _get_kraken_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Kraken format."""
        return self.symbol_map.get(symbol, symbol)
        
    def _get_standard_symbol(self, kraken_symbol: str) -> str:
        """Convert Kraken symbol to standard format."""
        return self.reverse_symbol_map.get(kraken_symbol, kraken_symbol)
        
    def _generate_signature(self, path: str, data: str, nonce: str) -> str:
        """Generate signature for private endpoints."""
        message = (nonce + data).encode()
        secret = base64.b64decode(self.api_secret)
        
        sha256_hash = hashlib.sha256(message).digest()
        hmac_obj = hmac.new(secret, path.encode() + sha256_hash, hashlib.sha512)
        
        return base64.b64encode(hmac_obj.digest()).decode()
        
    async def _public_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make public API request."""
        if not self.session:
            await self.connect()
            
        url = f"{self.base_url}/0/public/{endpoint}"
        
        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()
                
                if data.get("error"):
                    raise Exception(f"Kraken API error: {data['error']}")
                    
                return data.get("result", {})
                
        except Exception as e:
            logger.error(f"Error in public request to {endpoint}: {e}")
            raise
            
    async def _private_request(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make authenticated private API request."""
        if not self.session:
            await self.connect()
            
        path = f"/0/private/{endpoint}"
        url = f"{self.base_url}{path}"
        
        nonce = str(int(time.time() * 1000))
        
        post_data = data or {}
        post_data["nonce"] = nonce
        
        encoded_data = urllib.parse.urlencode(post_data)
        
        headers = {
            "API-Key": self.api_key,
            "API-Sign": self._generate_signature(path, encoded_data, nonce),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            async with self.session.post(url, headers=headers, data=encoded_data) as response:
                data = await response.json()
                
                if data.get("error"):
                    raise Exception(f"Kraken API error: {data['error']}")
                    
                return data.get("result", {})
                
        except Exception as e:
            logger.error(f"Error in private request to {endpoint}: {e}")
            raise
            
    async def get_asset_pairs(self) -> Dict[str, Any]:
        """Get available trading pairs."""
        try:
            return await self._public_request("AssetPairs")
        except Exception as e:
            logger.error(f"Error getting asset pairs: {e}")
            return {}
            
    async def get_ticker(self, symbol: str) -> Optional[KrakenQuote]:
        """Get current ticker information."""
        try:
            kraken_symbol = self._get_kraken_symbol(symbol)
            result = await self._public_request("Ticker", {"pair": kraken_symbol})
            
            if not result or kraken_symbol not in result:
                return None
                
            ticker = result[kraken_symbol]
            
            return KrakenQuote(
                symbol=symbol,
                bid=float(ticker["b"][0]),  # Best bid price
                bid_size=float(ticker["b"][2]),  # Bid lot volume
                ask=float(ticker["a"][0]),  # Best ask price
                ask_size=float(ticker["a"][2]),  # Ask lot volume
                last_price=float(ticker["c"][0]),  # Last trade price
                volume_24h=float(ticker["v"][1]),  # Volume last 24h
                vwap_24h=float(ticker["p"][1]),  # VWAP last 24h
                trades_24h=int(ticker["t"][1]),  # Number of trades last 24h
                low_24h=float(ticker["l"][1]),  # Low last 24h
                high_24h=float(ticker["h"][1]),  # High last 24h
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error getting ticker for {symbol}: {e}")
            return None
            
    async def get_order_book(self, symbol: str, count: int = 100) -> Dict[str, Any]:
        """Get order book for a symbol."""
        try:
            kraken_symbol = self._get_kraken_symbol(symbol)
            result = await self._public_request("Depth", {"pair": kraken_symbol, "count": count})
            
            if not result or kraken_symbol not in result:
                return {}
                
            book = result[kraken_symbol]
            
            return {
                "bids": [[float(p), float(v)] for p, v, _ in book.get("bids", [])],
                "asks": [[float(p), float(v)] for p, v, _ in book.get("asks", [])],
                "timestamp": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting order book for {symbol}: {e}")
            return {}
            
    async def get_ohlc(
        self,
        symbol: str,
        interval: int = 1,  # 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
        since: Optional[int] = None
    ) -> List[List[float]]:
        """Get OHLC data."""
        try:
            kraken_symbol = self._get_kraken_symbol(symbol)
            params = {"pair": kraken_symbol, "interval": interval}
            
            if since:
                params["since"] = since
                
            result = await self._public_request("OHLC", params)
            
            if not result or kraken_symbol not in result:
                return []
                
            # Format: [time, open, high, low, close, vwap, volume, count]
            return result[kraken_symbol]
            
        except Exception as e:
            logger.error(f"Error getting OHLC for {symbol}: {e}")
            return []
            
    async def get_balance(self) -> Dict[str, float]:
        """Get account balance."""
        try:
            result = await self._private_request("Balance")
            
            # Convert to standard format
            balance = {}
            for asset, amount in result.items():
                # Remove X prefix for crypto assets
                clean_asset = asset[1:] if asset.startswith("X") and len(asset) == 4 else asset
                balance[clean_asset] = float(amount)
                
            return balance
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {}
            
    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        volume: float,
        order_type: str = "market",
        price: Optional[float] = None,
        leverage: Optional[str] = None,
        validate: bool = False
    ) -> Dict[str, Any]:
        """Place an order."""
        try:
            kraken_symbol = self._get_kraken_symbol(symbol)
            
            order_data = {
                "pair": kraken_symbol,
                "type": side.lower(),
                "ordertype": order_type,
                "volume": str(volume)
            }
            
            if price and order_type == "limit":
                order_data["price"] = str(price)
                
            if leverage:
                order_data["leverage"] = leverage
                
            if validate:
                order_data["validate"] = "true"
                
            result = await self._private_request("AddOrder", order_data)
            
            return {
                "order_id": result.get("txid", [None])[0],
                "description": result.get("descr", {})
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise
            
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            result = await self._private_request("CancelOrder", {"txid": order_id})
            return result.get("count", 0) > 0
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return False
            
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get open orders."""
        try:
            result = await self._private_request("OpenOrders")
            
            orders = []
            for order_id, order_info in result.get("open", {}).items():
                orders.append({
                    "order_id": order_id,
                    "symbol": self._get_standard_symbol(order_info["descr"]["pair"]),
                    "side": order_info["descr"]["type"],
                    "price": float(order_info.get("price", 0)),
                    "volume": float(order_info["vol"]),
                    "executed": float(order_info["vol_exec"]),
                    "status": order_info["status"],
                    "timestamp": datetime.fromtimestamp(order_info["opentm"])
                })
                
            return orders
            
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []
            
    async def get_trades_history(self, start: Optional[int] = None, end: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get trade history."""
        try:
            params = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
                
            result = await self._private_request("TradesHistory", params)
            
            trades = []
            for trade_id, trade_info in result.get("trades", {}).items():
                trades.append({
                    "trade_id": trade_id,
                    "order_id": trade_info["ordertxid"],
                    "symbol": self._get_standard_symbol(trade_info["pair"]),
                    "side": trade_info["type"],
                    "price": float(trade_info["price"]),
                    "volume": float(trade_info["vol"]),
                    "cost": float(trade_info["cost"]),
                    "fee": float(trade_info["fee"]),
                    "timestamp": datetime.fromtimestamp(trade_info["time"])
                })
                
            return trades
            
        except Exception as e:
            logger.error(f"Error getting trades history: {e}")
            return []
            
    # WebSocket Methods
    
    async def get_websocket_token(self) -> str:
        """Get WebSocket authentication token."""
        try:
            result = await self._private_request("GetWebSocketsToken")
            return result.get("token", "")
        except Exception as e:
            logger.error(f"Error getting WebSocket token: {e}")
            return ""
            
    async def connect_websocket(self):
        """Connect to Kraken WebSocket."""
        if self.websocket and not self.websocket.closed:
            return
            
        self.ws_session = aiohttp.ClientSession()
        
        try:
            # Get auth token for private channels
            self.ws_token = await self.get_websocket_token()
            
            self.websocket = await self.ws_session.ws_connect(self.ws_url)
            
            # Start message handler
            asyncio.create_task(self._handle_messages())
            
            logger.info("Connected to Kraken WebSocket")
            
        except Exception as e:
            logger.error(f"Error connecting to Kraken WebSocket: {e}")
            if self.ws_session:
                await self.ws_session.close()
            raise
            
    async def subscribe_ticker(self, symbols: List[str], callback: Callable):
        """Subscribe to ticker updates."""
        await self.connect_websocket()
        
        # Convert symbols to Kraken format
        kraken_symbols = [self._get_kraken_symbol(s) for s in symbols]
        
        # Store callbacks
        for symbol in symbols:
            if symbol not in self.subscriptions:
                self.subscriptions[symbol] = []
            self.subscriptions[symbol].append(callback)
            
        # Subscribe to ticker and spread channels
        sub_message = {
            "event": "subscribe",
            "pair": kraken_symbols,
            "subscription": {
                "name": "ticker"
            }
        }
        
        await self.websocket.send_json(sub_message)
        
        # Also subscribe to spread for better bid/ask
        spread_sub = {
            "event": "subscribe",
            "pair": kraken_symbols,
            "subscription": {
                "name": "spread"
            }
        }
        
        await self.websocket.send_json(spread_sub)
        
        logger.info(f"Subscribed to tickers: {symbols}")
        
    async def _handle_messages(self):
        """Handle incoming WebSocket messages."""
        try:
            # Cache for latest ticker data
            ticker_cache = {}
            
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Skip heartbeat
                    if isinstance(data, dict) and data.get("event") == "heartbeat":
                        continue
                        
                    # Process ticker data
                    if isinstance(data, list) and len(data) >= 4:
                        channel_id = data[0]
                        ticker_data = data[1]
                        channel_name = data[2]
                        pair = data[3]
                        
                        # Convert to standard symbol
                        symbol = self._get_standard_symbol(pair)
                        
                        if channel_name == "ticker":
                            # Update ticker cache
                            ticker_cache[symbol] = ticker_data
                            
                            # Create quote object
                            if symbol in self.subscriptions:
                                quote = KrakenQuote(
                                    symbol=symbol,
                                    bid=float(ticker_data.get("b", [0])[0]),
                                    bid_size=float(ticker_data.get("b", [0, 0])[1]),
                                    ask=float(ticker_data.get("a", [0])[0]),
                                    ask_size=float(ticker_data.get("a", [0, 0])[1]),
                                    last_price=float(ticker_data.get("c", [0])[0]),
                                    volume_24h=float(ticker_data.get("v", [0])[1]),
                                    vwap_24h=float(ticker_data.get("p", [0])[1]),
                                    trades_24h=int(ticker_data.get("t", [0])[1]),
                                    low_24h=float(ticker_data.get("l", [0])[1]),
                                    high_24h=float(ticker_data.get("h", [0])[1]),
                                    timestamp=datetime.utcnow()
                                )
                                
                                # Call callbacks
                                for callback in self.subscriptions[symbol]:
                                    try:
                                        await callback(quote)
                                    except Exception as e:
                                        logger.error(f"Error in ticker callback: {e}")
                                        
                        elif channel_name == "spread":
                            # Update bid/ask in cache if ticker exists
                            if symbol in ticker_cache:
                                bid, ask, timestamp, bid_vol, ask_vol = ticker_data
                                ticker_cache[symbol]["b"] = [float(bid), float(bid_vol)]
                                ticker_cache[symbol]["a"] = [float(ask), float(ask_vol)]
                                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.websocket.exception()}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
                    
        except Exception as e:
            logger.error(f"Error handling WebSocket messages: {e}")


# Global instance
kraken_client = KrakenClient()