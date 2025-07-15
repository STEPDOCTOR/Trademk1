"""Backtesting engine for trading strategies."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from uuid import uuid4

from app.services.strategies.base import BaseStrategy, Signal, SignalType


@dataclass
class Trade:
    """Represents a completed trade in backtest."""
    trade_id: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: str  # 'long' or 'short'
    pnl: float
    pnl_percent: float
    fees: float
    slippage: float
    strategy_id: str
    entry_signal: Signal
    exit_signal: Optional[Signal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class BacktestResult:
    """Results from a backtest run."""
    strategy_id: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    trades: List[Trade]
    equity_curve: pd.DataFrame
    metrics: Dict[str, float]
    drawdown_series: pd.Series
    
    
class BacktestEngine:
    """Engine for backtesting trading strategies."""
    
    def __init__(
        self,
        initial_capital: float = 100000,
        commission: float = 0.001,  # 0.1%
        slippage: float = 0.0005,   # 0.05%
        margin_requirement: float = 1.0  # 1.0 = no margin
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.margin_requirement = margin_requirement
        
        # Backtest state
        self.cash = initial_capital
        self.positions: Dict[str, float] = {}
        self.trades: List[Trade] = []
        self.pending_signals: Dict[str, Signal] = {}
        self.equity_history: List[Dict[str, Any]] = []
        
    async def run_backtest(
        self,
        strategy: BaseStrategy,
        market_data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """
        Run backtest for a strategy.
        
        Args:
            strategy: Strategy to backtest
            market_data: Historical market data
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            BacktestResult with performance metrics
        """
        # Reset state
        self.cash = self.initial_capital
        self.positions = {}
        self.trades = []
        self.pending_signals = {}
        self.equity_history = []
        
        # Filter data by date range
        if start_date:
            market_data = market_data[market_data['timestamp'] >= start_date]
        if end_date:
            market_data = market_data[market_data['timestamp'] <= end_date]
            
        # Group data by timestamp for time-series processing
        grouped_data = market_data.groupby('timestamp')
        
        # Initialize account value tracking
        timestamps = sorted(market_data['timestamp'].unique())
        
        for timestamp in timestamps:
            # Get data up to current timestamp
            historical_data = market_data[market_data['timestamp'] <= timestamp]
            current_data = grouped_data.get_group(timestamp)
            
            # Update equity
            self._update_equity(timestamp, current_data)
            
            # Get signals from strategy
            signals = await strategy.execute(historical_data, self.positions.copy())
            
            # Process signals
            for signal in signals:
                await self._process_signal(signal, current_data, timestamp)
                
        # Close any remaining positions at end
        final_timestamp = timestamps[-1]
        final_data = grouped_data.get_group(final_timestamp)
        await self._close_all_positions(final_data, final_timestamp)
        
        # Calculate final metrics
        result = self._calculate_results(
            strategy.strategy_id,
            start_date or market_data['timestamp'].min(),
            end_date or market_data['timestamp'].max()
        )
        
        return result
        
    async def _process_signal(
        self,
        signal: Signal,
        current_data: pd.DataFrame,
        timestamp: datetime
    ):
        """Process a trading signal."""
        symbol_data = current_data[current_data['symbol'] == signal.symbol]
        if symbol_data.empty:
            return
            
        current_price = float(symbol_data.iloc[0]['close'])
        
        if signal.signal_type == SignalType.BUY:
            await self._execute_buy(signal, current_price, timestamp)
        elif signal.signal_type == SignalType.SELL:
            await self._execute_sell(signal, current_price, timestamp)
            
    async def _execute_buy(
        self,
        signal: Signal,
        price: float,
        timestamp: datetime
    ):
        """Execute a buy order."""
        # Calculate position size
        if signal.quantity:
            quantity = signal.quantity
        else:
            # Use 2% of capital as default
            position_value = self.cash * 0.02
            quantity = position_value / price
            
        # Apply slippage
        execution_price = price * (1 + self.slippage)
        
        # Calculate costs
        trade_value = quantity * execution_price
        commission_cost = trade_value * self.commission
        total_cost = trade_value + commission_cost
        
        # Check if we have enough cash
        if total_cost > self.cash:
            return  # Skip if insufficient funds
            
        # Update positions and cash
        self.positions[signal.symbol] = self.positions.get(signal.symbol, 0) + quantity
        self.cash -= total_cost
        
        # Store pending signal for trade tracking
        self.pending_signals[signal.symbol] = signal
        
    async def _execute_sell(
        self,
        signal: Signal,
        price: float,
        timestamp: datetime
    ):
        """Execute a sell order."""
        current_position = self.positions.get(signal.symbol, 0)
        if current_position <= 0:
            return  # No position to sell
            
        # Determine quantity to sell
        quantity = min(signal.quantity or current_position, current_position)
        
        # Apply slippage
        execution_price = price * (1 - self.slippage)
        
        # Calculate proceeds
        trade_value = quantity * execution_price
        commission_cost = trade_value * self.commission
        net_proceeds = trade_value - commission_cost
        
        # Update positions and cash
        self.positions[signal.symbol] -= quantity
        if self.positions[signal.symbol] <= 0:
            del self.positions[signal.symbol]
        self.cash += net_proceeds
        
        # Create trade record if we have entry signal
        if signal.symbol in self.pending_signals:
            entry_signal = self.pending_signals[signal.symbol]
            
            # Calculate trade P&L
            entry_price = float(entry_signal.metadata.get('price', price))
            pnl = (execution_price - entry_price) * quantity - commission_cost * 2
            pnl_percent = pnl / (entry_price * quantity)
            
            trade = Trade(
                trade_id=str(uuid4()),
                symbol=signal.symbol,
                entry_time=entry_signal.timestamp,
                exit_time=timestamp,
                entry_price=entry_price,
                exit_price=execution_price,
                quantity=quantity,
                side='long',
                pnl=pnl,
                pnl_percent=pnl_percent,
                fees=commission_cost * 2,
                slippage=self.slippage * (entry_price + execution_price),
                strategy_id=signal.strategy_id,
                entry_signal=entry_signal,
                exit_signal=signal
            )
            
            self.trades.append(trade)
            
            # Remove pending signal if position closed
            if signal.symbol not in self.positions:
                del self.pending_signals[signal.symbol]
                
    async def _close_all_positions(
        self,
        final_data: pd.DataFrame,
        timestamp: datetime
    ):
        """Close all remaining positions at end of backtest."""
        for symbol, quantity in list(self.positions.items()):
            symbol_data = final_data[final_data['symbol'] == symbol]
            if not symbol_data.empty:
                price = float(symbol_data.iloc[0]['close'])
                
                # Create exit signal
                exit_signal = Signal(
                    strategy_id="backtest_close",
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=1.0,
                    quantity=quantity,
                    reason="Backtest end - closing position"
                )
                
                await self._execute_sell(exit_signal, price, timestamp)
                
    def _update_equity(self, timestamp: datetime, current_data: pd.DataFrame):
        """Update and record current equity value."""
        # Calculate position values
        position_value = 0
        for symbol, quantity in self.positions.items():
            symbol_data = current_data[current_data['symbol'] == symbol]
            if not symbol_data.empty:
                price = float(symbol_data.iloc[0]['close'])
                position_value += quantity * price
                
        total_equity = self.cash + position_value
        
        self.equity_history.append({
            'timestamp': timestamp,
            'cash': self.cash,
            'position_value': position_value,
            'total_equity': total_equity,
            'positions': len(self.positions)
        })
        
    def _calculate_results(
        self,
        strategy_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestResult:
        """Calculate backtest results and metrics."""
        # Create equity curve
        equity_df = pd.DataFrame(self.equity_history)
        equity_df.set_index('timestamp', inplace=True)
        
        # Calculate returns
        equity_df['returns'] = equity_df['total_equity'].pct_change()
        equity_df['cumulative_returns'] = (1 + equity_df['returns']).cumprod() - 1
        
        # Calculate drawdown
        equity_df['running_max'] = equity_df['total_equity'].cummax()
        equity_df['drawdown'] = (equity_df['total_equity'] - equity_df['running_max']) / equity_df['running_max']
        
        # Calculate metrics
        metrics = self._calculate_metrics(equity_df, self.trades)
        
        return BacktestResult(
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=equity_df['total_equity'].iloc[-1] if not equity_df.empty else self.initial_capital,
            trades=self.trades,
            equity_curve=equity_df,
            metrics=metrics,
            drawdown_series=equity_df['drawdown']
        )
        
    def _calculate_metrics(
        self,
        equity_df: pd.DataFrame,
        trades: List[Trade]
    ) -> Dict[str, float]:
        """Calculate performance metrics."""
        if equity_df.empty:
            return {}
            
        # Basic metrics
        total_return = (equity_df['total_equity'].iloc[-1] / self.initial_capital - 1)
        
        # Annualized metrics (assuming daily data)
        days = len(equity_df)
        annual_factor = 252 / days if days > 0 else 1
        
        returns = equity_df['returns'].dropna()
        
        metrics = {
            # Returns
            'total_return': total_return,
            'annual_return': (1 + total_return) ** annual_factor - 1,
            'volatility': returns.std() * np.sqrt(252) if len(returns) > 0 else 0,
            
            # Risk metrics
            'max_drawdown': equity_df['drawdown'].min(),
            'calmar_ratio': 0,  # Will calculate below
            'sharpe_ratio': 0,  # Will calculate below
            'sortino_ratio': 0,  # Will calculate below
            
            # Trade statistics
            'total_trades': len(trades),
            'win_rate': 0,  # Will calculate below
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'expectancy': 0,
            
            # Other metrics
            'time_in_market': len(equity_df[equity_df['positions'] > 0]) / len(equity_df) if len(equity_df) > 0 else 0
        }
        
        # Calculate Sharpe ratio (assuming 0% risk-free rate)
        if metrics['volatility'] > 0:
            metrics['sharpe_ratio'] = metrics['annual_return'] / metrics['volatility']
            
        # Calculate Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_vol = downside_returns.std() * np.sqrt(252)
            if downside_vol > 0:
                metrics['sortino_ratio'] = metrics['annual_return'] / downside_vol
                
        # Calculate Calmar ratio
        if metrics['max_drawdown'] < 0:
            metrics['calmar_ratio'] = metrics['annual_return'] / abs(metrics['max_drawdown'])
            
        # Trade metrics
        if trades:
            winning_trades = [t for t in trades if t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl < 0]
            
            metrics['win_rate'] = len(winning_trades) / len(trades)
            
            if winning_trades:
                metrics['avg_win'] = np.mean([t.pnl for t in winning_trades])
                
            if losing_trades:
                metrics['avg_loss'] = np.mean([t.pnl for t in losing_trades])
                metrics['profit_factor'] = sum(t.pnl for t in winning_trades) / abs(sum(t.pnl for t in losing_trades))
                
            metrics['expectancy'] = np.mean([t.pnl for t in trades])
            
        return metrics