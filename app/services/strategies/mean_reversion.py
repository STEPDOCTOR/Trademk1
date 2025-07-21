"""Mean reversion trading strategy."""
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from app.services.strategies.base import Strategy, Signal
from app.db.questdb import get_questdb_pool
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MeanReversionSignal:
    """Mean reversion trading signal."""
    symbol: str
    current_price: float
    mean_price: float
    std_dev: float
    z_score: float
    bb_upper: float
    bb_lower: float
    rsi: float
    action: str  # "buy", "sell", "close"
    confidence: float
    expected_reversion: float
    time_horizon_hours: int


class MeanReversionStrategy(Strategy):
    """Mean reversion trading strategy using Bollinger Bands and RSI."""
    
    def __init__(
        self,
        symbols: List[str],
        allocation: float = 0.25,
        lookback_period: int = 20,
        bb_std_dev: float = 2.0,
        rsi_period: int = 14,
        entry_z_score: float = 2.0,
        exit_z_score: float = 0.5,
        max_holding_hours: int = 72
    ):
        super().__init__("mean_reversion", symbols, allocation)
        self.lookback_period = lookback_period
        self.bb_std_dev = bb_std_dev
        self.rsi_period = rsi_period
        self.entry_z_score = entry_z_score
        self.exit_z_score = exit_z_score
        self.max_holding_hours = max_holding_hours
        self.positions: Dict[str, Dict[str, Any]] = {}
        
    async def initialize(self):
        """Initialize the strategy."""
        logger.info(f"Initializing mean reversion strategy for {len(self.symbols)} symbols")
        
    async def generate_signals(self, market_data: Dict[str, Any]) -> List[Signal]:
        """Generate trading signals based on mean reversion."""
        signals = []
        
        for symbol in self.symbols:
            try:
                # Analyze mean reversion opportunity
                mr_signal = await self._analyze_mean_reversion(symbol)
                
                if mr_signal:
                    # Check if we have a position
                    has_position = symbol in self.positions
                    
                    if mr_signal.action == "buy" and not has_position:
                        # Enter long position on oversold condition
                        signal = Signal(
                            symbol=symbol,
                            action="buy",
                            strength=mr_signal.confidence,
                            reason=f"Mean reversion buy: Z-score {mr_signal.z_score:.2f}, RSI {mr_signal.rsi:.0f}"
                        )
                        signals.append(signal)
                        
                    elif mr_signal.action == "sell" and not has_position:
                        # Enter short position on overbought condition
                        signal = Signal(
                            symbol=symbol,
                            action="sell",
                            strength=mr_signal.confidence,
                            reason=f"Mean reversion sell: Z-score {mr_signal.z_score:.2f}, RSI {mr_signal.rsi:.0f}"
                        )
                        signals.append(signal)
                        
                    elif mr_signal.action == "close" and has_position:
                        # Close position when reverting to mean
                        position = self.positions[symbol]
                        opposite_action = "sell" if position['side'] == "buy" else "buy"
                        
                        signal = Signal(
                            symbol=symbol,
                            action=opposite_action,
                            strength=mr_signal.confidence,
                            reason=f"Mean reversion close: Z-score {mr_signal.z_score:.2f} approaching mean"
                        )
                        signals.append(signal)
                        
            except Exception as e:
                logger.error(f"Error generating mean reversion signal for {symbol}: {e}")
                
        return signals
        
    async def _analyze_mean_reversion(self, symbol: str) -> Optional[MeanReversionSignal]:
        """Analyze mean reversion opportunity for a symbol."""
        try:
            # Get price data
            prices = await self._get_price_data(symbol, hours=24 * 5)  # 5 days
            
            if len(prices) < self.lookback_period:
                return None
                
            # Calculate indicators
            current_price = prices[-1]
            
            # Simple Moving Average
            sma = np.mean(prices[-self.lookback_period:])
            
            # Standard Deviation
            std_dev = np.std(prices[-self.lookback_period:])
            
            # Bollinger Bands
            bb_upper = sma + (self.bb_std_dev * std_dev)
            bb_lower = sma - (self.bb_std_dev * std_dev)
            
            # Z-score
            z_score = (current_price - sma) / std_dev if std_dev > 0 else 0
            
            # RSI
            rsi = self._calculate_rsi(prices, self.rsi_period)
            
            # Mean reversion expectation
            expected_reversion = sma - current_price
            expected_reversion_pct = expected_reversion / current_price
            
            # Check entry conditions
            if abs(z_score) >= self.entry_z_score:
                if z_score < -self.entry_z_score and rsi < 30:
                    # Oversold - potential buy
                    confidence = self._calculate_confidence(z_score, rsi, "oversold")
                    
                    return MeanReversionSignal(
                        symbol=symbol,
                        current_price=current_price,
                        mean_price=sma,
                        std_dev=std_dev,
                        z_score=z_score,
                        bb_upper=bb_upper,
                        bb_lower=bb_lower,
                        rsi=rsi,
                        action="buy",
                        confidence=confidence,
                        expected_reversion=expected_reversion_pct,
                        time_horizon_hours=self._estimate_reversion_time(z_score)
                    )
                    
                elif z_score > self.entry_z_score and rsi > 70:
                    # Overbought - potential sell
                    confidence = self._calculate_confidence(z_score, rsi, "overbought")
                    
                    return MeanReversionSignal(
                        symbol=symbol,
                        current_price=current_price,
                        mean_price=sma,
                        std_dev=std_dev,
                        z_score=z_score,
                        bb_upper=bb_upper,
                        bb_lower=bb_lower,
                        rsi=rsi,
                        action="sell",
                        confidence=confidence,
                        expected_reversion=expected_reversion_pct,
                        time_horizon_hours=self._estimate_reversion_time(z_score)
                    )
                    
            # Check exit conditions for existing positions
            if symbol in self.positions and abs(z_score) <= self.exit_z_score:
                # Price returning to mean - close position
                confidence = 0.9  # High confidence for exit
                
                return MeanReversionSignal(
                    symbol=symbol,
                    current_price=current_price,
                    mean_price=sma,
                    std_dev=std_dev,
                    z_score=z_score,
                    bb_upper=bb_upper,
                    bb_lower=bb_lower,
                    rsi=rsi,
                    action="close",
                    confidence=confidence,
                    expected_reversion=0,
                    time_horizon_hours=0
                )
                
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing mean reversion for {symbol}: {e}")
            return None
            
    async def _get_price_data(self, symbol: str, hours: int) -> List[float]:
        """Get historical price data."""
        try:
            query = f"""
            SELECT price
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > dateadd('h', -{hours}, now())
            ORDER BY timestamp ASC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                
            return [row['price'] for row in result] if result else []
            
        except Exception as e:
            logger.error(f"Error getting price data for {symbol}: {e}")
            return []
            
    def _calculate_rsi(self, prices: List[float], period: int) -> float:
        """Calculate RSI indicator."""
        if len(prices) < period + 1:
            return 50  # Neutral
            
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
                
        # Calculate average gains and losses
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
        
    def _calculate_confidence(self, z_score: float, rsi: float, condition: str) -> float:
        """Calculate confidence score for the signal."""
        # Base confidence from z-score
        z_confidence = min(abs(z_score) / 3, 1.0)
        
        # RSI confidence
        if condition == "oversold":
            rsi_confidence = (30 - rsi) / 30 if rsi < 30 else 0
        else:  # overbought
            rsi_confidence = (rsi - 70) / 30 if rsi > 70 else 0
            
        # Combine confidences
        confidence = (z_confidence + rsi_confidence) / 2
        
        return min(max(confidence, 0.3), 0.9)
        
    def _estimate_reversion_time(self, z_score: float) -> int:
        """Estimate time for mean reversion in hours."""
        # Simple estimation based on z-score magnitude
        base_hours = 24
        z_factor = abs(z_score) / self.entry_z_score
        
        return int(base_hours * z_factor)
        
    async def update_positions(self, positions: List[Dict[str, Any]]):
        """Update current positions."""
        self.positions = {
            pos['symbol']: pos for pos in positions
            if pos['symbol'] in self.symbols
        }
        
        # Check for positions held too long
        current_time = datetime.utcnow()
        for symbol, pos in self.positions.items():
            if 'entry_time' in pos:
                hold_time = (current_time - pos['entry_time']).total_seconds() / 3600
                if hold_time > self.max_holding_hours:
                    logger.warning(f"Position {symbol} held for {hold_time:.1f} hours, consider closing")
                    
    def get_strategy_params(self) -> Dict[str, Any]:
        """Get strategy parameters."""
        return {
            "lookback_period": self.lookback_period,
            "bb_std_dev": self.bb_std_dev,
            "rsi_period": self.rsi_period,
            "entry_z_score": self.entry_z_score,
            "exit_z_score": self.exit_z_score,
            "max_holding_hours": self.max_holding_hours,
            "active_positions": len(self.positions)
        }
        
    async def analyze_performance(self, lookback_days: int = 30) -> Dict[str, Any]:
        """Analyze strategy performance."""
        # Would implement backtesting here
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0
        }