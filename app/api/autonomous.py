"""API endpoints for autonomous trading control."""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, AuthUser
from app.services.strategies.autonomous_trader import StrategyType
from app import dependencies
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Autonomous Trading"])


class StrategyConfig(BaseModel):
    """Strategy configuration update."""
    enabled: Optional[bool] = None
    position_size_pct: Optional[float] = Field(None, ge=0.001, le=0.1)
    max_positions: Optional[int] = Field(None, ge=1, le=100)
    stop_loss_pct: Optional[float] = Field(None, ge=0.01, le=0.5)
    take_profit_pct: Optional[float] = Field(None, ge=0.01, le=1.0)
    momentum_lookback_hours: Optional[int] = Field(None, ge=1, le=168)
    momentum_threshold: Optional[float] = Field(None, ge=0.001, le=0.5)
    rebalance_threshold: Optional[float] = Field(None, ge=0.01, le=0.5)


class AutonomousStatus(BaseModel):
    """Autonomous trading status."""
    running: bool
    strategies: Dict[str, Dict[str, Any]]
    check_interval: int
    position_sync_enabled: bool


@router.get("/status", response_model=AutonomousStatus)
async def get_autonomous_status(
    current_user: AuthUser = Depends(get_current_user)
) -> AutonomousStatus:
    """Get autonomous trading system status."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    trader = dependencies.autonomous_trader
    return AutonomousStatus(
        running=trader.running,
        strategies={
            strategy_type.value: {
                "enabled": config.enabled,
                "position_size_pct": config.position_size_pct,
                "max_positions": config.max_positions,
                "stop_loss_pct": config.stop_loss_pct,
                "take_profit_pct": config.take_profit_pct,
                "momentum_lookback_hours": config.momentum_lookback_hours,
                "momentum_threshold": config.momentum_threshold,
                "rebalance_threshold": config.rebalance_threshold,
            }
            for strategy_type, config in trader.strategies.items()
        },
        check_interval=trader.check_interval,
        position_sync_enabled=dependencies.position_sync_service is not None and dependencies.position_sync_service.running
    )


@router.post("/start")
async def start_autonomous_trading(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, str]:
    """Start autonomous trading system."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    if dependencies.autonomous_trader.running:
        return {"status": "already_running", "message": "Autonomous trading is already running"}
    
    # Start in background
    import asyncio
    asyncio.create_task(dependencies.autonomous_trader.run())
    
    return {"status": "started", "message": "Autonomous trading system started"}


@router.post("/stop")
async def stop_autonomous_trading(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, str]:
    """Stop autonomous trading system."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    await dependencies.autonomous_trader.stop()
    return {"status": "stopped", "message": "Autonomous trading system stopped"}


@router.patch("/strategy/{strategy_type}")
async def update_strategy_config(
    strategy_type: StrategyType,
    config: StrategyConfig,
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Update strategy configuration."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    # Update configuration
    config_dict = config.dict(exclude_none=True)
    dependencies.autonomous_trader.update_strategy(strategy_type, **config_dict)
    
    # Return updated configuration
    updated_config = dependencies.autonomous_trader.strategies[strategy_type]
    return {
        "strategy": strategy_type.value,
        "updated": True,
        "config": {
            "enabled": updated_config.enabled,
            "position_size_pct": updated_config.position_size_pct,
            "max_positions": updated_config.max_positions,
            "stop_loss_pct": updated_config.stop_loss_pct,
            "take_profit_pct": updated_config.take_profit_pct,
            "momentum_lookback_hours": updated_config.momentum_lookback_hours,
            "momentum_threshold": updated_config.momentum_threshold,
            "rebalance_threshold": updated_config.rebalance_threshold,
        }
    }


@router.post("/force-cycle")
async def force_trading_cycle(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Force an immediate trading cycle."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    if not dependencies.autonomous_trader.running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Autonomous trading system is not running"
        )
    
    # Run cycle
    await dependencies.autonomous_trader.run_cycle()
    
    return {
        "status": "completed",
        "message": "Trading cycle completed"
    }


@router.get("/position-summary")
async def get_position_summary(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current position summary."""
    if not dependencies.position_sync_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Position sync service not initialized"
        )
    
    return await dependencies.position_sync_service.get_position_summary()


# TEMPORARY: Internal endpoint for starting without auth (remove in production)
@router.post("/internal/start")
async def start_autonomous_internal() -> Dict[str, str]:
    """Internal endpoint to start autonomous trading (NO AUTH - REMOVE IN PRODUCTION)."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    if dependencies.autonomous_trader.running:
        return {"status": "already_running", "message": "Autonomous trading is already running"}
    
    # Start in background
    import asyncio
    asyncio.create_task(dependencies.autonomous_trader.run())
    
    return {"status": "started", "message": "Autonomous trading system started (NO AUTH MODE)"}


@router.patch("/daily-limits")
async def update_daily_limits(
    loss_limit: float = Query(..., description="Daily loss limit (as positive number, will be negated)"),
    profit_target: float = Query(..., description="Daily profit target"),
    stop_on_loss: bool = Query(True, description="Stop trading when loss limit hit"),
    stop_on_profit: bool = Query(False, description="Stop trading when profit target hit"),
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Update daily trading limits."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    # Ensure loss limit is negative and profit target is positive
    loss_limit = -abs(loss_limit)
    profit_target = abs(profit_target)
    
    dependencies.autonomous_trader.update_strategy(StrategyType.DAILY_LIMITS,
        enabled=True,
        daily_loss_limit=loss_limit,
        daily_profit_target=profit_target,
        stop_on_loss_limit=stop_on_loss,
        stop_on_profit_target=stop_on_profit
    )
    
    return {
        "status": "updated",
        "daily_limits": {
            "loss_limit": loss_limit,
            "profit_target": profit_target,
            "stop_on_loss": stop_on_loss,
            "stop_on_profit": stop_on_profit
        }
    }