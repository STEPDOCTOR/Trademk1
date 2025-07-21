"""Machine learning based trading strategy."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.services.strategies.base import Strategy, Signal
from app.services.ml import price_predictor
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


class MLStrategy(Strategy):
    """Trading strategy based on ML predictions."""
    
    def __init__(
        self,
        symbols: List[str],
        allocation: float = 0.25,
        min_confidence: float = 0.75,
        min_predicted_return: float = 0.003,  # 0.3%
        max_positions: int = 5
    ):
        super().__init__("ml_strategy", symbols, allocation)
        self.min_confidence = min_confidence
        self.min_predicted_return = min_predicted_return
        self.max_positions = max_positions
        self.current_positions: Dict[str, Dict[str, Any]] = {}
        
    async def initialize(self):
        """Initialize the strategy."""
        logger.info(f"Initializing ML strategy for {len(self.symbols)} symbols")
        
        # Train initial models
        await price_predictor.train_models(self.symbols)
        
        # Start continuous model updates
        asyncio.create_task(
            price_predictor.update_models_continuously(self.symbols)
        )
        
    async def generate_signals(self, market_data: Dict[str, Any]) -> List[Signal]:
        """Generate trading signals based on ML predictions."""
        signals = []
        
        try:
            # Get ML signals
            ml_signals = await price_predictor.generate_signals(
                self.symbols,
                self.min_confidence,
                self.min_predicted_return
            )
            
            for ml_signal in ml_signals:
                symbol = ml_signal.symbol
                
                # Check if we already have a position
                has_position = symbol in self.current_positions
                
                # Check position limits
                if not has_position and len(self.current_positions) >= self.max_positions:
                    continue
                    
                # Generate trading signal
                if ml_signal.action == "buy" and not has_position:
                    signal = Signal(
                        symbol=symbol,
                        action="buy",
                        strength=ml_signal.confidence,
                        reason=f"ML: {ml_signal.predicted_return:.2%} return expected, confidence {ml_signal.confidence:.1%}"
                    )
                    signals.append(signal)
                    
                elif ml_signal.action == "sell" and has_position:
                    # Check if prediction suggests closing position
                    position = self.current_positions[symbol]
                    
                    # Only sell if we're in profit or prediction is strongly negative
                    if position['unrealized_pnl'] > 0 or ml_signal.predicted_return < -0.005:
                        signal = Signal(
                            symbol=symbol,
                            action="sell",
                            strength=ml_signal.confidence,
                            reason=f"ML: {ml_signal.predicted_return:.2%} decline expected, closing position"
                        )
                        signals.append(signal)
                        
        except Exception as e:
            logger.error(f"Error generating ML signals: {e}")
            
        return signals
        
    async def update_positions(self, positions: List[Dict[str, Any]]):
        """Update current positions."""
        self.current_positions = {
            pos['symbol']: pos for pos in positions
            if pos['symbol'] in self.symbols
        }
        
    async def calculate_position_size(
        self,
        symbol: str,
        signal: Signal,
        current_price: float,
        account_value: float
    ) -> int:
        """Calculate position size based on ML confidence."""
        try:
            # Get latest prediction
            prediction = await price_predictor.predict_price(symbol, time_horizon=15)
            
            if not prediction:
                return 0
                
            # Base position size
            base_size = (account_value * self.allocation) / current_price
            
            # Adjust based on confidence and expected return
            confidence_factor = prediction.confidence
            return_factor = min(2.0, 1 + abs(prediction.predicted_change_pct) * 10)
            
            # Risk adjustment based on prediction variance
            risk_adjustment = 1.0
            if hasattr(prediction, 'risk_score'):
                risk_adjustment = 1.0 - (prediction.risk_score * 0.5)
                
            adjusted_size = base_size * confidence_factor * return_factor * risk_adjustment
            
            return int(adjusted_size)
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
            
    def get_strategy_params(self) -> Dict[str, Any]:
        """Get strategy parameters."""
        return {
            "min_confidence": self.min_confidence,
            "min_predicted_return": self.min_predicted_return,
            "max_positions": self.max_positions,
            "current_positions": len(self.current_positions),
            "model_status": {
                symbol: symbol in price_predictor.models
                for symbol in self.symbols
            }
        }
        
    async def should_exit_position(
        self,
        symbol: str,
        position: Dict[str, Any],
        current_price: float
    ) -> bool:
        """Check if position should be exited based on ML prediction."""
        try:
            # Get latest prediction
            prediction = await price_predictor.predict_price(symbol, time_horizon=5)
            
            if not prediction:
                return False
                
            # Exit if strong negative prediction
            if prediction.predicted_change_pct < -0.005 and prediction.confidence > 0.8:
                return True
                
            # Exit if target reached and momentum reversing
            if position['unrealized_pnl_pct'] > 0.02 and prediction.predicted_change_pct < 0:
                return True
                
            # Exit if stop loss and no recovery predicted
            if position['unrealized_pnl_pct'] < -0.03 and prediction.predicted_change_pct < 0:
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking exit condition: {e}")
            return False