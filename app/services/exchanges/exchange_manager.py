"""Unified exchange manager for multi-exchange operations."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from app.monitoring.logger import get_logger
from app.services.exchanges import coinbase_client, kraken_client
from app.services.trading.alpaca_client import get_alpaca_client
from app.db.questdb import get_questdb_pool

logger = get_logger(__name__)


class Exchange(str, Enum):
    """Supported exchanges."""
    ALPACA = "alpaca"
    BINANCE = "binance"
    COINBASE = "coinbase"
    KRAKEN = "kraken"


@dataclass
class UnifiedQuote:
    """Unified quote across all exchanges."""
    symbol: str
    exchange: Exchange
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    mid: float
    spread: float
    spread_pct: float
    last_price: float
    volume_24h: float
    timestamp: datetime


@dataclass
class BestQuote:
    """Best bid and ask across exchanges."""
    symbol: str
    best_bid: float
    best_bid_size: float
    best_bid_exchange: Exchange
    best_ask: float
    best_ask_size: float
    best_ask_exchange: Exchange
    spread: float
    spread_pct: float
    arbitrage_opportunity: bool
    timestamp: datetime


class ExchangeManager:
    """Manages connections and operations across multiple exchanges."""
    
    def __init__(self):
        self.alpaca_client = get_alpaca_client()
        self.active_exchanges = {
            Exchange.ALPACA: True,
            Exchange.BINANCE: True,
            Exchange.COINBASE: False,  # Disabled until API keys configured
            Exchange.KRAKEN: False     # Disabled until API keys configured
        }
        self.quote_callbacks: Dict[str, List[Callable]] = {}
        
    async def initialize(self):
        """Initialize exchange connections."""
        tasks = []
        
        # Connect to exchanges with API keys
        if coinbase_client.api_key and self.active_exchanges[Exchange.COINBASE]:
            tasks.append(coinbase_client.connect())
            
        if kraken_client.api_key and self.active_exchanges[Exchange.KRAKEN]:
            tasks.append(kraken_client.connect())
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        logger.info("Exchange manager initialized")
        
    async def disconnect(self):
        """Disconnect from all exchanges."""
        tasks = []
        
        if self.active_exchanges[Exchange.COINBASE]:
            tasks.append(coinbase_client.disconnect())
            
        if self.active_exchanges[Exchange.KRAKEN]:
            tasks.append(kraken_client.disconnect())
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    def enable_exchange(self, exchange: Exchange, enabled: bool = True):
        """Enable or disable an exchange."""
        self.active_exchanges[exchange] = enabled
        logger.info(f"Exchange {exchange} {'enabled' if enabled else 'disabled'}")
        
    async def get_quote(self, symbol: str, exchange: Exchange) -> Optional[UnifiedQuote]:
        """Get quote from specific exchange."""
        if not self.active_exchanges.get(exchange):
            return None
            
        try:
            if exchange == Exchange.ALPACA:
                quote = await self.alpaca_client.get_latest_quote(symbol)
                if quote:
                    bid = quote['bid_price']
                    ask = quote['ask_price']
                    return UnifiedQuote(
                        symbol=symbol,
                        exchange=exchange,
                        bid=bid,
                        ask=ask,
                        bid_size=quote['bid_size'],
                        ask_size=quote['ask_size'],
                        mid=(bid + ask) / 2,
                        spread=ask - bid,
                        spread_pct=(ask - bid) / ask if ask > 0 else 0,
                        last_price=quote.get('last_price', ask),
                        volume_24h=0,  # Alpaca doesn't provide 24h volume in quote
                        timestamp=datetime.utcnow()
                    )
                    
            elif exchange == Exchange.BINANCE:
                # Get from QuestDB
                query = f"""
                SELECT price, bid, ask, bid_size, ask_size, volume
                FROM market_ticks
                WHERE symbol = '{symbol}'
                AND exchange = 'binance'
                ORDER BY timestamp DESC
                LIMIT 1
                """
                
                async with get_questdb_pool() as conn:
                    result = await conn.fetch(query)
                    
                if result:
                    row = result[0]
                    bid = row['bid'] or row['price']
                    ask = row['ask'] or row['price']
                    return UnifiedQuote(
                        symbol=symbol,
                        exchange=exchange,
                        bid=bid,
                        ask=ask,
                        bid_size=row['bid_size'] or 100,
                        ask_size=row['ask_size'] or 100,
                        mid=(bid + ask) / 2,
                        spread=ask - bid,
                        spread_pct=(ask - bid) / ask if ask > 0 else 0,
                        last_price=row['price'],
                        volume_24h=row['volume'] or 0,
                        timestamp=datetime.utcnow()
                    )
                    
            elif exchange == Exchange.COINBASE:
                # Convert symbol format
                if symbol.endswith("USD") and len(symbol) > 3:
                    base = symbol[:-3]
                    coinbase_symbol = f"{base}-USD"
                else:
                    coinbase_symbol = symbol
                    
                quote = await coinbase_client.get_ticker(coinbase_symbol)
                if quote:
                    return UnifiedQuote(
                        symbol=symbol,
                        exchange=exchange,
                        bid=quote.bid,
                        ask=quote.ask,
                        bid_size=quote.bid_size,
                        ask_size=quote.ask_size,
                        mid=(quote.bid + quote.ask) / 2,
                        spread=quote.ask - quote.bid,
                        spread_pct=(quote.ask - quote.bid) / quote.ask if quote.ask > 0 else 0,
                        last_price=quote.last_price,
                        volume_24h=quote.volume_24h,
                        timestamp=quote.timestamp
                    )
                    
            elif exchange == Exchange.KRAKEN:
                quote = await kraken_client.get_ticker(symbol)
                if quote:
                    return UnifiedQuote(
                        symbol=symbol,
                        exchange=exchange,
                        bid=quote.bid,
                        ask=quote.ask,
                        bid_size=quote.bid_size,
                        ask_size=quote.ask_size,
                        mid=(quote.bid + quote.ask) / 2,
                        spread=quote.ask - quote.bid,
                        spread_pct=(quote.ask - quote.bid) / quote.ask if quote.ask > 0 else 0,
                        last_price=quote.last_price,
                        volume_24h=quote.volume_24h,
                        timestamp=quote.timestamp
                    )
                    
        except Exception as e:
            logger.error(f"Error getting quote from {exchange} for {symbol}: {e}")
            
        return None
        
    async def get_all_quotes(self, symbol: str) -> List[UnifiedQuote]:
        """Get quotes from all active exchanges."""
        tasks = []
        
        for exchange in Exchange:
            if self.active_exchanges.get(exchange):
                tasks.append(self.get_quote(symbol, exchange))
                
        quotes = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        valid_quotes = [q for q in quotes if isinstance(q, UnifiedQuote)]
        
        return valid_quotes
        
    async def get_best_quote(self, symbol: str) -> Optional[BestQuote]:
        """Get best bid and ask across all exchanges."""
        quotes = await self.get_all_quotes(symbol)
        
        if not quotes:
            return None
            
        # Find best bid (highest) and best ask (lowest)
        best_bid_quote = max(quotes, key=lambda q: q.bid)
        best_ask_quote = min(quotes, key=lambda q: q.ask)
        
        # Check for arbitrage opportunity
        arbitrage = best_bid_quote.bid > best_ask_quote.ask
        
        return BestQuote(
            symbol=symbol,
            best_bid=best_bid_quote.bid,
            best_bid_size=best_bid_quote.bid_size,
            best_bid_exchange=best_bid_quote.exchange,
            best_ask=best_ask_quote.ask,
            best_ask_size=best_ask_quote.ask_size,
            best_ask_exchange=best_ask_quote.exchange,
            spread=best_ask_quote.ask - best_bid_quote.bid,
            spread_pct=(best_ask_quote.ask - best_bid_quote.bid) / best_ask_quote.ask if best_ask_quote.ask > 0 else 0,
            arbitrage_opportunity=arbitrage,
            timestamp=datetime.utcnow()
        )
        
    async def place_order(
        self,
        exchange: Exchange,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Place order on specific exchange."""
        try:
            if exchange == Exchange.ALPACA:
                order = await self.alpaca_client.submit_order(
                    symbol=symbol,
                    qty=quantity,
                    side=side,
                    order_type=order_type,
                    time_in_force="day",
                    limit_price=limit_price
                )
                return {"exchange": exchange, "order_id": order['id'], "status": "submitted"}
                
            elif exchange == Exchange.COINBASE:
                # Convert symbol format
                if symbol.endswith("USD") and len(symbol) > 3:
                    base = symbol[:-3]
                    coinbase_symbol = f"{base}-USD"
                else:
                    coinbase_symbol = symbol
                    
                order = await coinbase_client.place_order(
                    product_id=coinbase_symbol,
                    side=side.upper(),
                    size=quantity,
                    order_type=order_type,
                    limit_price=limit_price
                )
                return {"exchange": exchange, "order_id": order.get('order_id'), "status": "submitted"}
                
            elif exchange == Exchange.KRAKEN:
                order = await kraken_client.place_order(
                    symbol=symbol,
                    side=side,
                    volume=quantity,
                    order_type=order_type,
                    price=limit_price
                )
                return {"exchange": exchange, "order_id": order.get('order_id'), "status": "submitted"}
                
            else:
                return {"exchange": exchange, "error": "Exchange not supported for trading"}
                
        except Exception as e:
            logger.error(f"Error placing order on {exchange}: {e}")
            return {"exchange": exchange, "error": str(e)}
            
    async def get_balances(self) -> Dict[Exchange, Dict[str, float]]:
        """Get balances from all exchanges."""
        balances = {}
        
        try:
            # Alpaca
            if self.active_exchanges.get(Exchange.ALPACA):
                account = await self.alpaca_client.get_account()
                balances[Exchange.ALPACA] = {
                    "USD": float(account.get("cash", 0)),
                    "buying_power": float(account.get("buying_power", 0))
                }
                
            # Coinbase
            if self.active_exchanges.get(Exchange.COINBASE):
                accounts = await coinbase_client.get_accounts()
                balances[Exchange.COINBASE] = {
                    acc['currency']: float(acc['available_balance']['value'])
                    for acc in accounts
                    if float(acc['available_balance']['value']) > 0
                }
                
            # Kraken
            if self.active_exchanges.get(Exchange.KRAKEN):
                kraken_balance = await kraken_client.get_balance()
                balances[Exchange.KRAKEN] = kraken_balance
                
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            
        return balances
        
    async def start_quote_stream(self, symbols: List[str], callback: Callable):
        """Start streaming quotes from all exchanges."""
        # Store callback
        for symbol in symbols:
            if symbol not in self.quote_callbacks:
                self.quote_callbacks[symbol] = []
            self.quote_callbacks[symbol].append(callback)
            
        # Start WebSocket connections
        tasks = []
        
        if self.active_exchanges.get(Exchange.COINBASE):
            tasks.append(coinbase_client.subscribe_ticker(
                symbols,
                lambda q: asyncio.create_task(self._handle_quote(q, Exchange.COINBASE))
            ))
            
        if self.active_exchanges.get(Exchange.KRAKEN):
            tasks.append(kraken_client.subscribe_ticker(
                symbols,
                lambda q: asyncio.create_task(self._handle_quote(q, Exchange.KRAKEN))
            ))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    async def _handle_quote(self, quote: Any, exchange: Exchange):
        """Handle incoming quote from exchange."""
        try:
            # Convert to unified quote
            if exchange == Exchange.COINBASE:
                unified = UnifiedQuote(
                    symbol=quote.symbol,
                    exchange=exchange,
                    bid=quote.bid,
                    ask=quote.ask,
                    bid_size=quote.bid_size,
                    ask_size=quote.ask_size,
                    mid=(quote.bid + quote.ask) / 2,
                    spread=quote.ask - quote.bid,
                    spread_pct=(quote.ask - quote.bid) / quote.ask if quote.ask > 0 else 0,
                    last_price=quote.last_price,
                    volume_24h=quote.volume_24h,
                    timestamp=quote.timestamp
                )
            elif exchange == Exchange.KRAKEN:
                unified = UnifiedQuote(
                    symbol=quote.symbol,
                    exchange=exchange,
                    bid=quote.bid,
                    ask=quote.ask,
                    bid_size=quote.bid_size,
                    ask_size=quote.ask_size,
                    mid=(quote.bid + quote.ask) / 2,
                    spread=quote.ask - quote.bid,
                    spread_pct=(quote.ask - quote.bid) / quote.ask if quote.ask > 0 else 0,
                    last_price=quote.last_price,
                    volume_24h=quote.volume_24h,
                    timestamp=quote.timestamp
                )
            else:
                return
                
            # Call callbacks
            if quote.symbol in self.quote_callbacks:
                for callback in self.quote_callbacks[quote.symbol]:
                    await callback(unified)
                    
        except Exception as e:
            logger.error(f"Error handling quote from {exchange}: {e}")
            
    def get_supported_symbols(self, exchange: Exchange) -> List[str]:
        """Get list of supported symbols for an exchange."""
        if exchange == Exchange.ALPACA:
            # US stocks
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AMD"]
            
        elif exchange in [Exchange.BINANCE, Exchange.COINBASE, Exchange.KRAKEN]:
            # Cryptocurrencies
            return ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "ADAUSD", "DOTUSD", 
                   "LINKUSD", "MATICUSD", "SOLUSD", "UNIUSD"]
                   
        return []


# Global instance
exchange_manager = ExchangeManager()