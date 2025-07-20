"""Technical indicators calculation service for advanced trading strategies."""
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass

from app.db.questdb import get_questdb_pool
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TechnicalSignals:
    """Container for technical indicator signals."""
    symbol: str
    timestamp: datetime
    # Price data
    current_price: float
    price_change_pct: float
    # RSI
    rsi: float
    rsi_signal: str  # "oversold", "overbought", "neutral"
    # MACD
    macd: float
    macd_signal: float
    macd_histogram: float
    macd_cross: str  # "bullish", "bearish", "none"
    # Volume
    volume_ratio: float  # Current vs average
    volume_trend: str  # "increasing", "decreasing", "stable"
    # Bollinger Bands
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: str  # "above", "below", "inside"
    # Combined signal
    overall_signal: str  # "strong_buy", "buy", "neutral", "sell", "strong_sell"
    confidence: float  # 0-1 confidence score


class TechnicalIndicatorService:
    """Service for calculating technical indicators and generating signals."""
    
    def __init__(self):
        self.cache: Dict[str, TechnicalSignals] = {}
        self.cache_ttl = 30  # Cache for 30 seconds
        
    async def get_technical_signals(self, symbol: str, force_refresh: bool = False) -> Optional[TechnicalSignals]:
        """Get technical signals for a symbol."""
        # Check cache
        if not force_refresh and symbol in self.cache:
            cached = self.cache[symbol]
            if (datetime.utcnow() - cached.timestamp).total_seconds() < self.cache_ttl:
                return cached
        
        try:
            # Get price history
            prices = await self._get_price_history(symbol, hours=48)
            if len(prices) < 30:
                logger.warning(f"Insufficient price data for {symbol}: {len(prices)} points")
                return None
            
            # Get volume data
            volumes = await self._get_volume_history(symbol, hours=48)
            
            # Calculate indicators
            current_price = prices[-1]
            price_change_pct = ((current_price - prices[-24]) / prices[-24]) * 100 if len(prices) > 24 else 0
            
            # RSI
            rsi = self._calculate_rsi(prices, period=14)
            rsi_signal = self._interpret_rsi(rsi)
            
            # MACD
            macd, signal, histogram = self._calculate_macd(prices)
            macd_cross = self._detect_macd_cross(macd, signal)
            
            # Volume analysis
            volume_ratio, volume_trend = self._analyze_volume(volumes)
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices, period=20)
            bb_position = self._get_bb_position(current_price, bb_upper, bb_lower)
            
            # Generate overall signal
            overall_signal, confidence = self._generate_overall_signal(
                rsi_signal, macd_cross, volume_trend, bb_position, price_change_pct
            )
            
            # Create signals object
            signals = TechnicalSignals(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                current_price=current_price,
                price_change_pct=price_change_pct,
                rsi=rsi,
                rsi_signal=rsi_signal,
                macd=macd[-1] if macd else 0,
                macd_signal=signal[-1] if signal else 0,
                macd_histogram=histogram[-1] if histogram else 0,
                macd_cross=macd_cross,
                volume_ratio=volume_ratio,
                volume_trend=volume_trend,
                bb_upper=bb_upper,
                bb_middle=bb_middle,
                bb_lower=bb_lower,
                bb_position=bb_position,
                overall_signal=overall_signal,
                confidence=confidence
            )
            
            # Cache result
            self.cache[symbol] = signals
            
            return signals
            
        except Exception as e:
            logger.error(f"Error calculating technical signals for {symbol}: {e}")
            return None
    
    async def scan_for_opportunities(self, symbols: List[str]) -> List[TechnicalSignals]:
        """Scan multiple symbols for trading opportunities."""
        tasks = [self.get_technical_signals(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        opportunities = []
        for result in results:
            if isinstance(result, TechnicalSignals) and result.overall_signal in ["strong_buy", "buy"]:
                opportunities.append(result)
        
        # Sort by confidence
        opportunities.sort(key=lambda x: x.confidence, reverse=True)
        
        return opportunities
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0  # Neutral
        
        # Calculate price changes
        deltas = np.diff(prices)
        gains = deltas.copy()
        losses = deltas.copy()
        gains[gains < 0] = 0
        losses[losses > 0] = 0
        losses = abs(losses)
        
        # Calculate average gains and losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _interpret_rsi(self, rsi: float) -> str:
        """Interpret RSI value."""
        if rsi < 30:
            return "oversold"
        elif rsi > 70:
            return "overbought"
        else:
            return "neutral"
    
    def _calculate_macd(self, prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
        """Calculate MACD, Signal line, and Histogram."""
        if len(prices) < slow:
            return [], [], []
        
        # Calculate EMAs
        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)
        
        # MACD line
        macd = [f - s for f, s in zip(ema_fast, ema_slow)]
        
        # Signal line (EMA of MACD)
        signal_line = self._calculate_ema(macd, signal)
        
        # Histogram
        histogram = [m - s for m, s in zip(macd[-len(signal_line):], signal_line)]
        
        return macd, signal_line, histogram
    
    def _calculate_ema(self, data: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema = [sum(data[:period]) / period]  # SMA for first value
        
        for price in data[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        
        return ema
    
    def _detect_macd_cross(self, macd: List[float], signal: List[float]) -> str:
        """Detect MACD crossover signals."""
        if len(macd) < 2 or len(signal) < 2:
            return "none"
        
        # Check last two points for crossover
        prev_diff = macd[-2] - signal[-2]
        curr_diff = macd[-1] - signal[-1]
        
        if prev_diff <= 0 and curr_diff > 0:
            return "bullish"  # MACD crossed above signal
        elif prev_diff >= 0 and curr_diff < 0:
            return "bearish"  # MACD crossed below signal
        else:
            return "none"
    
    def _analyze_volume(self, volumes: List[float]) -> Tuple[float, str]:
        """Analyze volume patterns."""
        if len(volumes) < 20:
            return 1.0, "stable"
        
        # Current vs average volume
        current_volume = volumes[-1]
        avg_volume = np.mean(volumes[-20:])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Volume trend
        recent_avg = np.mean(volumes[-5:])
        older_avg = np.mean(volumes[-20:-5])
        
        if recent_avg > older_avg * 1.2:
            trend = "increasing"
        elif recent_avg < older_avg * 0.8:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return volume_ratio, trend
    
    def _calculate_bollinger_bands(self, prices: List[float], period: int = 20, std_dev: int = 2) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return upper, sma, lower
    
    def _get_bb_position(self, price: float, upper: float, lower: float) -> str:
        """Get position relative to Bollinger Bands."""
        if price > upper:
            return "above"
        elif price < lower:
            return "below"
        else:
            return "inside"
    
    def _generate_overall_signal(self, rsi_signal: str, macd_cross: str, 
                                volume_trend: str, bb_position: str, 
                                price_change_pct: float) -> Tuple[str, float]:
        """Generate overall trading signal and confidence score."""
        score = 0
        signals = 0
        
        # RSI signal
        if rsi_signal == "oversold":
            score += 2
            signals += 1
        elif rsi_signal == "overbought":
            score -= 2
            signals += 1
        
        # MACD signal
        if macd_cross == "bullish":
            score += 2
            signals += 1
        elif macd_cross == "bearish":
            score -= 2
            signals += 1
        
        # Volume signal
        if volume_trend == "increasing":
            score += 1 if score > 0 else -1  # Amplifies existing signal
            signals += 0.5
        
        # Bollinger Bands
        if bb_position == "below":
            score += 1
            signals += 0.5
        elif bb_position == "above":
            score -= 1
            signals += 0.5
        
        # Price momentum
        if abs(price_change_pct) > 5:
            if price_change_pct > 0:
                score += 1
            else:
                score -= 1
            signals += 0.5
        
        # Calculate confidence (0-1)
        confidence = min(abs(score) / 6, 1.0) * (signals / 4)
        
        # Determine signal
        if score >= 3:
            signal = "strong_buy"
        elif score >= 1:
            signal = "buy"
        elif score <= -3:
            signal = "strong_sell"
        elif score <= -1:
            signal = "sell"
        else:
            signal = "neutral"
        
        return signal, confidence
    
    async def _get_price_history(self, symbol: str, hours: int = 24) -> List[float]:
        """Get price history from QuestDB."""
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
                return [row['price'] for row in result]
        except Exception as e:
            logger.error(f"Error getting price history for {symbol}: {e}")
            return []
    
    async def _get_volume_history(self, symbol: str, hours: int = 24) -> List[float]:
        """Get volume history from QuestDB."""
        try:
            query = f"""
            SELECT volume 
            FROM market_ticks 
            WHERE symbol = '{symbol}' 
            AND timestamp > dateadd('h', -{hours}, now())
            ORDER BY timestamp ASC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                return [row['volume'] for row in result if row['volume'] is not None]
        except Exception as e:
            logger.error(f"Error getting volume history for {symbol}: {e}")
            return []


# Global instance
technical_indicators = TechnicalIndicatorService()