"""Performance metrics and reporting for trading strategies."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from enum import Enum


class MetricPeriod(str, Enum):
    """Time periods for metric calculation."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


@dataclass
class PerformanceReport:
    """Comprehensive performance report for a strategy or portfolio."""
    report_id: str
    strategy_id: str
    period: MetricPeriod
    start_date: datetime
    end_date: datetime
    
    # Return metrics
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    
    # Risk metrics
    max_drawdown: float
    max_drawdown_duration: int  # days
    var_95: float
    cvar_95: float
    downside_deviation: float
    
    # Trade metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    
    # Additional metrics
    best_trade: float
    worst_trade: float
    avg_trade_duration: float  # days
    time_in_market: float  # percentage
    
    # Time series data
    equity_curve: pd.DataFrame
    monthly_returns: pd.Series
    rolling_sharpe: pd.Series
    
    metadata: Dict[str, Any]


class PerformanceAnalyzer:
    """Analyzes and reports on strategy performance."""
    
    def __init__(self):
        self.benchmark_returns: Optional[pd.Series] = None
        
    def generate_report(
        self,
        trades: pd.DataFrame,
        equity_curve: pd.DataFrame,
        strategy_id: str,
        period: MetricPeriod = MetricPeriod.ALL_TIME,
        benchmark: Optional[pd.Series] = None
    ) -> PerformanceReport:
        """Generate comprehensive performance report."""
        # Filter by period
        start_date, end_date = self._get_period_dates(period, equity_curve.index)
        period_equity = equity_curve[start_date:end_date]
        period_trades = trades[(trades['entry_time'] >= start_date) & 
                               (trades['exit_time'] <= end_date)]
        
        # Calculate returns
        returns = period_equity['total_equity'].pct_change().dropna()
        
        # Return metrics
        total_return = (period_equity['total_equity'].iloc[-1] / 
                       period_equity['total_equity'].iloc[0] - 1)
        annualized_return = self._annualize_return(total_return, len(period_equity))
        volatility = returns.std() * np.sqrt(252)
        
        # Risk-adjusted returns
        sharpe_ratio = self._calculate_sharpe(returns, annualized_return, volatility)
        sortino_ratio = self._calculate_sortino(returns, annualized_return)
        
        # Drawdown analysis
        drawdown_data = self._calculate_drawdowns(period_equity['total_equity'])
        max_drawdown = drawdown_data['max_drawdown']
        max_dd_duration = drawdown_data['max_duration']
        
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0
        
        # VaR and CVaR
        var_95 = np.percentile(returns, 5)
        cvar_95 = returns[returns <= var_95].mean()
        
        # Trade analysis
        trade_metrics = self._analyze_trades(period_trades)
        
        # Monthly returns
        monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
        
        # Rolling metrics
        rolling_sharpe = self._calculate_rolling_sharpe(returns, window=252)
        
        # Create report
        report = PerformanceReport(
            report_id=f"{strategy_id}_{period.value}_{datetime.utcnow().isoformat()}",
            strategy_id=strategy_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            var_95=var_95,
            cvar_95=cvar_95,
            downside_deviation=self._calculate_downside_deviation(returns),
            total_trades=trade_metrics['total_trades'],
            winning_trades=trade_metrics['winning_trades'],
            losing_trades=trade_metrics['losing_trades'],
            win_rate=trade_metrics['win_rate'],
            avg_win=trade_metrics['avg_win'],
            avg_loss=trade_metrics['avg_loss'],
            profit_factor=trade_metrics['profit_factor'],
            expectancy=trade_metrics['expectancy'],
            best_trade=trade_metrics['best_trade'],
            worst_trade=trade_metrics['worst_trade'],
            avg_trade_duration=trade_metrics['avg_duration'],
            time_in_market=self._calculate_time_in_market(period_equity),
            equity_curve=period_equity,
            monthly_returns=monthly_returns,
            rolling_sharpe=rolling_sharpe,
            metadata=self._generate_metadata(period_equity, period_trades, benchmark)
        )
        
        return report
        
    def _get_period_dates(
        self,
        period: MetricPeriod,
        index: pd.DatetimeIndex
    ) -> Tuple[datetime, datetime]:
        """Get start and end dates for period."""
        end_date = index[-1]
        
        if period == MetricPeriod.ALL_TIME:
            start_date = index[0]
        elif period == MetricPeriod.DAILY:
            start_date = end_date - timedelta(days=1)
        elif period == MetricPeriod.WEEKLY:
            start_date = end_date - timedelta(days=7)
        elif period == MetricPeriod.MONTHLY:
            start_date = end_date - timedelta(days=30)
        elif period == MetricPeriod.QUARTERLY:
            start_date = end_date - timedelta(days=90)
        elif period == MetricPeriod.YEARLY:
            start_date = end_date - timedelta(days=365)
        else:
            start_date = index[0]
            
        # Ensure start_date is in index
        if start_date < index[0]:
            start_date = index[0]
            
        return start_date, end_date
        
    def _annualize_return(self, total_return: float, periods: int) -> float:
        """Annualize return based on number of periods."""
        if periods <= 0:
            return 0
        years = periods / 252  # Assuming daily data
        return (1 + total_return) ** (1 / years) - 1
        
    def _calculate_sharpe(
        self,
        returns: pd.Series,
        annual_return: float,
        volatility: float
    ) -> float:
        """Calculate Sharpe ratio."""
        if volatility == 0:
            return 0
        return annual_return / volatility
        
    def _calculate_sortino(
        self,
        returns: pd.Series,
        annual_return: float
    ) -> float:
        """Calculate Sortino ratio."""
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return 0
            
        downside_vol = downside_returns.std() * np.sqrt(252)
        if downside_vol == 0:
            return 0
            
        return annual_return / downside_vol
        
    def _calculate_drawdowns(
        self,
        equity_series: pd.Series
    ) -> Dict[str, Any]:
        """Calculate drawdown statistics."""
        rolling_max = equity_series.expanding().max()
        drawdowns = (equity_series - rolling_max) / rolling_max
        
        # Find drawdown periods
        is_drawdown = drawdowns < 0
        drawdown_groups = (is_drawdown != is_drawdown.shift()).cumsum()
        
        max_drawdown = drawdowns.min()
        
        # Calculate max duration
        max_duration = 0
        if any(is_drawdown):
            for _, group in drawdowns[is_drawdown].groupby(drawdown_groups[is_drawdown]):
                duration = len(group)
                max_duration = max(max_duration, duration)
                
        return {
            'max_drawdown': max_drawdown,
            'max_duration': max_duration,
            'current_drawdown': drawdowns.iloc[-1],
            'drawdown_periods': drawdown_groups.max()
        }
        
    def _analyze_trades(self, trades: pd.DataFrame) -> Dict[str, Any]:
        """Analyze trade statistics."""
        if trades.empty:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'expectancy': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_duration': 0
            }
            
        winning_trades = trades[trades['pnl'] > 0]
        losing_trades = trades[trades['pnl'] < 0]
        
        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_rate = win_count / total_trades if total_trades > 0 else 0
        avg_win = winning_trades['pnl'].mean() if win_count > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if loss_count > 0 else 0
        
        gross_profit = winning_trades['pnl'].sum() if win_count > 0 else 0
        gross_loss = abs(losing_trades['pnl'].sum()) if loss_count > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        expectancy = trades['pnl'].mean()
        best_trade = trades['pnl'].max()
        worst_trade = trades['pnl'].min()
        
        # Calculate average duration
        trades['duration'] = (trades['exit_time'] - trades['entry_time']).dt.total_seconds() / 86400
        avg_duration = trades['duration'].mean()
        
        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_duration': avg_duration
        }
        
    def _calculate_downside_deviation(self, returns: pd.Series) -> float:
        """Calculate downside deviation."""
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return 0
        return downside_returns.std() * np.sqrt(252)
        
    def _calculate_time_in_market(self, equity_df: pd.DataFrame) -> float:
        """Calculate percentage of time with open positions."""
        if 'positions' not in equity_df.columns:
            return 0
            
        periods_with_positions = (equity_df['positions'] > 0).sum()
        total_periods = len(equity_df)
        
        return periods_with_positions / total_periods if total_periods > 0 else 0
        
    def _calculate_rolling_sharpe(
        self,
        returns: pd.Series,
        window: int = 252
    ) -> pd.Series:
        """Calculate rolling Sharpe ratio."""
        rolling_mean = returns.rolling(window).mean() * 252
        rolling_std = returns.rolling(window).std() * np.sqrt(252)
        
        rolling_sharpe = rolling_mean / rolling_std
        rolling_sharpe = rolling_sharpe.fillna(0)
        
        return rolling_sharpe
        
    def _generate_metadata(
        self,
        equity_df: pd.DataFrame,
        trades: pd.DataFrame,
        benchmark: Optional[pd.Series]
    ) -> Dict[str, Any]:
        """Generate additional metadata for the report."""
        metadata = {
            'data_points': len(equity_df),
            'trading_days': len(equity_df),
            'first_trade': trades['entry_time'].min().isoformat() if not trades.empty else None,
            'last_trade': trades['exit_time'].max().isoformat() if not trades.empty else None,
            'report_generated': datetime.utcnow().isoformat()
        }
        
        # Add benchmark comparison if provided
        if benchmark is not None:
            benchmark_return = (benchmark.iloc[-1] / benchmark.iloc[0] - 1)
            metadata['benchmark_return'] = benchmark_return
            metadata['excess_return'] = metadata.get('total_return', 0) - benchmark_return
            
            # Calculate beta and alpha
            if len(equity_df) > 20:
                strategy_returns = equity_df['total_equity'].pct_change().dropna()
                benchmark_returns = benchmark.pct_change().dropna()
                
                # Align dates
                common_dates = strategy_returns.index.intersection(benchmark_returns.index)
                if len(common_dates) > 20:
                    aligned_strategy = strategy_returns[common_dates]
                    aligned_benchmark = benchmark_returns[common_dates]
                    
                    covariance = np.cov(aligned_strategy, aligned_benchmark)[0, 1]
                    benchmark_var = np.var(aligned_benchmark)
                    
                    beta = covariance / benchmark_var if benchmark_var > 0 else 0
                    alpha = metadata.get('annualized_return', 0) - beta * (benchmark_return * 252 / len(benchmark))
                    
                    metadata['beta'] = beta
                    metadata['alpha'] = alpha
                    
        return metadata
        
    def compare_strategies(
        self,
        reports: List[PerformanceReport]
    ) -> pd.DataFrame:
        """Compare multiple strategy performance reports."""
        comparison_data = []
        
        for report in reports:
            data = {
                'strategy_id': report.strategy_id,
                'period': report.period.value,
                'total_return': report.total_return,
                'annual_return': report.annualized_return,
                'volatility': report.volatility,
                'sharpe_ratio': report.sharpe_ratio,
                'max_drawdown': report.max_drawdown,
                'win_rate': report.win_rate,
                'profit_factor': report.profit_factor,
                'total_trades': report.total_trades
            }
            comparison_data.append(data)
            
        return pd.DataFrame(comparison_data)