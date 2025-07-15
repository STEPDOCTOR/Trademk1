"""Momentum-based trading strategy."""
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from app.services.strategies.base import BaseStrategy, Signal, SignalType, StrategyConfig


class MomentumStrategy(BaseStrategy):
    """
    Momentum Trading Strategy.
    
    Trades based on momentum indicators including RSI, rate of change,
    and volume confirmation.
    
    Parameters:
        rsi_period: Period for RSI calculation (default: 14)
        rsi_oversold: RSI oversold threshold (default: 30)
        rsi_overbought: RSI overbought threshold (default: 70)
        roc_period: Rate of change period (default: 10)
        roc_threshold: ROC threshold for signals (default: 0.05)
        volume_factor: Volume confirmation factor (default: 1.5)
        use_divergence: Check for price/RSI divergence (default: True)
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.rsi_period = self.parameters.get('rsi_period', 14)
        self.rsi_oversold = self.parameters.get('rsi_oversold', 30)
        self.rsi_overbought = self.parameters.get('rsi_overbought', 70)
        self.roc_period = self.parameters.get('roc_period', 10)
        self.roc_threshold = self.parameters.get('roc_threshold', 0.05)
        self.volume_factor = self.parameters.get('volume_factor', 1.5)
        self.use_divergence = self.parameters.get('use_divergence', True)
        
    def validate_parameters(self) -> Tuple[bool, Optional[str]]:
        """Validate strategy parameters."""
        if self.rsi_period <= 0:
            return False, "RSI period must be positive"
        if not (0 <= self.rsi_oversold < self.rsi_overbought <= 100):
            return False, "Invalid RSI thresholds"
        if self.roc_period <= 0:
            return False, "ROC period must be positive"
        if self.volume_factor <= 0:
            return False, "Volume factor must be positive"
        return True, None
        
    def calculate_rsi(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate momentum indicators."""
        # RSI
        data['rsi'] = self.calculate_rsi(data['close'], self.rsi_period)
        
        # Rate of Change
        data['roc'] = (data['close'] - data['close'].shift(self.roc_period)) / data['close'].shift(self.roc_period)
        
        # Volume indicators
        data['volume_sma'] = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / data['volume_sma']
        
        # Price momentum
        data['price_momentum'] = data['close'].pct_change(self.roc_period)
        
        # Highs and lows for divergence
        data['high_rolling'] = data['high'].rolling(window=self.roc_period).max()
        data['low_rolling'] = data['low'].rolling(window=self.roc_period).min()
        
        return data
        
    def check_divergence(self, data: pd.DataFrame, lookback: int = 20) -> Tuple[bool, bool]:
        """Check for bullish or bearish divergence between price and RSI."""
        if len(data) < lookback:
            return False, False
            
        recent_data = data.tail(lookback)
        
        # Find swing highs and lows in price
        price_highs = recent_data[recent_data['high'] == recent_data['high_rolling']]['high']
        price_lows = recent_data[recent_data['low'] == recent_data['low_rolling']]['low']
        
        # Find corresponding RSI values
        if len(price_highs) >= 2:
            # Check for bearish divergence (higher highs in price, lower highs in RSI)
            last_high_idx = price_highs.index[-1]
            prev_high_idx = price_highs.index[-2]
            
            if (data.loc[last_high_idx, 'high'] > data.loc[prev_high_idx, 'high'] and
                data.loc[last_high_idx, 'rsi'] < data.loc[prev_high_idx, 'rsi']):
                return False, True  # Bearish divergence
                
        if len(price_lows) >= 2:
            # Check for bullish divergence (lower lows in price, higher lows in RSI)
            last_low_idx = price_lows.index[-1]
            prev_low_idx = price_lows.index[-2]
            
            if (data.loc[last_low_idx, 'low'] < data.loc[prev_low_idx, 'low'] and
                data.loc[last_low_idx, 'rsi'] > data.loc[prev_low_idx, 'rsi']):
                return True, False  # Bullish divergence
                
        return False, False
        
    async def calculate_signals(
        self,
        market_data: pd.DataFrame,
        current_positions: Dict[str, float]
    ) -> List[Signal]:
        """Calculate momentum-based signals."""
        signals = []
        
        for symbol in self.symbols:
            # Filter data for this symbol
            symbol_data = market_data[market_data['symbol'] == symbol].copy()
            
            if len(symbol_data) < max(self.rsi_period, self.roc_period) + 1:
                continue  # Not enough data
                
            # Calculate indicators
            symbol_data = self.calculate_indicators(symbol_data)
            
            # Get latest values
            latest = symbol_data.iloc[-1]
            current_position = current_positions.get(symbol, 0)
            
            # Check for divergence if enabled
            bullish_div = False
            bearish_div = False
            if self.use_divergence:
                bullish_div, bearish_div = self.check_divergence(symbol_data)
                
            # Buy signals
            if current_position <= 0:  # Not already long
                buy_conditions = []
                signal_strength = 0
                
                # RSI oversold
                if latest['rsi'] < self.rsi_oversold:
                    buy_conditions.append("RSI oversold")
                    signal_strength += 0.3
                    
                # Strong positive momentum
                if latest['roc'] > self.roc_threshold:
                    buy_conditions.append("Strong positive ROC")
                    signal_strength += 0.3
                    
                # Volume confirmation
                if latest['volume_ratio'] > self.volume_factor:
                    buy_conditions.append("High volume")
                    signal_strength += 0.2
                    
                # Bullish divergence
                if bullish_div:
                    buy_conditions.append("Bullish divergence")
                    signal_strength += 0.4
                    
                # Generate buy signal if conditions met
                if signal_strength >= 0.5:  # At least moderate strength
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        strength=min(1.0, signal_strength),
                        reason=f"Momentum buy: {', '.join(buy_conditions)}",
                        metadata={
                            'rsi': float(latest['rsi']),
                            'roc': float(latest['roc']),
                            'volume_ratio': float(latest['volume_ratio']),
                            'price': float(latest['close']),
                            'conditions': buy_conditions
                        }
                    )
                    signals.append(signal)
                    
            # Sell signals
            elif current_position > 0:  # Currently long
                sell_conditions = []
                signal_strength = 0
                
                # RSI overbought
                if latest['rsi'] > self.rsi_overbought:
                    sell_conditions.append("RSI overbought")
                    signal_strength += 0.3
                    
                # Negative momentum
                if latest['roc'] < -self.roc_threshold:
                    sell_conditions.append("Strong negative ROC")
                    signal_strength += 0.4
                    
                # Bearish divergence
                if bearish_div:
                    sell_conditions.append("Bearish divergence")
                    signal_strength += 0.4
                    
                # Momentum reversal
                if latest['price_momentum'] < -0.02 and latest['volume_ratio'] > self.volume_factor:
                    sell_conditions.append("Momentum reversal with volume")
                    signal_strength += 0.3
                    
                # Generate sell signal if conditions met
                if signal_strength >= 0.4:  # Lower threshold for exits
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=min(1.0, signal_strength),
                        quantity=current_position,
                        reason=f"Momentum sell: {', '.join(sell_conditions)}",
                        metadata={
                            'rsi': float(latest['rsi']),
                            'roc': float(latest['roc']),
                            'volume_ratio': float(latest['volume_ratio']),
                            'price': float(latest['close']),
                            'conditions': sell_conditions
                        }
                    )
                    signals.append(signal)
                    
        return signals
        
    def backtest_metrics(self, trades_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate momentum strategy specific metrics."""
        if trades_df.empty:
            return {}
            
        # Calculate win rate by signal type
        metrics = {}
        
        if 'entry_conditions' in trades_df:
            # Analyze which conditions lead to profitable trades
            for condition in ['RSI oversold', 'Strong positive ROC', 'High volume', 'Bullish divergence']:
                condition_trades = trades_df[trades_df['entry_conditions'].str.contains(condition, na=False)]
                if len(condition_trades) > 0:
                    win_rate = len(condition_trades[condition_trades['pnl'] > 0]) / len(condition_trades)
                    avg_pnl = condition_trades['pnl'].mean()
                    metrics[f'{condition}_win_rate'] = win_rate
                    metrics[f'{condition}_avg_pnl'] = avg_pnl
                    
        # General momentum metrics
        metrics.update({
            'avg_holding_period': trades_df['holding_period'].mean() if 'holding_period' in trades_df else 0,
            'best_trade': trades_df['pnl'].max() if 'pnl' in trades_df else 0,
            'worst_trade': trades_df['pnl'].min() if 'pnl' in trades_df else 0,
            'risk_reward_ratio': abs(trades_df[trades_df['pnl'] > 0]['pnl'].mean() / 
                                   trades_df[trades_df['pnl'] < 0]['pnl'].mean()) if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0
        })
        
        return metrics