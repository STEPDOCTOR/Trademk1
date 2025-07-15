"""Simple Moving Average (SMA) Crossover Strategy."""
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from app.services.strategies.base import BaseStrategy, Signal, SignalType, StrategyConfig


class SMACrossoverStrategy(BaseStrategy):
    """
    SMA Crossover Strategy.
    
    Generates buy signals when fast SMA crosses above slow SMA,
    and sell signals when fast SMA crosses below slow SMA.
    
    Parameters:
        fast_period: Period for fast moving average (default: 10)
        slow_period: Period for slow moving average (default: 30)
        use_ema: Use exponential moving average instead of simple (default: False)
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = self.parameters.get('fast_period', 10)
        self.slow_period = self.parameters.get('slow_period', 30)
        self.use_ema = self.parameters.get('use_ema', False)
        
    def validate_parameters(self) -> Tuple[bool, Optional[str]]:
        """Validate strategy parameters."""
        if self.fast_period <= 0:
            return False, "Fast period must be positive"
        if self.slow_period <= 0:
            return False, "Slow period must be positive"
        if self.fast_period >= self.slow_period:
            return False, "Fast period must be less than slow period"
        if len(self.symbols) == 0:
            return False, "At least one symbol must be configured"
        return True, None
        
    def calculate_moving_averages(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate moving averages for the data."""
        if self.use_ema:
            data['fast_ma'] = data['close'].ewm(span=self.fast_period, adjust=False).mean()
            data['slow_ma'] = data['close'].ewm(span=self.slow_period, adjust=False).mean()
        else:
            data['fast_ma'] = data['close'].rolling(window=self.fast_period).mean()
            data['slow_ma'] = data['close'].rolling(window=self.slow_period).mean()
            
        # Calculate crossover points
        data['position'] = 0
        data.loc[data['fast_ma'] > data['slow_ma'], 'position'] = 1
        data.loc[data['fast_ma'] < data['slow_ma'], 'position'] = -1
        
        # Identify crossover signals
        data['signal'] = data['position'].diff()
        
        return data
        
    async def calculate_signals(
        self,
        market_data: pd.DataFrame,
        current_positions: Dict[str, float]
    ) -> List[Signal]:
        """Calculate SMA crossover signals."""
        signals = []
        
        for symbol in self.symbols:
            # Filter data for this symbol
            symbol_data = market_data[market_data['symbol'] == symbol].copy()
            
            if len(symbol_data) < self.slow_period:
                continue  # Not enough data
                
            # Calculate moving averages
            symbol_data = self.calculate_moving_averages(symbol_data)
            
            # Get the latest signal
            latest = symbol_data.iloc[-1]
            prev = symbol_data.iloc[-2] if len(symbol_data) > 1 else None
            
            signal_value = latest['signal']
            current_position = current_positions.get(symbol, 0)
            
            # Generate signals based on crossovers
            if signal_value > 0:  # Bullish crossover
                if current_position <= 0:  # Not already long
                    # Calculate signal strength based on MA separation
                    ma_spread = (latest['fast_ma'] - latest['slow_ma']) / latest['close']
                    strength = min(1.0, abs(ma_spread) * 10)  # Scale to 0-1
                    
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        strength=strength,
                        reason=f"Bullish SMA crossover: {self.fast_period} > {self.slow_period}",
                        metadata={
                            'fast_ma': float(latest['fast_ma']),
                            'slow_ma': float(latest['slow_ma']),
                            'price': float(latest['close'])
                        }
                    )
                    signals.append(signal)
                    
            elif signal_value < 0:  # Bearish crossover
                if current_position > 0:  # Currently long
                    # Calculate signal strength
                    ma_spread = (latest['slow_ma'] - latest['fast_ma']) / latest['close']
                    strength = min(1.0, abs(ma_spread) * 10)
                    
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=strength,
                        quantity=current_position,  # Sell entire position
                        reason=f"Bearish SMA crossover: {self.fast_period} < {self.slow_period}",
                        metadata={
                            'fast_ma': float(latest['fast_ma']),
                            'slow_ma': float(latest['slow_ma']),
                            'price': float(latest['close'])
                        }
                    )
                    signals.append(signal)
                    
            # Optional: Generate hold signal for monitoring
            elif current_position > 0 and prev is not None:
                # Check trend strength for position monitoring
                trend_strength = (latest['fast_ma'] - latest['slow_ma']) / latest['slow_ma']
                
                if abs(trend_strength) < 0.001:  # Very weak trend
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_type=SignalType.HOLD,
                        strength=0.1,
                        reason="Weak trend - monitoring position",
                        metadata={
                            'trend_strength': float(trend_strength),
                            'fast_ma': float(latest['fast_ma']),
                            'slow_ma': float(latest['slow_ma'])
                        }
                    )
                    signals.append(signal)
                    
        return signals
        
    def backtest_metrics(self, trades_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate strategy-specific backtest metrics."""
        if trades_df.empty:
            return {}
            
        metrics = {
            'total_trades': len(trades_df),
            'avg_bars_in_trade': trades_df['bars_held'].mean() if 'bars_held' in trades_df else 0,
            'profit_factor': abs(trades_df[trades_df['pnl'] > 0]['pnl'].sum() / 
                               trades_df[trades_df['pnl'] < 0]['pnl'].sum()) if len(trades_df[trades_df['pnl'] < 0]) > 0 else np.inf,
            'avg_mae': trades_df['mae'].mean() if 'mae' in trades_df else 0,  # Maximum adverse excursion
            'avg_mfe': trades_df['mfe'].mean() if 'mfe' in trades_df else 0,  # Maximum favorable excursion
        }
        
        return metrics