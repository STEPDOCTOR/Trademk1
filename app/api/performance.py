"""Performance monitoring API endpoints."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import dependencies
from app.db.postgres import get_session
from app.models.trade_history import TradeHistory
from app.models.performance_metrics import DailyPerformance, RealtimeMetrics
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.performance_tracker import performance_tracker

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


@router.get("/realtime")
async def get_realtime_performance(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get real-time performance metrics."""
    metrics = await performance_tracker.get_realtime_metrics()
    
    # Check daily limits
    if metrics.get("realized_pnl"):
        limit_status = await performance_tracker.check_daily_limits(metrics["realized_pnl"])
        metrics["limit_status"] = limit_status
    
    return metrics


@router.get("/daily/{trading_date}")
async def get_daily_performance(
    trading_date: date,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get performance metrics for a specific day."""
    perf = await performance_tracker.get_daily_performance(trading_date)
    
    if not perf:
        # Try to calculate it
        perf = await performance_tracker.calculate_daily_performance(trading_date)
        if not perf:
            raise HTTPException(status_code=404, detail=f"No trades found for {trading_date}")
    
    return {
        "date": perf.trading_date.isoformat(),
        "total_trades": perf.total_trades,
        "winning_trades": perf.winning_trades,
        "losing_trades": perf.losing_trades,
        "win_rate": perf.win_rate,
        "total_pnl": perf.total_profit_loss,
        "best_trade": perf.best_trade,
        "worst_trade": perf.worst_trade,
        "average_win": perf.average_win,
        "average_loss": perf.average_loss,
        "total_volume": perf.total_volume_traded,
        "profit_factor": perf.profit_factor,
        "trades_by_strategy": perf.trades_by_strategy,
        "pnl_by_strategy": perf.pnl_by_strategy
    }


@router.get("/daily")
async def get_daily_performance_range(
    start_date: Optional[date] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[date] = Query(None, description="End date (default: today)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get daily performance for a date range."""
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    performances = await session.scalars(
        select(DailyPerformance)
        .where(
            DailyPerformance.trading_date >= start_date,
            DailyPerformance.trading_date <= end_date
        )
        .order_by(DailyPerformance.trading_date)
    )
    
    return [
        {
            "date": perf.trading_date.isoformat(),
            "total_trades": perf.total_trades,
            "win_rate": perf.win_rate,
            "total_pnl": perf.total_profit_loss,
            "total_volume": perf.total_volume_traded,
            "profit_factor": perf.profit_factor
        }
        for perf in performances
    ]


@router.get("/trades/recent")
async def get_recent_trades(
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get recent trade history."""
    query = select(TradeHistory).order_by(desc(TradeHistory.executed_at)).limit(limit)
    
    if symbol:
        query = query.where(TradeHistory.symbol == symbol)
    
    trades = await session.scalars(query)
    
    return [
        {
            "id": str(trade.id),
            "executed_at": trade.executed_at.isoformat(),
            "symbol": trade.symbol,
            "type": trade.trade_type.value,
            "quantity": trade.quantity,
            "price": trade.price,
            "total_value": trade.total_value,
            "reason": trade.reason.value,
            "strategy": trade.strategy_name,
            "profit_loss": trade.profit_loss,
            "profit_loss_pct": trade.profit_loss_pct
        }
        for trade in trades
    ]


@router.get("/summary")
async def get_performance_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to summarize"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get performance summary for the specified period."""
    start_date = date.today() - timedelta(days=days)
    
    # Get all daily performances
    performances = await session.scalars(
        select(DailyPerformance)
        .where(DailyPerformance.trading_date >= start_date)
    )
    perf_list = list(performances)
    
    if not perf_list:
        return {
            "period_days": days,
            "total_trades": 0,
            "total_pnl": 0,
            "win_rate": 0,
            "best_day": 0,
            "worst_day": 0,
            "trading_days": 0,
            "message": "No trading data available for this period"
        }
    
    # Calculate summary statistics
    total_trades = sum(p.total_trades for p in perf_list)
    total_wins = sum(p.winning_trades for p in perf_list)
    total_pnl = sum(p.total_profit_loss for p in perf_list)
    total_volume = sum(p.total_volume_traded for p in perf_list)
    
    daily_pnls = [p.total_profit_loss for p in perf_list]
    positive_days = sum(1 for pnl in daily_pnls if pnl > 0)
    
    # Strategy breakdown
    all_trades_by_strategy = {}
    all_pnl_by_strategy = {}
    
    for perf in perf_list:
        if perf.trades_by_strategy:
            for strategy, count in perf.trades_by_strategy.items():
                all_trades_by_strategy[strategy] = all_trades_by_strategy.get(strategy, 0) + count
        
        if perf.pnl_by_strategy:
            for strategy, pnl in perf.pnl_by_strategy.items():
                all_pnl_by_strategy[strategy] = all_pnl_by_strategy.get(strategy, 0) + pnl
    
    # Calculate Sharpe ratio (simplified)
    if len(daily_pnls) > 1:
        import numpy as np
        returns = np.array(daily_pnls)
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    else:
        sharpe = 0
    
    return {
        "period_days": days,
        "trading_days": len(perf_list),
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 2),
        "total_volume": round(total_volume, 2),
        "average_daily_pnl": round(total_pnl / len(perf_list), 2) if perf_list else 0,
        "win_rate": round((total_wins / total_trades * 100), 2) if total_trades > 0 else 0,
        "win_days": positive_days,
        "loss_days": len(perf_list) - positive_days,
        "best_day": round(max(daily_pnls), 2) if daily_pnls else 0,
        "worst_day": round(min(daily_pnls), 2) if daily_pnls else 0,
        "sharpe_ratio": round(sharpe, 2),
        "trades_by_strategy": all_trades_by_strategy,
        "pnl_by_strategy": {k: round(v, 2) for k, v in all_pnl_by_strategy.items()}
    }


@router.get("/alerts")
async def get_performance_alerts(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get current performance alerts and warnings."""
    alerts = []
    
    # Get realtime metrics
    metrics = await performance_tracker.get_realtime_metrics()
    
    if metrics.get("realized_pnl"):
        # Check daily limits
        limit_status = await performance_tracker.check_daily_limits(metrics["realized_pnl"])
        
        if limit_status["loss_limit_hit"]:
            alerts.append({
                "level": "critical",
                "type": "daily_loss_limit",
                "message": f"Daily loss limit hit! Current loss: ${limit_status['current_pnl']:.2f}",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "Trading should be stopped for the day"
            })
        elif limit_status["pct_to_loss_limit"] > 80:
            alerts.append({
                "level": "warning",
                "type": "approaching_loss_limit",
                "message": f"Approaching daily loss limit: {limit_status['pct_to_loss_limit']:.1f}% of limit",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "Consider reducing position sizes"
            })
        
        if limit_status["profit_target_hit"]:
            alerts.append({
                "level": "success",
                "type": "daily_profit_target",
                "message": f"Daily profit target reached! Profit: ${limit_status['current_pnl']:.2f}",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "Consider stopping for the day to lock in profits"
            })
    
    # Check win rate
    if metrics.get("trades_today", 0) > 10:
        win_rate = (metrics.get("winning_trades_today", 0) / metrics["trades_today"] * 100)
        if win_rate < 30:
            alerts.append({
                "level": "warning",
                "type": "low_win_rate",
                "message": f"Low win rate today: {win_rate:.1f}%",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "Review strategy parameters"
            })
    
    # Check position concentration
    if metrics.get("open_positions", 0) > 20:
        alerts.append({
            "level": "info",
            "type": "high_position_count",
            "message": f"High number of open positions: {metrics['open_positions']}",
            "timestamp": datetime.utcnow().isoformat(),
            "action": "Monitor risk exposure carefully"
        })
    
    return alerts


@router.post("/calculate-daily/{trading_date}")
async def calculate_daily_performance(
    trading_date: date,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually trigger daily performance calculation."""
    perf = await performance_tracker.calculate_daily_performance(trading_date)
    
    if not perf:
        raise HTTPException(status_code=404, detail=f"No trades found for {trading_date}")
    
    return {
        "message": f"Daily performance calculated for {trading_date}",
        "total_trades": perf.total_trades,
        "total_pnl": perf.total_profit_loss,
        "win_rate": perf.win_rate
    }