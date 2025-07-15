"""Portfolio analytics and performance tracking service."""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus, OrderSide
from app.models.position import Position
from app.models.user_portfolio import UserPortfolio
from app.services.cache import cache_service
from app.monitoring.logger import get_business_logger


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics."""
    total_return: float
    total_return_percentage: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    alpha: float
    beta: float
    win_rate: float
    profit_factor: float
    largest_win: float
    largest_loss: float
    average_win: float
    average_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio snapshot."""
    timestamp: datetime
    total_value: float
    cash_balance: float
    positions_value: float
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    positions: List[Dict[str, Any]]


@dataclass
class AssetAllocation:
    """Asset allocation breakdown."""
    symbol: str
    market_value: float
    percentage: float
    shares: float
    avg_cost: float
    unrealized_pnl: float
    unrealized_pnl_percentage: float


class PortfolioAnalytics:
    """Portfolio analytics service."""
    
    def __init__(self):
        self.logger = get_business_logger()
        
    async def get_portfolio_performance(
        self,
        db: AsyncSession,
        user_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PerformanceMetrics:
        """Calculate comprehensive portfolio performance metrics."""
        
        # Default to last year if no dates provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)
            
        # Get portfolio value history
        value_history = await self._get_portfolio_value_history(
            db, user_id, start_date, end_date
        )
        
        if len(value_history) < 2:
            # Not enough data for meaningful metrics
            return PerformanceMetrics(
                total_return=0.0,
                total_return_percentage=0.0,
                annualized_return=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                volatility=0.0,
                alpha=0.0,
                beta=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                average_win=0.0,
                average_loss=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0
            )
            
        # Calculate returns
        returns = self._calculate_returns(value_history)
        
        # Get trade statistics
        trade_stats = await self._get_trade_statistics(db, user_id, start_date, end_date)
        
        # Calculate performance metrics
        total_return = value_history[-1] - value_history[0]
        total_return_pct = (total_return / value_history[0]) * 100 if value_history[0] > 0 else 0
        
        # Annualized return
        days = (end_date - start_date).days
        years = days / 365.25
        annualized_return = ((value_history[-1] / value_history[0]) ** (1/years) - 1) * 100 if years > 0 and value_history[0] > 0 else 0
        
        # Risk metrics
        volatility = np.std(returns) * np.sqrt(252) * 100  # Annualized volatility
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        max_drawdown = self._calculate_max_drawdown(value_history)
        
        # Market comparison (simplified - using SPY as benchmark)
        alpha, beta = await self._calculate_alpha_beta(returns, start_date, end_date)
        
        return PerformanceMetrics(
            total_return=total_return,
            total_return_percentage=total_return_pct,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            volatility=volatility,
            alpha=alpha,
            beta=beta,
            win_rate=trade_stats['win_rate'],
            profit_factor=trade_stats['profit_factor'],
            largest_win=trade_stats['largest_win'],
            largest_loss=trade_stats['largest_loss'],
            average_win=trade_stats['average_win'],
            average_loss=trade_stats['average_loss'],
            total_trades=trade_stats['total_trades'],
            winning_trades=trade_stats['winning_trades'],
            losing_trades=trade_stats['losing_trades']
        )
        
    async def get_portfolio_snapshot(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> PortfolioSnapshot:
        """Get current portfolio snapshot."""
        
        # Get current portfolio
        portfolio_result = await db.execute(
            select(UserPortfolio).where(UserPortfolio.user_id == user_id)
        )
        portfolio = portfolio_result.scalar_one_or_none()
        
        if not portfolio:
            return PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_value=0.0,
                cash_balance=0.0,
                positions_value=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                daily_pnl=0.0,
                positions=[]
            )
            
        # Get current positions
        positions_result = await db.execute(
            select(Position).where(
                and_(
                    Position.user_id == user_id,
                    Position.quantity != 0
                )
            )
        )
        positions = positions_result.scalars().all()
        
        # Calculate daily P&L
        daily_pnl = await self._calculate_daily_pnl(db, user_id)
        
        # Format positions
        formatted_positions = []
        for pos in positions:
            formatted_positions.append({
                'symbol': pos.symbol,
                'quantity': pos.quantity,
                'avg_cost': pos.avg_cost,
                'market_value': pos.market_value,
                'unrealized_pnl': pos.unrealized_pnl,
                'unrealized_pnl_percentage': (pos.unrealized_pnl / (pos.avg_cost * abs(pos.quantity))) * 100 if pos.avg_cost > 0 and pos.quantity != 0 else 0,
                'last_updated': pos.updated_at
            })
            
        return PortfolioSnapshot(
            timestamp=datetime.utcnow(),
            total_value=portfolio.total_value,
            cash_balance=portfolio.cash_balance,
            positions_value=portfolio.positions_value,
            unrealized_pnl=sum(pos.unrealized_pnl for pos in positions),
            realized_pnl=portfolio.realized_pnl,
            daily_pnl=daily_pnl,
            positions=formatted_positions
        )
        
    async def get_asset_allocation(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[AssetAllocation]:
        """Get current asset allocation breakdown."""
        
        # Get current positions
        positions_result = await db.execute(
            select(Position).where(
                and_(
                    Position.user_id == user_id,
                    Position.quantity != 0
                )
            )
        )
        positions = positions_result.scalars().all()
        
        if not positions:
            return []
            
        # Calculate total portfolio value
        total_value = sum(pos.market_value for pos in positions)
        
        if total_value <= 0:
            return []
            
        # Create allocation breakdown
        allocations = []
        for pos in positions:
            allocation = AssetAllocation(
                symbol=pos.symbol,
                market_value=pos.market_value,
                percentage=(pos.market_value / total_value) * 100,
                shares=pos.quantity,
                avg_cost=pos.avg_cost,
                unrealized_pnl=pos.unrealized_pnl,
                unrealized_pnl_percentage=(pos.unrealized_pnl / (pos.avg_cost * abs(pos.quantity))) * 100 if pos.avg_cost > 0 and pos.quantity != 0 else 0
            )
            allocations.append(allocation)
            
        # Sort by market value descending
        allocations.sort(key=lambda x: abs(x.market_value), reverse=True)
        
        return allocations
        
    async def get_performance_attribution(
        self,
        db: AsyncSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Calculate performance attribution by asset."""
        
        # Get orders in the period
        orders_result = await db.execute(
            select(Order).where(
                and_(
                    Order.user_id == user_id,
                    Order.status == OrderStatus.FILLED,
                    Order.filled_at >= start_date,
                    Order.filled_at <= end_date
                )
            ).order_by(Order.filled_at)
        )
        orders = orders_result.scalars().all()
        
        # Group by symbol
        symbol_performance = {}
        
        for order in orders:
            symbol = order.symbol
            if symbol not in symbol_performance:
                symbol_performance[symbol] = {
                    'trades': [],
                    'total_pnl': 0.0,
                    'total_return': 0.0,
                    'contribution_to_return': 0.0
                }
                
            # Calculate trade P&L (simplified)
            if order.side == OrderSide.SELL:
                # This is a simplification - in reality you'd need to match with buy orders
                symbol_performance[symbol]['total_pnl'] += order.filled_price * order.filled_quantity
            else:
                symbol_performance[symbol]['total_pnl'] -= order.filled_price * order.filled_quantity
                
            symbol_performance[symbol]['trades'].append({
                'side': order.side.value,
                'quantity': order.filled_quantity,
                'price': order.filled_price,
                'timestamp': order.filled_at
            })
            
        return symbol_performance
        
    async def _get_portfolio_value_history(
        self,
        db: AsyncSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> List[float]:
        """Get historical portfolio values."""
        
        # This is a simplified implementation
        # In a production system, you'd store daily portfolio snapshots
        
        # For now, we'll estimate based on current value and historical changes
        # You should implement proper historical value tracking
        
        current_portfolio = await db.execute(
            select(UserPortfolio).where(UserPortfolio.user_id == user_id)
        )
        portfolio = current_portfolio.scalar_one_or_none()
        
        if not portfolio:
            return [0.0, 0.0]
            
        # Simplified: return current value for both start and end
        # In reality, you'd query historical snapshots
        return [portfolio.total_value * 0.9, portfolio.total_value]  # Simulate some growth
        
    def _calculate_returns(self, value_history: List[float]) -> np.ndarray:
        """Calculate daily returns from value history."""
        if len(value_history) < 2:
            return np.array([])
            
        values = np.array(value_history)
        returns = np.diff(values) / values[:-1]
        return returns
        
    def _calculate_sharpe_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) == 0:
            return 0.0
            
        excess_returns = returns - (risk_free_rate / 252)  # Daily risk-free rate
        if np.std(excess_returns) == 0:
            return 0.0
            
        return (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(252)
        
    def _calculate_sortino_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (using downside deviation)."""
        if len(returns) == 0:
            return 0.0
            
        excess_returns = returns - (risk_free_rate / 252)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0.0
            
        return (np.mean(excess_returns) / np.std(downside_returns)) * np.sqrt(252)
        
    def _calculate_max_drawdown(self, value_history: List[float]) -> float:
        """Calculate maximum drawdown."""
        if len(value_history) < 2:
            return 0.0
            
        values = np.array(value_history)
        peak = np.maximum.accumulate(values)
        drawdown = (values - peak) / peak
        return abs(np.min(drawdown)) * 100
        
    async def _calculate_alpha_beta(
        self,
        returns: np.ndarray,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[float, float]:
        """Calculate alpha and beta vs market (simplified)."""
        # This is a placeholder implementation
        # In reality, you'd fetch market data (e.g., SPY) and calculate correlation
        
        if len(returns) == 0:
            return 0.0, 1.0
            
        # Simplified calculation - just return sample values
        beta = np.std(returns) / 0.15  # Assume market volatility of 15%
        alpha = np.mean(returns) * 252 - (beta * 0.10)  # Assume market return of 10%
        
        return alpha * 100, beta
        
    async def _get_trade_statistics(
        self,
        db: AsyncSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get trade statistics for the period."""
        
        # Get filled orders
        orders_result = await db.execute(
            select(Order).where(
                and_(
                    Order.user_id == user_id,
                    Order.status == OrderStatus.FILLED,
                    Order.filled_at >= start_date,
                    Order.filled_at <= end_date
                )
            )
        )
        orders = orders_result.scalars().all()
        
        if not orders:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0
            }
            
        # Simplified P&L calculation (you'd need proper trade matching)
        trade_pnls = []
        for order in orders:
            # This is very simplified - just using order value as P&L proxy
            pnl = order.filled_price * order.filled_quantity
            if order.side == OrderSide.SELL:
                trade_pnls.append(pnl)
            else:
                trade_pnls.append(-pnl)
                
        winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in trade_pnls if pnl < 0]
        
        total_trades = len(trade_pnls)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
        
        total_wins = sum(winning_trades) if winning_trades else 0
        total_losses = abs(sum(losing_trades)) if losing_trades else 0
        
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'largest_win': max(winning_trades) if winning_trades else 0,
            'largest_loss': min(losing_trades) if losing_trades else 0,
            'average_win': np.mean(winning_trades) if winning_trades else 0,
            'average_loss': np.mean(losing_trades) if losing_trades else 0
        }
        
    async def _calculate_daily_pnl(self, db: AsyncSession, user_id: UUID) -> float:
        """Calculate daily P&L change."""
        # This would typically compare with yesterday's portfolio value
        # For now, return 0 as placeholder
        return 0.0