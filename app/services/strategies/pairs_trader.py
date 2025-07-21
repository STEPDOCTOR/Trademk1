"""Pairs trading strategy implementation."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from statsmodels.tsa.stattools import coint, adfuller
import asyncio

from app.db.questdb import get_questdb_pool
from app.db.optimized_postgres import optimized_db
from app.models.position import Position
from app.services.trading.execution_engine import ExecutionEngine
from app.monitoring.logger import get_logger
from sqlalchemy import select

logger = get_logger(__name__)


@dataclass
class PairStats:
    """Statistics for a trading pair."""
    symbol1: str
    symbol2: str
    correlation: float
    cointegration_pvalue: float
    half_life: float  # Mean reversion time
    spread_mean: float
    spread_std: float
    current_spread: float
    z_score: float
    hedge_ratio: float
    is_stationary: bool
    last_updated: datetime


@dataclass
class PairSignal:
    """Trading signal for a pair."""
    pair: Tuple[str, str]
    action: str  # "open_long", "open_short", "close", "reverse"
    symbol1_side: str  # "buy" or "sell"
    symbol1_qty: int
    symbol2_side: str  # "buy" or "sell"
    symbol2_qty: int
    z_score: float
    expected_profit: float
    confidence: float
    reason: str


class PairsTrader:
    """Pairs trading strategy implementation."""
    
    def __init__(self, execution_engine: ExecutionEngine):
        self.execution_engine = execution_engine
        self.lookback_days = 60  # Days of history for analysis
        self.min_correlation = 0.7  # Minimum correlation
        self.max_pvalue = 0.05  # Max p-value for cointegration
        self.entry_z_score = 2.0  # Z-score to enter position
        self.exit_z_score = 0.5  # Z-score to exit
        self.stop_loss_z_score = 3.0  # Stop loss threshold
        self.position_size_pct = 0.05  # 5% of portfolio per pair
        self.pairs_cache: Dict[Tuple[str, str], PairStats] = {}
        self.active_pairs: Dict[Tuple[str, str], Dict] = {}
        
    async def find_cointegrated_pairs(
        self,
        symbols: List[str],
        sector_filter: bool = True
    ) -> List[PairStats]:
        """Find cointegrated pairs from a list of symbols."""
        pairs_stats = []
        
        # Get price data for all symbols
        price_data = await self._get_price_data_bulk(symbols)
        
        if not price_data:
            return pairs_stats
        
        # Test all combinations
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                symbol1, symbol2 = symbols[i], symbols[j]
                
                # Skip if same sector filter is on and they're different sectors
                if sector_filter and not self._same_sector(symbol1, symbol2):
                    continue
                
                try:
                    # Get price series
                    prices1 = price_data.get(symbol1, [])
                    prices2 = price_data.get(symbol2, [])
                    
                    if len(prices1) < 50 or len(prices2) < 50:
                        continue
                    
                    # Align prices
                    prices1 = np.array(prices1[-min(len(prices1), len(prices2)):])
                    prices2 = np.array(prices2[-min(len(prices1), len(prices2)):])
                    
                    # Calculate correlation
                    correlation = np.corrcoef(prices1, prices2)[0, 1]
                    
                    if correlation < self.min_correlation:
                        continue
                    
                    # Test for cointegration
                    score, pvalue, _ = coint(prices1, prices2)
                    
                    if pvalue > self.max_pvalue:
                        continue
                    
                    # Calculate hedge ratio (beta)
                    hedge_ratio = self._calculate_hedge_ratio(prices1, prices2)
                    
                    # Calculate spread
                    spread = prices1 - hedge_ratio * prices2
                    
                    # Test spread for stationarity
                    adf_result = adfuller(spread)
                    is_stationary = adf_result[1] < 0.05
                    
                    if not is_stationary:
                        continue
                    
                    # Calculate spread statistics
                    spread_mean = np.mean(spread)
                    spread_std = np.std(spread)
                    current_spread = spread[-1]
                    z_score = (current_spread - spread_mean) / spread_std
                    
                    # Calculate half-life (mean reversion time)
                    half_life = self._calculate_half_life(spread)
                    
                    pair_stat = PairStats(
                        symbol1=symbol1,
                        symbol2=symbol2,
                        correlation=correlation,
                        cointegration_pvalue=pvalue,
                        half_life=half_life,
                        spread_mean=spread_mean,
                        spread_std=spread_std,
                        current_spread=current_spread,
                        z_score=z_score,
                        hedge_ratio=hedge_ratio,
                        is_stationary=is_stationary,
                        last_updated=datetime.utcnow()
                    )
                    
                    pairs_stats.append(pair_stat)
                    self.pairs_cache[(symbol1, symbol2)] = pair_stat
                    
                except Exception as e:
                    logger.error(f"Error analyzing pair {symbol1}-{symbol2}: {e}")
                    continue
        
        # Sort by cointegration strength
        pairs_stats.sort(key=lambda x: x.cointegration_pvalue)
        
        return pairs_stats
    
    async def generate_signals(
        self,
        pairs: Optional[List[Tuple[str, str]]] = None
    ) -> List[PairSignal]:
        """Generate trading signals for pairs."""
        signals = []
        
        # Use cached pairs if none provided
        if not pairs:
            pairs = list(self.pairs_cache.keys())
        
        for pair in pairs:
            try:
                # Update pair statistics
                pair_stats = await self._update_pair_stats(pair)
                
                if not pair_stats or not pair_stats.is_stationary:
                    continue
                
                # Check if we have an existing position
                has_position = pair in self.active_pairs
                
                if has_position:
                    position_info = self.active_pairs[pair]
                    position_type = position_info.get('type')  # 'long' or 'short'
                    
                    # Check exit conditions
                    if position_type == 'long' and pair_stats.z_score <= self.exit_z_score:
                        # Close long position
                        signal = await self._create_close_signal(pair, pair_stats, 'long')
                        if signal:
                            signals.append(signal)
                            
                    elif position_type == 'short' and pair_stats.z_score >= -self.exit_z_score:
                        # Close short position
                        signal = await self._create_close_signal(pair, pair_stats, 'short')
                        if signal:
                            signals.append(signal)
                            
                    # Check stop loss
                    elif abs(pair_stats.z_score) > self.stop_loss_z_score:
                        signal = await self._create_close_signal(pair, pair_stats, position_type, is_stop_loss=True)
                        if signal:
                            signals.append(signal)
                            
                else:
                    # Check entry conditions
                    if pair_stats.z_score >= self.entry_z_score:
                        # Open short position (spread is too high, expect reversion)
                        signal = await self._create_entry_signal(pair, pair_stats, 'short')
                        if signal:
                            signals.append(signal)
                            
                    elif pair_stats.z_score <= -self.entry_z_score:
                        # Open long position (spread is too low, expect reversion)
                        signal = await self._create_entry_signal(pair, pair_stats, 'long')
                        if signal:
                            signals.append(signal)
                
            except Exception as e:
                logger.error(f"Error generating signals for pair {pair}: {e}")
                continue
        
        return signals
    
    async def execute_pair_signal(self, signal: PairSignal) -> Dict[str, Any]:
        """Execute a pairs trading signal."""
        try:
            # Execute first leg
            order1 = await self.execution_engine._process_signal({
                "symbol": signal.pair[0],
                "side": signal.symbol1_side,
                "qty": signal.symbol1_qty,
                "reason": f"[PAIRS] {signal.reason} - Leg 1"
            })
            
            # Execute second leg
            order2 = await self.execution_engine._process_signal({
                "symbol": signal.pair[1],
                "side": signal.symbol2_side,
                "qty": signal.symbol2_qty,
                "reason": f"[PAIRS] {signal.reason} - Leg 2"
            })
            
            # Update active pairs tracking
            if signal.action.startswith("open"):
                self.active_pairs[signal.pair] = {
                    "type": signal.action.split("_")[1],  # 'long' or 'short'
                    "entry_z_score": signal.z_score,
                    "entry_time": datetime.utcnow(),
                    "symbol1_qty": signal.symbol1_qty,
                    "symbol2_qty": signal.symbol2_qty
                }
            elif signal.action == "close":
                self.active_pairs.pop(signal.pair, None)
            
            return {
                "status": "executed",
                "pair": signal.pair,
                "action": signal.action,
                "orders": [order1, order2]
            }
            
        except Exception as e:
            logger.error(f"Error executing pair signal: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _get_price_data_bulk(self, symbols: List[str]) -> Dict[str, List[float]]:
        """Get historical price data for multiple symbols."""
        price_data = {}
        
        for symbol in symbols:
            try:
                query = f"""
                SELECT price
                FROM market_ticks
                WHERE symbol = '{symbol}'
                AND timestamp > dateadd('d', -{self.lookback_days}, now())
                ORDER BY timestamp ASC
                """
                
                async with get_questdb_pool() as conn:
                    result = await conn.fetch(query)
                    
                if result:
                    prices = [row['price'] for row in result]
                    price_data[symbol] = prices
                    
            except Exception as e:
                logger.error(f"Error getting price data for {symbol}: {e}")
                
        return price_data
    
    async def _update_pair_stats(self, pair: Tuple[str, str]) -> Optional[PairStats]:
        """Update statistics for a pair."""
        symbol1, symbol2 = pair
        
        # Get recent prices
        prices1_data = await self._get_price_data_bulk([symbol1])
        prices2_data = await self._get_price_data_bulk([symbol2])
        
        if not prices1_data or not prices2_data:
            return None
        
        prices1 = np.array(prices1_data[symbol1])
        prices2 = np.array(prices2_data[symbol2])
        
        if len(prices1) < 20 or len(prices2) < 20:
            return None
        
        # Recalculate spread with existing hedge ratio
        cached_stats = self.pairs_cache.get(pair)
        if cached_stats:
            hedge_ratio = cached_stats.hedge_ratio
        else:
            hedge_ratio = self._calculate_hedge_ratio(prices1, prices2)
        
        spread = prices1 - hedge_ratio * prices2
        spread_mean = np.mean(spread)
        spread_std = np.std(spread)
        current_spread = spread[-1]
        z_score = (current_spread - spread_mean) / spread_std
        
        # Update cache
        if cached_stats:
            cached_stats.current_spread = current_spread
            cached_stats.z_score = z_score
            cached_stats.last_updated = datetime.utcnow()
            return cached_stats
        
        return None
    
    def _calculate_hedge_ratio(self, prices1: np.ndarray, prices2: np.ndarray) -> float:
        """Calculate optimal hedge ratio using OLS."""
        # Simple linear regression
        x = prices2.reshape(-1, 1)
        y = prices1.reshape(-1, 1)
        
        # Add intercept
        x = np.column_stack([np.ones(len(x)), x])
        
        # OLS formula: (X'X)^-1 X'y
        beta = np.linalg.inv(x.T @ x) @ x.T @ y
        
        return float(beta[1][0])  # Slope is the hedge ratio
    
    def _calculate_half_life(self, spread: np.ndarray) -> float:
        """Calculate half-life of mean reversion."""
        # Use Ornstein-Uhlenbeck process
        spread_lag = spread[:-1]
        spread_diff = spread[1:] - spread_lag
        
        # Regression
        x = spread_lag.reshape(-1, 1)
        y = spread_diff.reshape(-1, 1)
        
        x = np.column_stack([np.ones(len(x)), x])
        beta = np.linalg.inv(x.T @ x) @ x.T @ y
        
        # Half-life = -log(2) / beta
        half_life = -np.log(2) / beta[1][0] if beta[1][0] < 0 else 30
        
        return min(max(half_life, 1), 30)  # Clamp between 1 and 30 days
    
    def _same_sector(self, symbol1: str, symbol2: str) -> bool:
        """Check if two symbols are in the same sector."""
        # Simplified sector mapping
        tech_stocks = ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC"]
        finance_stocks = ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA"]
        retail_stocks = ["AMZN", "WMT", "TGT", "HD", "LOW", "COST"]
        
        for sector in [tech_stocks, finance_stocks, retail_stocks]:
            if symbol1 in sector and symbol2 in sector:
                return True
        
        return False
    
    async def _create_entry_signal(
        self,
        pair: Tuple[str, str],
        stats: PairStats,
        position_type: str
    ) -> Optional[PairSignal]:
        """Create entry signal for a pair."""
        # Get account info
        account_info = await self.execution_engine.alpaca_client.get_account()
        portfolio_value = float(account_info["portfolio_value"])
        
        # Calculate position sizes
        position_value = portfolio_value * self.position_size_pct
        
        # Get current prices
        price1 = await self._get_current_price(pair[0])
        price2 = await self._get_current_price(pair[1])
        
        if not price1 or not price2:
            return None
        
        # Calculate quantities
        # For pairs trading, we want dollar-neutral positions
        symbol1_value = position_value / 2
        symbol2_value = position_value / 2
        
        symbol1_qty = int(symbol1_value / price1)
        symbol2_qty = int(symbol2_value / price2 / stats.hedge_ratio)
        
        if symbol1_qty == 0 or symbol2_qty == 0:
            return None
        
        # Determine sides based on position type
        if position_type == "long":
            # Long the spread: buy symbol1, sell symbol2
            symbol1_side = "buy"
            symbol2_side = "sell"
        else:  # short
            # Short the spread: sell symbol1, buy symbol2
            symbol1_side = "sell"
            symbol2_side = "buy"
        
        # Calculate expected profit
        expected_move = abs(stats.z_score - 0) * stats.spread_std
        expected_profit = expected_move * symbol1_qty
        
        return PairSignal(
            pair=pair,
            action=f"open_{position_type}",
            symbol1_side=symbol1_side,
            symbol1_qty=symbol1_qty,
            symbol2_side=symbol2_side,
            symbol2_qty=symbol2_qty,
            z_score=stats.z_score,
            expected_profit=expected_profit,
            confidence=min(abs(stats.z_score) / 3, 1.0),  # Higher z-score = higher confidence
            reason=f"Z-score {stats.z_score:.2f}, half-life {stats.half_life:.1f} days"
        )
    
    async def _create_close_signal(
        self,
        pair: Tuple[str, str],
        stats: PairStats,
        position_type: str,
        is_stop_loss: bool = False
    ) -> Optional[PairSignal]:
        """Create close signal for a pair."""
        position_info = self.active_pairs.get(pair)
        if not position_info:
            return None
        
        # Reverse the original position
        if position_type == "long":
            symbol1_side = "sell"
            symbol2_side = "buy"
        else:
            symbol1_side = "buy"
            symbol2_side = "sell"
        
        reason = "Stop loss" if is_stop_loss else f"Target reached (z-score: {stats.z_score:.2f})"
        
        return PairSignal(
            pair=pair,
            action="close",
            symbol1_side=symbol1_side,
            symbol1_qty=position_info["symbol1_qty"],
            symbol2_side=symbol2_side,
            symbol2_qty=position_info["symbol2_qty"],
            z_score=stats.z_score,
            expected_profit=0,  # Will be calculated from actual P&L
            confidence=1.0,
            reason=reason
        )
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            quote = await self.execution_engine.alpaca_client.get_latest_trade(symbol)
            return quote["price"]
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    async def get_active_pairs_status(self) -> List[Dict[str, Any]]:
        """Get status of all active pair positions."""
        status_list = []
        
        for pair, info in self.active_pairs.items():
            stats = self.pairs_cache.get(pair)
            if stats:
                # Calculate current P&L
                entry_z = info["entry_z_score"]
                current_z = stats.z_score
                z_move = entry_z - current_z if info["type"] == "short" else current_z - entry_z
                
                status_list.append({
                    "pair": pair,
                    "type": info["type"],
                    "entry_z_score": entry_z,
                    "current_z_score": current_z,
                    "z_score_move": z_move,
                    "time_held": (datetime.utcnow() - info["entry_time"]).total_seconds() / 3600,
                    "half_life": stats.half_life
                })
        
        return status_list