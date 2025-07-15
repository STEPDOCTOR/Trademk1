"""Advanced risk management for trading strategies."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from enum import Enum

from app.services.strategies.base import Signal, SignalType


class RiskLevel(str, Enum):
    """Risk level classifications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RiskMetrics:
    """Current risk metrics for portfolio."""
    timestamp: datetime
    total_exposure: float
    var_95: float  # Value at Risk 95%
    cvar_95: float  # Conditional VaR (Expected Shortfall)
    current_drawdown: float
    max_drawdown: float
    correlation_risk: float
    concentration_risk: float
    leverage_ratio: float
    risk_level: RiskLevel
    warnings: List[str]
    

class AdvancedRiskManager:
    """Advanced risk management with drawdown control and correlation analysis."""
    
    def __init__(
        self,
        max_drawdown: float = 0.20,  # 20% max drawdown
        max_correlation: float = 0.7,  # Max correlation between positions
        max_var_95: float = 0.05,  # 5% VaR limit
        max_leverage: float = 1.0,  # No leverage by default
        max_concentration: float = 0.25,  # 25% max in single position
        lookback_days: int = 252  # 1 year for risk calculations
    ):
        self.max_drawdown = max_drawdown
        self.max_correlation = max_correlation
        self.max_var_95 = max_var_95
        self.max_leverage = max_leverage
        self.max_concentration = max_concentration
        self.lookback_days = lookback_days
        
        # Risk state
        self.equity_history: List[float] = []
        self.position_history: Dict[str, List[float]] = {}
        self.returns_history: pd.DataFrame = pd.DataFrame()
        self.correlation_matrix: pd.DataFrame = pd.DataFrame()
        
    def update_history(
        self,
        equity: float,
        positions: Dict[str, float],
        market_prices: Dict[str, float],
        timestamp: datetime
    ):
        """Update risk tracking history."""
        # Update equity history
        self.equity_history.append(equity)
        if len(self.equity_history) > self.lookback_days:
            self.equity_history.pop(0)
            
        # Update position returns
        returns_data = {}
        for symbol, quantity in positions.items():
            if symbol in market_prices:
                value = quantity * market_prices[symbol]
                
                if symbol not in self.position_history:
                    self.position_history[symbol] = []
                    
                self.position_history[symbol].append(value)
                
                # Calculate return if we have history
                if len(self.position_history[symbol]) > 1:
                    prev_value = self.position_history[symbol][-2]
                    if prev_value != 0:
                        returns_data[symbol] = (value - prev_value) / prev_value
                    else:
                        returns_data[symbol] = 0
                else:
                    returns_data[symbol] = 0
                    
        # Update returns dataframe
        if returns_data:
            new_row = pd.DataFrame([returns_data], index=[timestamp])
            self.returns_history = pd.concat([self.returns_history, new_row])
            
            # Keep only lookback period
            if len(self.returns_history) > self.lookback_days:
                self.returns_history = self.returns_history.iloc[-self.lookback_days:]
                
            # Update correlation matrix
            if len(self.returns_history) > 20:  # Need minimum data
                self.correlation_matrix = self.returns_history.corr()
                
    def calculate_risk_metrics(
        self,
        current_equity: float,
        positions: Dict[str, float],
        market_prices: Dict[str, float],
        account_value: float
    ) -> RiskMetrics:
        """Calculate comprehensive risk metrics."""
        warnings = []
        
        # Calculate exposure
        total_exposure = sum(
            abs(positions.get(symbol, 0) * market_prices.get(symbol, 0))
            for symbol in positions
        )
        
        # Calculate drawdown
        current_drawdown = 0
        max_drawdown_value = 0
        if self.equity_history:
            peak = max(self.equity_history)
            current_drawdown = (current_equity - peak) / peak if peak > 0 else 0
            
            # Calculate max drawdown from history
            peaks = pd.Series(self.equity_history).expanding().max()
            drawdowns = (pd.Series(self.equity_history) - peaks) / peaks
            max_drawdown_value = drawdowns.min()
            
        # Calculate VaR and CVaR
        var_95 = 0
        cvar_95 = 0
        if len(self.returns_history) > 20:
            portfolio_returns = self.returns_history.mean(axis=1)
            var_95 = np.percentile(portfolio_returns, 5)
            cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean()
            
        # Calculate correlation risk
        correlation_risk = self._calculate_correlation_risk(positions)
        
        # Calculate concentration risk
        concentration_risk = 0
        if total_exposure > 0:
            position_values = {
                symbol: abs(qty * market_prices.get(symbol, 0))
                for symbol, qty in positions.items()
            }
            if position_values:
                max_position = max(position_values.values())
                concentration_risk = max_position / total_exposure
                
        # Calculate leverage
        leverage_ratio = total_exposure / account_value if account_value > 0 else 0
        
        # Determine risk level and warnings
        risk_score = 0
        
        if abs(current_drawdown) > self.max_drawdown * 0.5:
            risk_score += 1
            warnings.append(f"Drawdown at {abs(current_drawdown)*100:.1f}% (limit: {self.max_drawdown*100}%)")
            
        if abs(current_drawdown) > self.max_drawdown:
            risk_score += 2
            warnings.append("CRITICAL: Maximum drawdown exceeded!")
            
        if abs(var_95) > self.max_var_95:
            risk_score += 1
            warnings.append(f"VaR exceeds limit: {abs(var_95)*100:.1f}% > {self.max_var_95*100}%")
            
        if correlation_risk > self.max_correlation:
            risk_score += 1
            warnings.append(f"High correlation risk: {correlation_risk:.2f}")
            
        if concentration_risk > self.max_concentration:
            risk_score += 1
            warnings.append(f"Position concentration too high: {concentration_risk*100:.1f}%")
            
        if leverage_ratio > self.max_leverage:
            risk_score += 2
            warnings.append(f"Leverage exceeds limit: {leverage_ratio:.2f}x")
            
        # Determine risk level
        if risk_score >= 4:
            risk_level = RiskLevel.EXTREME
        elif risk_score >= 2:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 1:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
            
        return RiskMetrics(
            timestamp=datetime.utcnow(),
            total_exposure=total_exposure,
            var_95=var_95,
            cvar_95=cvar_95,
            current_drawdown=current_drawdown,
            max_drawdown=max_drawdown_value,
            correlation_risk=correlation_risk,
            concentration_risk=concentration_risk,
            leverage_ratio=leverage_ratio,
            risk_level=risk_level,
            warnings=warnings
        )
        
    def _calculate_correlation_risk(self, positions: Dict[str, float]) -> float:
        """Calculate correlation risk score."""
        if len(positions) < 2 or self.correlation_matrix.empty:
            return 0
            
        position_symbols = list(positions.keys())
        correlation_scores = []
        
        for i, symbol1 in enumerate(position_symbols):
            for symbol2 in position_symbols[i+1:]:
                if symbol1 in self.correlation_matrix and symbol2 in self.correlation_matrix:
                    corr = self.correlation_matrix.loc[symbol1, symbol2]
                    if not np.isnan(corr):
                        correlation_scores.append(abs(corr))
                        
        return max(correlation_scores) if correlation_scores else 0
        
    def filter_signals_by_risk(
        self,
        signals: List[Signal],
        current_positions: Dict[str, float],
        market_prices: Dict[str, float],
        account_value: float
    ) -> Tuple[List[Signal], List[str]]:
        """Filter signals based on risk constraints."""
        filtered_signals = []
        rejected_reasons = []
        
        # Calculate current risk metrics
        current_equity = account_value
        risk_metrics = self.calculate_risk_metrics(
            current_equity, current_positions, market_prices, account_value
        )
        
        # If risk is extreme, only allow closing positions
        if risk_metrics.risk_level == RiskLevel.EXTREME:
            for signal in signals:
                if signal.signal_type == SignalType.SELL:
                    filtered_signals.append(signal)
                else:
                    rejected_reasons.append(
                        f"{signal.symbol}: Rejected due to extreme risk level"
                    )
            return filtered_signals, rejected_reasons
            
        # Check each signal
        for signal in signals:
            accept_signal = True
            
            # Simulate position after signal
            simulated_positions = current_positions.copy()
            if signal.signal_type == SignalType.BUY:
                simulated_positions[signal.symbol] = simulated_positions.get(signal.symbol, 0) + (signal.quantity or 0)
            elif signal.signal_type == SignalType.SELL:
                simulated_positions[signal.symbol] = simulated_positions.get(signal.symbol, 0) - (signal.quantity or 0)
                
            # Check concentration
            if signal.signal_type == SignalType.BUY:
                position_value = simulated_positions.get(signal.symbol, 0) * market_prices.get(signal.symbol, 1)
                if position_value / account_value > self.max_concentration:
                    accept_signal = False
                    rejected_reasons.append(
                        f"{signal.symbol}: Would exceed concentration limit"
                    )
                    
            # Check correlation for new positions
            if signal.signal_type == SignalType.BUY and signal.symbol not in current_positions:
                correlation_risk = self._calculate_correlation_with_portfolio(
                    signal.symbol, current_positions
                )
                if correlation_risk > self.max_correlation:
                    accept_signal = False
                    rejected_reasons.append(
                        f"{signal.symbol}: Correlation too high ({correlation_risk:.2f})"
                    )
                    
            # Check if signal would worsen drawdown
            if risk_metrics.current_drawdown < -self.max_drawdown * 0.8:
                if signal.signal_type == SignalType.BUY:
                    accept_signal = False
                    rejected_reasons.append(
                        f"{signal.symbol}: Near max drawdown, reducing risk"
                    )
                    
            if accept_signal:
                filtered_signals.append(signal)
                
        return filtered_signals, rejected_reasons
        
    def _calculate_correlation_with_portfolio(
        self,
        symbol: str,
        current_positions: Dict[str, float]
    ) -> float:
        """Calculate maximum correlation of symbol with current portfolio."""
        if not current_positions or self.correlation_matrix.empty:
            return 0
            
        if symbol not in self.correlation_matrix:
            return 0
            
        correlations = []
        for position_symbol in current_positions:
            if position_symbol in self.correlation_matrix:
                corr = self.correlation_matrix.loc[symbol, position_symbol]
                if not np.isnan(corr):
                    correlations.append(abs(corr))
                    
        return max(correlations) if correlations else 0
        
    def suggest_position_sizes(
        self,
        signals: List[Signal],
        account_value: float,
        market_prices: Dict[str, float],
        current_positions: Dict[str, float]
    ) -> Dict[str, float]:
        """Suggest position sizes based on risk budget."""
        suggestions = {}
        
        # Calculate available risk budget
        risk_metrics = self.calculate_risk_metrics(
            account_value, current_positions, market_prices, account_value
        )
        
        # Adjust position sizes based on risk level
        risk_multiplier = {
            RiskLevel.LOW: 1.0,
            RiskLevel.MEDIUM: 0.7,
            RiskLevel.HIGH: 0.3,
            RiskLevel.EXTREME: 0.0
        }[risk_metrics.risk_level]
        
        for signal in signals:
            if signal.signal_type != SignalType.BUY:
                continue
                
            base_size = account_value * 0.02  # 2% base position
            
            # Adjust for signal strength
            size = base_size * signal.strength
            
            # Adjust for risk level
            size *= risk_multiplier
            
            # Adjust for correlation
            if signal.symbol in self.returns_history.columns:
                correlation_factor = 1 - self._calculate_correlation_with_portfolio(
                    signal.symbol, current_positions
                )
                size *= correlation_factor
                
            # Convert to shares
            price = market_prices.get(signal.symbol, 1)
            quantity = size / price
            
            suggestions[signal.symbol] = round(quantity, 2)
            
        return suggestions
        
    def get_risk_report(self) -> Dict[str, Any]:
        """Generate comprehensive risk report."""
        report = {
            "limits": {
                "max_drawdown": self.max_drawdown,
                "max_correlation": self.max_correlation,
                "max_var_95": self.max_var_95,
                "max_leverage": self.max_leverage,
                "max_concentration": self.max_concentration
            },
            "correlation_matrix": self.correlation_matrix.to_dict() if not self.correlation_matrix.empty else {},
            "historical_drawdowns": self._calculate_drawdown_stats(),
            "var_analysis": self._calculate_var_stats()
        }
        
        return report
        
    def _calculate_drawdown_stats(self) -> Dict[str, float]:
        """Calculate drawdown statistics."""
        if len(self.equity_history) < 2:
            return {}
            
        equity_series = pd.Series(self.equity_history)
        peaks = equity_series.expanding().max()
        drawdowns = (equity_series - peaks) / peaks
        
        return {
            "current": float(drawdowns.iloc[-1]),
            "max": float(drawdowns.min()),
            "avg": float(drawdowns[drawdowns < 0].mean()) if len(drawdowns[drawdowns < 0]) > 0 else 0,
            "duration_days": len(drawdowns[drawdowns < 0])
        }
        
    def _calculate_var_stats(self) -> Dict[str, float]:
        """Calculate VaR statistics."""
        if self.returns_history.empty:
            return {}
            
        portfolio_returns = self.returns_history.mean(axis=1)
        
        return {
            "var_95": float(np.percentile(portfolio_returns, 5)),
            "var_99": float(np.percentile(portfolio_returns, 1)),
            "cvar_95": float(portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, 5)].mean()),
            "worst_day": float(portfolio_returns.min()),
            "volatility": float(portfolio_returns.std() * np.sqrt(252))
        }