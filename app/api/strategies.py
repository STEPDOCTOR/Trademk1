"""Strategy management and backtesting API endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.db.postgres import get_db
from app.services.strategies.base import StrategyConfig
from app.services.strategies.sma_crossover import SMACrossoverStrategy
from app.services.strategies.momentum import MomentumStrategy
from app.services.strategies.backtest import BacktestEngine
from app.services.strategies.portfolio_manager import MultiStrategyPortfolioManager
from app.services.strategies.performance import PerformanceAnalyzer, MetricPeriod


router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


# Global portfolio manager instance (in production, this would be managed differently)
portfolio_manager = MultiStrategyPortfolioManager()


class StrategyCreateRequest(BaseModel):
    """Request to create a new strategy."""
    strategy_type: str = Field(..., description="Strategy type: sma_crossover, momentum")
    name: str = Field(..., description="Strategy name")
    symbols: List[str] = Field(..., description="List of symbols to trade")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    risk_parameters: Dict[str, Any] = Field(default_factory=dict, description="Risk parameters")
    allocation: float = Field(default=0.25, ge=0.0, le=1.0, description="Portfolio allocation")


class BacktestRequest(BaseModel):
    """Request to run a backtest."""
    strategy_id: str = Field(..., description="Strategy ID to backtest")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: float = Field(default=100000, description="Initial capital")
    

class StrategyResponse(BaseModel):
    """Strategy information response."""
    strategy_id: str
    name: str
    type: str
    symbols: List[str]
    enabled: bool
    parameters: Dict[str, Any]
    risk_parameters: Dict[str, Any]
    allocation: float
    performance_score: float
    

class BacktestResponse(BaseModel):
    """Backtest result summary."""
    backtest_id: str
    strategy_id: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    

class PerformanceResponse(BaseModel):
    """Performance metrics response."""
    strategy_id: str
    period: str
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    

class RiskMetricsResponse(BaseModel):
    """Current risk metrics."""
    timestamp: datetime
    risk_level: str
    current_drawdown: float
    var_95: float
    total_exposure: float
    leverage_ratio: float
    warnings: List[str]


@router.post("/create", response_model=StrategyResponse)
async def create_strategy(request: StrategyCreateRequest):
    """Create and add a new strategy to the portfolio."""
    # Generate strategy ID
    strategy_id = f"{request.strategy_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Create strategy config
    config = StrategyConfig(
        strategy_id=strategy_id,
        name=request.name,
        symbols=request.symbols,
        parameters=request.parameters,
        risk_parameters=request.risk_parameters
    )
    
    # Create strategy instance based on type
    if request.strategy_type == "sma_crossover":
        strategy = SMACrossoverStrategy(config)
    elif request.strategy_type == "momentum":
        strategy = MomentumStrategy(config)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy type: {request.strategy_type}"
        )
        
    # Validate parameters
    is_valid, error_msg = strategy.validate_parameters()
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
        
    # Add to portfolio manager
    portfolio_manager.add_strategy(strategy, request.allocation)
    
    return StrategyResponse(
        strategy_id=strategy_id,
        name=request.name,
        type=request.strategy_type,
        symbols=request.symbols,
        enabled=True,
        parameters=request.parameters,
        risk_parameters=request.risk_parameters,
        allocation=request.allocation,
        performance_score=0.5  # Initial neutral score
    )


@router.get("/list", response_model=List[StrategyResponse])
async def list_strategies():
    """List all strategies in the portfolio."""
    strategies = []
    
    for strategy_id, allocation in portfolio_manager.strategies.items():
        strategy = allocation.strategy
        strategies.append(StrategyResponse(
            strategy_id=strategy_id,
            name=strategy.name,
            type=strategy.__class__.__name__.replace("Strategy", "").lower(),
            symbols=strategy.symbols,
            enabled=allocation.enabled,
            parameters=strategy.parameters,
            risk_parameters=strategy.risk_parameters,
            allocation=allocation.allocation,
            performance_score=allocation.performance_score
        ))
        
    return strategies


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str):
    """Get details of a specific strategy."""
    if strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    allocation = portfolio_manager.strategies[strategy_id]
    strategy = allocation.strategy
    
    return StrategyResponse(
        strategy_id=strategy_id,
        name=strategy.name,
        type=strategy.__class__.__name__.replace("Strategy", "").lower(),
        symbols=strategy.symbols,
        enabled=allocation.enabled,
        parameters=strategy.parameters,
        risk_parameters=strategy.risk_parameters,
        allocation=allocation.allocation,
        performance_score=allocation.performance_score
    )


@router.put("/{strategy_id}/enable")
async def enable_strategy(strategy_id: str, enabled: bool = True):
    """Enable or disable a strategy."""
    if strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    portfolio_manager.strategies[strategy_id].enabled = enabled
    
    return {"status": "success", "enabled": enabled}


@router.put("/{strategy_id}/allocation")
async def update_allocation(strategy_id: str, allocation: float = Query(..., ge=0.0, le=1.0)):
    """Update strategy allocation."""
    if strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    portfolio_manager.strategies[strategy_id].allocation = allocation
    portfolio_manager._normalize_allocations()
    
    return {"status": "success", "allocation": allocation}


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """Remove a strategy from the portfolio."""
    if strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    portfolio_manager.remove_strategy(strategy_id)
    
    return {"status": "success", "message": f"Strategy {strategy_id} removed"}


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Run a backtest for a strategy."""
    if request.strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    strategy = portfolio_manager.strategies[request.strategy_id].strategy
    
    # In a real implementation, we would fetch historical data from QuestDB
    # For now, create sample data
    market_data = pd.DataFrame()  # Would fetch from QuestDB
    
    # Run backtest
    engine = BacktestEngine(initial_capital=request.initial_capital)
    
    # This would be async in production
    result = await engine.run_backtest(
        strategy,
        market_data,
        request.start_date,
        request.end_date
    )
    
    return BacktestResponse(
        backtest_id=result.metrics.get('backtest_id', 'test'),
        strategy_id=request.strategy_id,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        final_capital=result.final_capital,
        total_return=result.metrics['total_return'],
        sharpe_ratio=result.metrics['sharpe_ratio'],
        max_drawdown=result.metrics['max_drawdown'],
        total_trades=result.metrics['total_trades'],
        win_rate=result.metrics['win_rate']
    )


@router.get("/performance/{strategy_id}", response_model=PerformanceResponse)
async def get_performance(
    strategy_id: str,
    period: MetricPeriod = Query(default=MetricPeriod.MONTHLY)
):
    """Get performance metrics for a strategy."""
    if strategy_id not in portfolio_manager.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    # In production, would fetch actual performance data
    # For now, return sample metrics
    return PerformanceResponse(
        strategy_id=strategy_id,
        period=period.value,
        total_return=0.15,  # 15%
        annualized_return=0.18,
        volatility=0.12,
        sharpe_ratio=1.5,
        max_drawdown=-0.08,
        win_rate=0.58,
        total_trades=45
    )


@router.get("/portfolio/status", response_model=Dict[str, Any])
async def get_portfolio_status():
    """Get current portfolio status."""
    status = await portfolio_manager.get_status()
    return status


@router.get("/portfolio/risk", response_model=RiskMetricsResponse)
async def get_risk_metrics():
    """Get current portfolio risk metrics."""
    # Get from Redis cache
    import redis.asyncio as redis
    from app.config.settings import get_settings
    import json
    
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        metrics_data = await redis_client.get('portfolio:risk_metrics')
        if metrics_data:
            metrics = json.loads(metrics_data)
            return RiskMetricsResponse(
                timestamp=datetime.fromisoformat(metrics['timestamp']),
                risk_level=metrics['risk_level'],
                current_drawdown=metrics['current_drawdown'],
                var_95=metrics['var_95'],
                total_exposure=metrics['total_exposure'],
                leverage_ratio=metrics['leverage_ratio'],
                warnings=metrics['warnings']
            )
        else:
            # Return default if no metrics available
            return RiskMetricsResponse(
                timestamp=datetime.utcnow(),
                risk_level="low",
                current_drawdown=0.0,
                var_95=0.0,
                total_exposure=0.0,
                leverage_ratio=0.0,
                warnings=[]
            )
    finally:
        await redis_client.close()


@router.post("/portfolio/rebalance")
async def trigger_rebalance():
    """Manually trigger portfolio rebalancing."""
    await portfolio_manager._rebalance_allocations()
    return {"status": "success", "message": "Rebalancing triggered"}


@router.get("/signals/recent", response_model=List[Dict[str, Any]])
async def get_recent_signals(limit: int = Query(default=50, le=200)):
    """Get recent signals from all strategies."""
    all_signals = []
    
    for strategy_id, allocation in portfolio_manager.strategies.items():
        for signal in allocation.recent_signals[-limit:]:
            all_signals.append({
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "strength": signal.strength,
                "timestamp": signal.timestamp.isoformat(),
                "reason": signal.reason
            })
            
    # Sort by timestamp
    all_signals.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return all_signals[:limit]