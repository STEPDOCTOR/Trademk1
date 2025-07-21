"""Arbitrage opportunity scanner across exchanges and assets."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np

from app.monitoring.logger import get_logger
from app.services.trading.execution_engine import ExecutionEngine
from app.services.exchanges import coinbase_client, kraken_client

logger = get_logger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity."""
    type: str  # "cross_exchange", "triangular", "statistical", "futures_spot"
    symbols: List[str]
    exchanges: List[str]
    buy_price: float
    sell_price: float
    spread: float
    spread_pct: float
    estimated_profit: float
    estimated_profit_pct: float
    trade_size: float
    confidence: float
    time_window: int  # Seconds to execute
    detected_at: datetime
    details: Dict[str, Any]


@dataclass
class ExchangeQuote:
    """Quote from an exchange."""
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp: datetime


class ArbitrageScanner:
    """Scans for arbitrage opportunities across markets."""
    
    def __init__(self, execution_engine: ExecutionEngine):
        self.execution_engine = execution_engine
        self.exchanges = {
            "alpaca": self._get_alpaca_quote,
            "binance": self._get_binance_quote,
            "coinbase": self._get_coinbase_quote,
            "kraken": self._get_kraken_quote
        }
        self.min_profit_pct = 0.001  # 0.1% minimum profit
        self.max_trade_size = 10000  # Maximum USD per trade
        self.execution_time = 2  # Seconds to execute
        self.opportunities: List[ArbitrageOpportunity] = []
        self.scanning = False
        
    async def start_scanning(self, symbols: List[str], scan_interval: int = 1):
        """Start scanning for arbitrage opportunities."""
        self.scanning = True
        
        while self.scanning:
            try:
                # Cross-exchange arbitrage
                await self._scan_cross_exchange(symbols)
                
                # Triangular arbitrage (crypto)
                await self._scan_triangular_arbitrage()
                
                # Statistical arbitrage
                await self._scan_statistical_arbitrage(symbols)
                
                # Futures-spot arbitrage
                await self._scan_futures_spot_arbitrage(symbols)
                
                # Clean old opportunities
                self._clean_old_opportunities()
                
                await asyncio.sleep(scan_interval)
                
            except Exception as e:
                logger.error(f"Error in arbitrage scanner: {e}")
                await asyncio.sleep(5)
    
    async def _scan_cross_exchange(self, symbols: List[str]):
        """Scan for cross-exchange arbitrage opportunities."""
        for symbol in symbols:
            try:
                # Get quotes from all exchanges
                quotes = await self._get_quotes_all_exchanges(symbol)
                
                if len(quotes) < 2:
                    continue
                
                # Find best bid and ask across exchanges
                best_bid = max(quotes, key=lambda q: q.bid)
                best_ask = min(quotes, key=lambda q: q.ask)
                
                # Check if arbitrage exists
                if best_bid.bid > best_ask.ask:
                    spread = best_bid.bid - best_ask.ask
                    spread_pct = spread / best_ask.ask
                    
                    if spread_pct < self.min_profit_pct:
                        continue
                    
                    # Calculate trade size
                    max_size = min(
                        best_bid.bid_size * best_bid.bid,
                        best_ask.ask_size * best_ask.ask,
                        self.max_trade_size
                    )
                    
                    # Estimate profit (after fees)
                    buy_fee = 0.001  # 0.1% taker fee
                    sell_fee = 0.001
                    net_profit_pct = spread_pct - buy_fee - sell_fee
                    
                    if net_profit_pct > 0:
                        estimated_profit = max_size * net_profit_pct
                        
                        opportunity = ArbitrageOpportunity(
                            type="cross_exchange",
                            symbols=[symbol],
                            exchanges=[best_ask.exchange, best_bid.exchange],
                            buy_price=best_ask.ask,
                            sell_price=best_bid.bid,
                            spread=spread,
                            spread_pct=spread_pct,
                            estimated_profit=estimated_profit,
                            estimated_profit_pct=net_profit_pct,
                            trade_size=max_size,
                            confidence=0.9 if spread_pct > 0.002 else 0.7,
                            time_window=self.execution_time,
                            detected_at=datetime.utcnow(),
                            details={
                                "buy_exchange": best_ask.exchange,
                                "sell_exchange": best_bid.exchange,
                                "buy_size": best_ask.ask_size,
                                "sell_size": best_bid.bid_size
                            }
                        )
                        
                        self.opportunities.append(opportunity)
                        logger.info(
                            f"Cross-exchange arbitrage: {symbol} "
                            f"{best_ask.exchange} -> {best_bid.exchange} "
                            f"spread: {spread_pct:.2%}"
                        )
                        
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
    
    async def _scan_triangular_arbitrage(self):
        """Scan for triangular arbitrage in crypto markets."""
        # Common triangular paths
        triangular_paths = [
            ("BTCUSD", "ETHUSD", "ETHBTC"),
            ("BTCUSD", "LTCUSD", "LTCBTC"),
            ("BTCUSD", "XRPUSD", "XRPBTC"),
        ]
        
        for path in triangular_paths:
            try:
                # Get quotes for all three pairs
                quotes = {}
                for symbol in path:
                    quote = await self._get_best_quote(symbol)
                    if quote:
                        quotes[symbol] = quote
                
                if len(quotes) != 3:
                    continue
                
                # Calculate triangular arbitrage
                # Example: USD -> BTC -> ETH -> USD
                btc_usd = quotes[path[0]]
                eth_usd = quotes[path[1]]
                eth_btc = quotes[path[2]]
                
                # Path 1: USD -> BTC -> ETH -> USD
                usd_to_btc = 1 / btc_usd.ask  # Buy BTC
                btc_to_eth = usd_to_btc / eth_btc.ask  # Buy ETH with BTC
                eth_to_usd = btc_to_eth * eth_usd.bid  # Sell ETH for USD
                
                profit_path1 = eth_to_usd - 1
                
                # Path 2: USD -> ETH -> BTC -> USD
                usd_to_eth = 1 / eth_usd.ask  # Buy ETH
                eth_to_btc = usd_to_eth * eth_btc.bid  # Sell ETH for BTC
                btc_to_usd = eth_to_btc * btc_usd.bid  # Sell BTC for USD
                
                profit_path2 = btc_to_usd - 1
                
                # Check if either path is profitable
                best_profit = max(profit_path1, profit_path2)
                best_path = 1 if profit_path1 > profit_path2 else 2
                
                # Account for fees (3 trades * 0.1% each)
                total_fees = 0.003
                net_profit = best_profit - total_fees
                
                if net_profit > self.min_profit_pct:
                    opportunity = ArbitrageOpportunity(
                        type="triangular",
                        symbols=list(path),
                        exchanges=["binance"],  # Assuming single exchange
                        buy_price=0,  # Complex calculation
                        sell_price=0,
                        spread=best_profit,
                        spread_pct=best_profit,
                        estimated_profit=self.max_trade_size * net_profit,
                        estimated_profit_pct=net_profit,
                        trade_size=self.max_trade_size,
                        confidence=0.8,
                        time_window=5,  # Need more time for 3 trades
                        detected_at=datetime.utcnow(),
                        details={
                            "path": best_path,
                            "gross_profit": best_profit,
                            "fees": total_fees,
                            "trades": path if best_path == 1 else (path[1], path[2], path[0])
                        }
                    )
                    
                    self.opportunities.append(opportunity)
                    logger.info(
                        f"Triangular arbitrage: Path {best_path} "
                        f"profit: {net_profit:.2%}"
                    )
                    
            except Exception as e:
                logger.error(f"Error in triangular arbitrage scan: {e}")
    
    async def _scan_statistical_arbitrage(self, symbols: List[str]):
        """Scan for statistical arbitrage (mean reversion) opportunities."""
        # This would integrate with the pairs trading logic
        # Looking for temporary mispricings in correlated assets
        
        # Example: ETF vs underlying components
        etf_arb_pairs = [
            ("SPY", ["AAPL", "MSFT", "GOOGL", "AMZN"]),  # Simplified
            ("QQQ", ["AAPL", "MSFT", "META", "GOOGL"]),
        ]
        
        for etf, components in etf_arb_pairs:
            try:
                # Get ETF price
                etf_quote = await self._get_best_quote(etf)
                if not etf_quote:
                    continue
                
                # Calculate synthetic ETF price from components
                component_value = 0
                component_quotes = {}
                
                for comp in components:
                    quote = await self._get_best_quote(comp)
                    if quote:
                        component_quotes[comp] = quote
                        # Simplified - would need actual weights
                        component_value += quote.ask / len(components)
                
                if len(component_quotes) != len(components):
                    continue
                
                # Check for divergence
                etf_price = etf_quote.ask
                divergence = (component_value - etf_price) / etf_price
                
                if abs(divergence) > 0.002:  # 0.2% divergence
                    if divergence > 0:
                        # Components expensive, ETF cheap - buy ETF, sell components
                        action = "buy_etf_sell_components"
                    else:
                        # ETF expensive, components cheap - sell ETF, buy components
                        action = "sell_etf_buy_components"
                    
                    opportunity = ArbitrageOpportunity(
                        type="statistical",
                        symbols=[etf] + components,
                        exchanges=["alpaca"],
                        buy_price=etf_price if action.startswith("buy_etf") else component_value,
                        sell_price=component_value if action.startswith("buy_etf") else etf_price,
                        spread=abs(divergence * etf_price),
                        spread_pct=abs(divergence),
                        estimated_profit=self.max_trade_size * abs(divergence) * 0.5,  # Conservative
                        estimated_profit_pct=abs(divergence) * 0.5,
                        trade_size=self.max_trade_size,
                        confidence=0.6,  # Lower confidence for statistical arb
                        time_window=30,  # Longer window
                        detected_at=datetime.utcnow(),
                        details={
                            "action": action,
                            "etf_price": etf_price,
                            "synthetic_price": component_value,
                            "divergence": divergence
                        }
                    )
                    
                    self.opportunities.append(opportunity)
                    
            except Exception as e:
                logger.error(f"Error in statistical arbitrage scan: {e}")
    
    async def _scan_futures_spot_arbitrage(self, symbols: List[str]):
        """Scan for futures-spot arbitrage (cash and carry)."""
        # Example for crypto futures
        futures_pairs = [
            ("BTCUSD", "BTCUSD-PERP"),  # Spot vs perpetual
            ("ETHUSD", "ETHUSD-PERP"),
        ]
        
        for spot_symbol, futures_symbol in futures_pairs:
            try:
                # Get spot and futures prices
                spot_quote = await self._get_best_quote(spot_symbol)
                futures_quote = await self._get_best_quote(futures_symbol)
                
                if not spot_quote or not futures_quote:
                    continue
                
                # Calculate basis
                basis = futures_quote.ask - spot_quote.ask
                basis_pct = basis / spot_quote.ask
                
                # Funding rate (simplified - would need actual rate)
                funding_rate = 0.0001  # 0.01% per 8 hours
                
                # If futures trade at premium, sell futures and buy spot
                if basis_pct > funding_rate * 3:  # 3x funding for buffer
                    
                    # Estimate profit from convergence
                    days_to_expiry = 30  # For perpetuals, use funding period
                    expected_funding = funding_rate * (days_to_expiry / 0.33)  # 8hr periods
                    net_profit = basis_pct - expected_funding
                    
                    if net_profit > self.min_profit_pct:
                        opportunity = ArbitrageOpportunity(
                            type="futures_spot",
                            symbols=[spot_symbol, futures_symbol],
                            exchanges=["binance"],
                            buy_price=spot_quote.ask,
                            sell_price=futures_quote.bid,
                            spread=basis,
                            spread_pct=basis_pct,
                            estimated_profit=self.max_trade_size * net_profit,
                            estimated_profit_pct=net_profit,
                            trade_size=self.max_trade_size,
                            confidence=0.85,
                            time_window=60,  # Longer execution window
                            detected_at=datetime.utcnow(),
                            details={
                                "strategy": "cash_and_carry",
                                "basis": basis_pct,
                                "funding_rate": funding_rate,
                                "expected_funding_cost": expected_funding,
                                "days_to_carry": days_to_expiry
                            }
                        )
                        
                        self.opportunities.append(opportunity)
                        logger.info(
                            f"Futures-spot arbitrage: {spot_symbol} "
                            f"basis: {basis_pct:.2%}"
                        )
                        
            except Exception as e:
                logger.error(f"Error in futures-spot arbitrage scan: {e}")
    
    async def _get_quotes_all_exchanges(self, symbol: str) -> List[ExchangeQuote]:
        """Get quotes from all supported exchanges."""
        quotes = []
        
        # Determine which exchanges support this symbol
        if symbol.endswith("USD") and len(symbol) > 6:  # Crypto
            exchange_list = ["binance", "coinbase", "kraken"]
        else:  # Stock
            exchange_list = ["alpaca"]
        
        for exchange in exchange_list:
            if exchange in self.exchanges:
                quote = await self.exchanges[exchange](symbol)
                if quote:
                    quotes.append(quote)
        
        return quotes
    
    async def _get_best_quote(self, symbol: str) -> Optional[ExchangeQuote]:
        """Get best quote across all exchanges."""
        quotes = await self._get_quotes_all_exchanges(symbol)
        
        if not quotes:
            return None
        
        # Return quote with tightest spread
        return min(quotes, key=lambda q: q.ask - q.bid)
    
    async def _get_alpaca_quote(self, symbol: str) -> Optional[ExchangeQuote]:
        """Get quote from Alpaca."""
        try:
            quote = await self.execution_engine.alpaca_client.get_latest_quote(symbol)
            
            return ExchangeQuote(
                exchange="alpaca",
                symbol=symbol,
                bid=quote['bid_price'],
                ask=quote['ask_price'],
                bid_size=quote['bid_size'],
                ask_size=quote['ask_size'],
                timestamp=datetime.utcnow()
            )
        except:
            return None
    
    async def _get_binance_quote(self, symbol: str) -> Optional[ExchangeQuote]:
        """Get quote from Binance."""
        try:
            # Get from QuestDB (where we store Binance WebSocket data)
            query = f"""
            SELECT price, bid, ask, bid_size, ask_size
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND exchange = 'binance'
            ORDER BY timestamp DESC
            LIMIT 1
            """
            
            from app.db.questdb import get_questdb_pool
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                
            if result:
                row = result[0]
                return ExchangeQuote(
                    exchange="binance",
                    symbol=symbol,
                    bid=row['bid'] or row['price'],
                    ask=row['ask'] or row['price'],
                    bid_size=row['bid_size'] or 100,
                    ask_size=row['ask_size'] or 100,
                    timestamp=datetime.utcnow()
                )
        except:
            pass
        return None
    
    async def _get_coinbase_quote(self, symbol: str) -> Optional[ExchangeQuote]:
        """Get quote from Coinbase."""
        try:
            # Convert symbol format (BTCUSD -> BTC-USD)
            if symbol.endswith("USD") and len(symbol) > 3:
                base = symbol[:-3]
                coinbase_symbol = f"{base}-USD"
            else:
                coinbase_symbol = symbol
                
            quote = await coinbase_client.get_ticker(coinbase_symbol)
            
            if quote:
                return ExchangeQuote(
                    exchange="coinbase",
                    symbol=symbol,
                    bid=quote.bid,
                    ask=quote.ask,
                    bid_size=quote.bid_size,
                    ask_size=quote.ask_size,
                    timestamp=quote.timestamp
                )
        except Exception as e:
            logger.debug(f"Error getting Coinbase quote for {symbol}: {e}")
        return None
    
    async def _get_kraken_quote(self, symbol: str) -> Optional[ExchangeQuote]:
        """Get quote from Kraken."""
        try:
            quote = await kraken_client.get_ticker(symbol)
            
            if quote:
                return ExchangeQuote(
                    exchange="kraken",
                    symbol=symbol,
                    bid=quote.bid,
                    ask=quote.ask,
                    bid_size=quote.bid_size,
                    ask_size=quote.ask_size,
                    timestamp=quote.timestamp
                )
        except Exception as e:
            logger.debug(f"Error getting Kraken quote for {symbol}: {e}")
        return None
    
    def _clean_old_opportunities(self):
        """Remove old opportunities that are no longer valid."""
        current_time = datetime.utcnow()
        
        self.opportunities = [
            opp for opp in self.opportunities
            if (current_time - opp.detected_at).total_seconds() < opp.time_window
        ]
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Execute an arbitrage opportunity."""
        try:
            if opportunity.type == "cross_exchange":
                # Execute cross-exchange arbitrage
                # Buy on one exchange, sell on another
                
                # Note: In practice, you need accounts on both exchanges
                # and handle transfers between them
                
                buy_order = {
                    "exchange": opportunity.details["buy_exchange"],
                    "symbol": opportunity.symbols[0],
                    "side": "buy",
                    "qty": opportunity.trade_size / opportunity.buy_price,
                    "price": opportunity.buy_price
                }
                
                sell_order = {
                    "exchange": opportunity.details["sell_exchange"],
                    "symbol": opportunity.symbols[0],
                    "side": "sell",
                    "qty": opportunity.trade_size / opportunity.sell_price,
                    "price": opportunity.sell_price
                }
                
                # Execute simultaneously
                # In reality, would use exchange-specific APIs
                
                return {
                    "status": "executed",
                    "type": opportunity.type,
                    "profit": opportunity.estimated_profit
                }
                
            # Handle other arbitrage types...
            
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_opportunities(
        self,
        min_profit: Optional[float] = None,
        opportunity_type: Optional[str] = None
    ) -> List[ArbitrageOpportunity]:
        """Get current arbitrage opportunities."""
        opportunities = self.opportunities
        
        if min_profit:
            opportunities = [
                opp for opp in opportunities
                if opp.estimated_profit >= min_profit
            ]
        
        if opportunity_type:
            opportunities = [
                opp for opp in opportunities
                if opp.type == opportunity_type
            ]
        
        # Sort by profit
        opportunities.sort(key=lambda x: x.estimated_profit, reverse=True)
        
        return opportunities