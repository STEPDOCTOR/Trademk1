"""Position sizing service for intelligent trade allocation."""
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.db.questdb import get_questdb_pool
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PositionSizeRecommendation:
    """Position size recommendation based on various factors."""
    symbol: str
    base_size: float  # Base position size in dollars
    volatility_adjusted_size: float  # Adjusted for volatility
    risk_adjusted_size: float  # Final size after all adjustments
    shares: int  # Number of shares to buy
    confidence_multiplier: float  # Based on signal strength
    volatility: float  # Recent volatility (ATR)
    risk_score: float  # Overall risk score (0-1)
    reasoning: List[str]  # Explanation of adjustments


class PositionSizingService:
    """Service for calculating optimal position sizes."""
    
    def __init__(self):
        self.default_position_pct = 0.02  # 2% default position
        self.max_position_pct = 0.05  # 5% max position
        self.min_position_pct = 0.005  # 0.5% min position
        self.volatility_lookback_days = 14
        self.atr_multiplier = 2.0  # For stop loss calculation
        
    async def calculate_position_size(
        self,
        symbol: str,
        account_value: float,
        current_price: float,
        signal_confidence: float = 0.5,
        existing_positions: int = 0,
        max_positions: int = 20,
        risk_per_trade: float = 0.01  # 1% risk per trade
    ) -> PositionSizeRecommendation:
        """Calculate optimal position size for a symbol."""
        reasoning = []
        
        # Base position size
        base_size = account_value * self.default_position_pct
        reasoning.append(f"Base position: {self.default_position_pct:.1%} of portfolio")
        
        # Get volatility data
        volatility = await self._calculate_volatility(symbol, current_price)
        
        # Volatility adjustment
        volatility_adjusted = self._adjust_for_volatility(base_size, volatility, reasoning)
        
        # Portfolio concentration adjustment
        concentration_adjusted = self._adjust_for_concentration(
            volatility_adjusted, existing_positions, max_positions, reasoning
        )
        
        # Confidence adjustment
        confidence_adjusted = self._adjust_for_confidence(
            concentration_adjusted, signal_confidence, reasoning
        )
        
        # Risk-based position sizing (using ATR for stop loss)
        risk_adjusted = self._apply_risk_based_sizing(
            confidence_adjusted, account_value, current_price, 
            volatility, risk_per_trade, reasoning
        )
        
        # Apply limits
        final_size = self._apply_position_limits(
            risk_adjusted, account_value, reasoning
        )
        
        # Calculate shares
        shares = int(final_size / current_price)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(
            volatility, signal_confidence, existing_positions, max_positions
        )
        
        return PositionSizeRecommendation(
            symbol=symbol,
            base_size=base_size,
            volatility_adjusted_size=volatility_adjusted,
            risk_adjusted_size=final_size,
            shares=shares,
            confidence_multiplier=signal_confidence,
            volatility=volatility,
            risk_score=risk_score,
            reasoning=reasoning
        )
    
    async def _calculate_volatility(self, symbol: str, current_price: float) -> float:
        """Calculate Average True Range (ATR) as volatility measure."""
        try:
            # Get OHLC data for ATR calculation
            query = f"""
            SELECT 
                timestamp,
                first(price) as open,
                max(price) as high,
                min(price) as low,
                last(price) as close
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > dateadd('d', -{self.volatility_lookback_days}, now())
            SAMPLE BY 1h
            ORDER BY timestamp DESC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                
            if len(result) < 10:
                # Not enough data, use simple percentage estimate
                return current_price * 0.02  # Assume 2% volatility
            
            # Calculate True Range for each period
            true_ranges = []
            for i in range(1, len(result)):
                high = result[i]['high']
                low = result[i]['low']
                prev_close = result[i-1]['close']
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            # Average True Range
            atr = np.mean(true_ranges[-14:])  # 14-period ATR
            
            return atr
            
        except Exception as e:
            logger.error(f"Error calculating volatility for {symbol}: {e}")
            return current_price * 0.02  # Default 2% volatility
    
    def _adjust_for_volatility(self, base_size: float, volatility: float, reasoning: List[str]) -> float:
        """Adjust position size based on volatility."""
        # Higher volatility = smaller position
        # Assume average volatility is 2% of price
        avg_volatility_pct = 0.02
        current_volatility_pct = volatility / base_size if base_size > 0 else avg_volatility_pct
        
        volatility_factor = avg_volatility_pct / max(current_volatility_pct, 0.005)
        volatility_factor = np.clip(volatility_factor, 0.5, 2.0)  # Limit adjustment
        
        adjusted_size = base_size * volatility_factor
        
        if volatility_factor < 1:
            reasoning.append(f"Reduced by {(1-volatility_factor)*100:.0f}% due to high volatility")
        elif volatility_factor > 1:
            reasoning.append(f"Increased by {(volatility_factor-1)*100:.0f}% due to low volatility")
        
        return adjusted_size
    
    def _adjust_for_concentration(self, size: float, existing_positions: int, 
                                 max_positions: int, reasoning: List[str]) -> float:
        """Adjust for portfolio concentration."""
        if existing_positions >= max_positions * 0.8:  # 80% full
            # Reduce size when nearing max positions
            concentration_factor = 0.7
            reasoning.append("Reduced by 30% due to high position count")
        elif existing_positions < max_positions * 0.3:  # Less than 30% full
            # Can be more aggressive with fewer positions
            concentration_factor = 1.2
            reasoning.append("Increased by 20% due to low position count")
        else:
            concentration_factor = 1.0
        
        return size * concentration_factor
    
    def _adjust_for_confidence(self, size: float, confidence: float, reasoning: List[str]) -> float:
        """Adjust size based on signal confidence."""
        # Scale between 0.5x and 1.5x based on confidence (0-1)
        confidence_factor = 0.5 + confidence
        adjusted_size = size * confidence_factor
        
        if confidence > 0.7:
            reasoning.append(f"Increased by {(confidence_factor-1)*100:.0f}% due to high confidence")
        elif confidence < 0.3:
            reasoning.append(f"Reduced by {(1-confidence_factor)*100:.0f}% due to low confidence")
        
        return adjusted_size
    
    def _apply_risk_based_sizing(self, size: float, account_value: float,
                                current_price: float, atr: float, 
                                risk_per_trade: float, reasoning: List[str]) -> float:
        """Apply Kelly Criterion-inspired risk-based sizing."""
        # Calculate stop loss based on ATR
        stop_loss_price = current_price - (atr * self.atr_multiplier)
        risk_per_share = current_price - stop_loss_price
        
        if risk_per_share <= 0:
            return size  # Can't calculate, use existing size
        
        # Maximum shares based on risk
        max_risk_amount = account_value * risk_per_trade
        max_shares_by_risk = max_risk_amount / risk_per_share
        max_size_by_risk = max_shares_by_risk * current_price
        
        # Use the smaller of the two
        if max_size_by_risk < size:
            reasoning.append(f"Limited to {risk_per_trade:.1%} risk per trade")
            return max_size_by_risk
        
        return size
    
    def _apply_position_limits(self, size: float, account_value: float, 
                              reasoning: List[str]) -> float:
        """Apply minimum and maximum position limits."""
        max_size = account_value * self.max_position_pct
        min_size = account_value * self.min_position_pct
        
        if size > max_size:
            reasoning.append(f"Capped at maximum {self.max_position_pct:.1%} position")
            return max_size
        elif size < min_size:
            reasoning.append(f"Increased to minimum {self.min_position_pct:.1%} position")
            return min_size
        
        return size
    
    def _calculate_risk_score(self, volatility: float, confidence: float,
                             existing_positions: int, max_positions: int) -> float:
        """Calculate overall risk score (0-1, higher is riskier)."""
        # Volatility component (assume 5% is very high)
        volatility_score = min(volatility / 0.05, 1.0)
        
        # Confidence component (inverted - low confidence is risky)
        confidence_score = 1 - confidence
        
        # Concentration component
        concentration_score = existing_positions / max_positions
        
        # Weighted average
        risk_score = (
            volatility_score * 0.4 +
            confidence_score * 0.3 +
            concentration_score * 0.3
        )
        
        return np.clip(risk_score, 0, 1)
    
    def scale_in_strategy(self, initial_size: float, levels: int = 3) -> List[float]:
        """Generate a scale-in strategy for gradual position building."""
        if levels == 1:
            return [initial_size]
        
        # Pyramid scaling: 50%, 30%, 20%
        scales = [0.5, 0.3, 0.2][:levels]
        return [initial_size * scale for scale in scales]
    
    def scale_out_strategy(self, position_size: float, profit_pct: float) -> float:
        """Determine how much to sell based on profit level."""
        if profit_pct >= 0.20:  # 20%+ profit
            return position_size * 0.5  # Sell half
        elif profit_pct >= 0.10:  # 10%+ profit
            return position_size * 0.33  # Sell third
        elif profit_pct >= 0.05:  # 5%+ profit
            return position_size * 0.25  # Sell quarter
        else:
            return 0  # Hold


# Global instance
position_sizing = PositionSizingService()