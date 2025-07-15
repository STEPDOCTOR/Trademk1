"""Portfolio tracking and analytics API endpoints."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, AuthUser
from app.db.postgres import get_db
from app.services.portfolio_analytics import PortfolioAnalytics, PerformanceMetrics, PortfolioSnapshot, AssetAllocation
from app.services.cache import cache_service, cache_result
from app.monitoring.metrics import timer

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


# Response models
class PerformanceMetricsResponse(BaseModel):
    """Portfolio performance metrics response."""
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
    period_start: datetime
    period_end: datetime


class PositionResponse(BaseModel):
    """Portfolio position response."""
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percentage: float
    last_updated: datetime


class PortfolioSnapshotResponse(BaseModel):
    """Portfolio snapshot response."""
    timestamp: datetime
    total_value: float
    cash_balance: float
    positions_value: float
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    positions: List[PositionResponse]


class AssetAllocationResponse(BaseModel):
    """Asset allocation response."""
    symbol: str
    market_value: float
    percentage: float
    shares: float
    avg_cost: float
    unrealized_pnl: float
    unrealized_pnl_percentage: float


class PerformanceAttributionResponse(BaseModel):
    """Performance attribution response."""
    symbol_performance: Dict[str, Any]
    total_attribution: float
    period_start: datetime
    period_end: datetime


class PortfolioSummaryResponse(BaseModel):
    """Portfolio summary response."""
    current_value: float
    daily_change: float
    daily_change_percentage: float
    total_return: float
    total_return_percentage: float
    positions_count: int
    largest_position: Optional[str]
    largest_position_percentage: Optional[float]


# Initialize analytics service
portfolio_analytics = PortfolioAnalytics()


@router.get("/summary", response_model=PortfolioSummaryResponse)
@cache_result(expire=60, key_prefix="portfolio_summary")
async def get_portfolio_summary(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio summary overview."""
    with timer("portfolio.summary.duration", tags={"user_id": str(current_user.user_id)}):
        # Get current snapshot
        snapshot = await portfolio_analytics.get_portfolio_snapshot(db, current_user.user_id)
        
        # Get asset allocation to find largest position
        allocations = await portfolio_analytics.get_asset_allocation(db, current_user.user_id)
        
        largest_position = None
        largest_position_pct = None
        if allocations:
            largest = max(allocations, key=lambda x: abs(x.percentage))
            largest_position = largest.symbol
            largest_position_pct = largest.percentage
            
        # Calculate daily change percentage
        daily_change_pct = 0.0
        if snapshot.total_value > 0 and snapshot.daily_pnl != 0:
            daily_change_pct = (snapshot.daily_pnl / snapshot.total_value) * 100
            
        # Get basic performance metrics (last 30 days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        metrics = await portfolio_analytics.get_portfolio_performance(
            db, current_user.user_id, start_date, end_date
        )
        
        return PortfolioSummaryResponse(
            current_value=snapshot.total_value,
            daily_change=snapshot.daily_pnl,
            daily_change_percentage=daily_change_pct,
            total_return=metrics.total_return,
            total_return_percentage=metrics.total_return_percentage,
            positions_count=len(snapshot.positions),
            largest_position=largest_position,
            largest_position_percentage=largest_position_pct
        )


@router.get("/snapshot", response_model=PortfolioSnapshotResponse)
@cache_result(expire=30, key_prefix="portfolio_snapshot")
async def get_portfolio_snapshot(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current portfolio snapshot."""
    with timer("portfolio.snapshot.duration", tags={"user_id": str(current_user.user_id)}):
        snapshot = await portfolio_analytics.get_portfolio_snapshot(db, current_user.user_id)
        
        positions = [
            PositionResponse(**pos) for pos in snapshot.positions
        ]
        
        return PortfolioSnapshotResponse(
            timestamp=snapshot.timestamp,
            total_value=snapshot.total_value,
            cash_balance=snapshot.cash_balance,
            positions_value=snapshot.positions_value,
            unrealized_pnl=snapshot.unrealized_pnl,
            realized_pnl=snapshot.realized_pnl,
            daily_pnl=snapshot.daily_pnl,
            positions=positions
        )


@router.get("/allocation", response_model=List[AssetAllocationResponse])
@cache_result(expire=60, key_prefix="portfolio_allocation")
async def get_asset_allocation(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current asset allocation breakdown."""
    with timer("portfolio.allocation.duration", tags={"user_id": str(current_user.user_id)}):
        allocations = await portfolio_analytics.get_asset_allocation(db, current_user.user_id)
        
        return [
            AssetAllocationResponse(
                symbol=alloc.symbol,
                market_value=alloc.market_value,
                percentage=alloc.percentage,
                shares=alloc.shares,
                avg_cost=alloc.avg_cost,
                unrealized_pnl=alloc.unrealized_pnl,
                unrealized_pnl_percentage=alloc.unrealized_pnl_percentage
            )
            for alloc in allocations
        ]


@router.get("/performance", response_model=PerformanceMetricsResponse)
@cache_result(expire=300, key_prefix="portfolio_performance")
async def get_portfolio_performance(
    period_days: int = Query(365, ge=7, le=3650, description="Performance period in days"),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio performance metrics for specified period."""
    with timer("portfolio.performance.duration", tags={
        "user_id": str(current_user.user_id),
        "period_days": str(period_days)
    }):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)
        
        metrics = await portfolio_analytics.get_portfolio_performance(
            db, current_user.user_id, start_date, end_date
        )
        
        return PerformanceMetricsResponse(
            **metrics.__dict__,
            period_start=start_date,
            period_end=end_date
        )


@router.get("/attribution", response_model=PerformanceAttributionResponse)
@cache_result(expire=300, key_prefix="portfolio_attribution")
async def get_performance_attribution(
    period_days: int = Query(30, ge=7, le=365, description="Attribution period in days"),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get performance attribution by asset."""
    with timer("portfolio.attribution.duration", tags={
        "user_id": str(current_user.user_id),
        "period_days": str(period_days)
    }):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)
        
        attribution = await portfolio_analytics.get_performance_attribution(
            db, current_user.user_id, start_date, end_date
        )
        
        # Calculate total attribution
        total_attribution = sum(
            data.get('total_pnl', 0) for data in attribution.values()
        )
        
        return PerformanceAttributionResponse(
            symbol_performance=attribution,
            total_attribution=total_attribution,
            period_start=start_date,
            period_end=end_date
        )


@router.get("/analytics/risk-metrics")
@cache_result(expire=300, key_prefix="portfolio_risk_metrics")
async def get_risk_metrics(
    period_days: int = Query(365, ge=30, le=3650, description="Risk analysis period in days"),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed risk analytics."""
    with timer("portfolio.risk_metrics.duration", tags={
        "user_id": str(current_user.user_id),
        "period_days": str(period_days)
    }):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)
        
        # Get performance metrics
        metrics = await portfolio_analytics.get_portfolio_performance(
            db, current_user.user_id, start_date, end_date
        )
        
        # Get current allocation for concentration risk
        allocations = await portfolio_analytics.get_asset_allocation(db, current_user.user_id)
        
        # Calculate concentration metrics
        concentration_risk = "Low"
        max_position_pct = 0.0
        if allocations:
            max_position_pct = max(alloc.percentage for alloc in allocations)
            if max_position_pct > 50:
                concentration_risk = "High"
            elif max_position_pct > 30:
                concentration_risk = "Medium"
                
        # Risk assessment
        risk_level = "Low"
        if metrics.volatility > 25:
            risk_level = "High"
        elif metrics.volatility > 15:
            risk_level = "Medium"
            
        return {
            "risk_level": risk_level,
            "volatility": metrics.volatility,
            "max_drawdown": metrics.max_drawdown,
            "sharpe_ratio": metrics.sharpe_ratio,
            "sortino_ratio": metrics.sortino_ratio,
            "beta": metrics.beta,
            "concentration_risk": concentration_risk,
            "max_position_percentage": max_position_pct,
            "total_positions": len(allocations),
            "period_start": start_date,
            "period_end": end_date
        }


@router.get("/analytics/returns-distribution")
@cache_result(expire=300, key_prefix="portfolio_returns_distribution")
async def get_returns_distribution(
    period_days: int = Query(365, ge=30, le=3650, description="Analysis period in days"),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get returns distribution analysis."""
    with timer("portfolio.returns_distribution.duration", tags={
        "user_id": str(current_user.user_id),
        "period_days": str(period_days)
    }):
        # This is a placeholder for returns distribution analysis
        # In a real implementation, you'd calculate actual return distributions
        
        return {
            "mean_return": 0.08,
            "median_return": 0.06,
            "std_deviation": 0.15,
            "skewness": -0.2,
            "kurtosis": 3.1,
            "var_95": -0.12,  # Value at Risk (95% confidence)
            "var_99": -0.18,  # Value at Risk (99% confidence)
            "positive_days_percentage": 55.0,
            "best_day_return": 0.08,
            "worst_day_return": -0.06,
            "period_days": period_days
        }


@router.post("/refresh")
async def refresh_portfolio_cache(
    current_user: AuthUser = Depends(get_current_user)
):
    """Refresh portfolio cache for current user."""
    try:
        await cache_service.connect()
        
        # Clear user-specific portfolio cache
        await cache_service.flush_pattern(f"*portfolio*{current_user.user_id}*")
        
        return {"message": "Portfolio cache refreshed successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh cache: {str(e)}"
        )