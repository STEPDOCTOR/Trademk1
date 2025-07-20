"""Backtesting API endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, AuthUser
from app.services.strategies.aggressive_backtester import AggressiveBacktester
from app.monitoring.logger import get_logger
from app.db.optimized_postgres import optimized_db
from app.models.symbol import Symbol
from sqlalchemy import select
from fastapi.responses import HTMLResponse
import os

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/backtesting", tags=["backtesting"])


class BacktestRequest(BaseModel):
    """Request model for running a backtest."""
    symbols: Optional[List[str]] = Field(None, description="Symbols to test (None = all active)")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: float = Field(100000, description="Starting capital")
    # Strategy parameters
    momentum_enabled: bool = True
    momentum_threshold: float = Field(0.001, description="Momentum threshold (0.1%)")
    technical_entries: bool = True
    technical_exits: bool = True
    min_confidence: float = Field(0.5, description="Minimum confidence for technical signals")
    # Risk management
    stop_loss_enabled: bool = True
    stop_loss_pct: float = Field(0.02, description="Stop loss percentage")
    take_profit_enabled: bool = True
    take_profit_pct: float = Field(0.05, description="Take profit percentage")
    trailing_stop_enabled: bool = True
    trail_pct: float = Field(0.02, description="Trailing stop percentage")
    # Position sizing
    position_size_pct: float = Field(0.02, description="Position size as % of portfolio")
    dynamic_sizing: bool = True
    max_positions: int = Field(20, description="Maximum concurrent positions")


class BacktestSummary(BaseModel):
    """Summary of backtest results."""
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    num_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    trades_per_day: float


class QuickBacktestRequest(BaseModel):
    """Request for quick backtest with preset strategies."""
    strategy_preset: str = Field(..., description="Preset: 'ultra_aggressive', 'aggressive', 'balanced', 'conservative'")
    lookback_days: int = Field(30, description="Days to look back")
    symbols: Optional[List[str]] = None


# Strategy presets
STRATEGY_PRESETS = {
    "ultra_aggressive": {
        "momentum_threshold": 0.001,  # 0.1%
        "min_confidence": 0.4,
        "stop_loss_pct": 0.015,  # 1.5%
        "take_profit_pct": 0.03,  # 3%
        "position_size_pct": 0.03,  # 3%
        "max_positions": 25
    },
    "aggressive": {
        "momentum_threshold": 0.003,  # 0.3%
        "min_confidence": 0.5,
        "stop_loss_pct": 0.02,  # 2%
        "take_profit_pct": 0.05,  # 5%
        "position_size_pct": 0.025,  # 2.5%
        "max_positions": 20
    },
    "balanced": {
        "momentum_threshold": 0.005,  # 0.5%
        "min_confidence": 0.6,
        "stop_loss_pct": 0.03,  # 3%
        "take_profit_pct": 0.08,  # 8%
        "position_size_pct": 0.02,  # 2%
        "max_positions": 15
    },
    "conservative": {
        "momentum_threshold": 0.01,  # 1%
        "min_confidence": 0.7,
        "stop_loss_pct": 0.05,  # 5%
        "take_profit_pct": 0.15,  # 15%
        "position_size_pct": 0.015,  # 1.5%
        "max_positions": 10
    }
}


@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Run a custom backtest with specified parameters."""
    # Validate dates
    if request.end_date <= request.start_date:
        raise HTTPException(400, "End date must be after start date")
    
    if request.end_date > datetime.utcnow():
        raise HTTPException(400, "End date cannot be in the future")
    
    # Get symbols
    symbols = request.symbols
    if not symbols:
        # Get all active symbols if none specified
        async with optimized_db.get_session() as db:
            result = await db.execute(
                select(Symbol).where(Symbol.is_active == True)
            )
            symbols = [sym.ticker for sym in result.scalars().all()]
    
    if not symbols:
        raise HTTPException(400, "No symbols available for backtesting")
    
    # Prepare strategy parameters
    strategy_params = {
        "momentum_enabled": request.momentum_enabled,
        "momentum_threshold": request.momentum_threshold,
        "technical_entries": request.technical_entries,
        "technical_exits": request.technical_exits,
        "min_confidence": request.min_confidence,
        "stop_loss_enabled": request.stop_loss_enabled,
        "stop_loss_pct": request.stop_loss_pct,
        "take_profit_enabled": request.take_profit_enabled,
        "take_profit_pct": request.take_profit_pct,
        "trailing_stop_enabled": request.trailing_stop_enabled,
        "trail_pct": request.trail_pct,
        "position_size_pct": request.position_size_pct,
        "dynamic_sizing": request.dynamic_sizing,
        "max_positions": request.max_positions
    }
    
    # Run backtest
    backtester = AggressiveBacktester(initial_capital=request.initial_capital)
    results = await backtester.run_backtest(
        symbols=symbols[:30],  # Limit to 30 symbols for performance
        start_date=request.start_date,
        end_date=request.end_date,
        strategy_params=strategy_params
    )
    
    return results.to_dict()


@router.post("/quick")
async def run_quick_backtest(
    request: QuickBacktestRequest,
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Run a quick backtest with preset strategies."""
    if request.strategy_preset not in STRATEGY_PRESETS:
        raise HTTPException(
            400,
            f"Invalid preset. Choose from: {list(STRATEGY_PRESETS.keys())}"
        )
    
    # Calculate dates
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=request.lookback_days)
    
    # Get preset parameters
    preset_params = STRATEGY_PRESETS[request.strategy_preset]
    
    # Build full request
    full_request = BacktestRequest(
        symbols=request.symbols,
        start_date=start_date,
        end_date=end_date,
        **preset_params
    )
    
    return await run_backtest(full_request, current_user)


@router.get("/compare-strategies")
async def compare_strategies(
    lookback_days: int = Query(30, ge=1, le=365),
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Compare all preset strategies over the same time period."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)
    
    # Get default symbols
    async with optimized_db.get_session() as db:
        result = await db.execute(
            select(Symbol).where(Symbol.is_active == True).limit(20)
        )
        symbols = [sym.ticker for sym in result.scalars().all()]
    
    results = {}
    
    for preset_name, preset_params in STRATEGY_PRESETS.items():
        logger.info(f"Running backtest for {preset_name} strategy")
        
        strategy_params = {
            "momentum_enabled": True,
            "technical_entries": True,
            "technical_exits": True,
            "stop_loss_enabled": True,
            "take_profit_enabled": True,
            "trailing_stop_enabled": True,
            "dynamic_sizing": True,
            **preset_params
        }
        
        backtester = AggressiveBacktester()
        backtest_results = await backtester.run_backtest(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            strategy_params=strategy_params
        )
        
        results[preset_name] = {
            "total_return_pct": backtest_results.total_return_pct,
            "win_rate": backtest_results.win_rate,
            "profit_factor": backtest_results.profit_factor,
            "max_drawdown_pct": backtest_results.max_drawdown_pct,
            "sharpe_ratio": backtest_results.sharpe_ratio,
            "trades_per_day": backtest_results.trades_per_day,
            "num_trades": len(backtest_results.trades)
        }
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": lookback_days
        },
        "symbols_tested": len(symbols),
        "strategies": results,
        "best_by_return": max(results.items(), key=lambda x: x[1]["total_return_pct"])[0],
        "best_by_sharpe": max(results.items(), key=lambda x: x[1]["sharpe_ratio"])[0],
        "best_by_win_rate": max(results.items(), key=lambda x: x[1]["win_rate"])[0]
    }


@router.get("/optimal-parameters/{symbol}")
async def find_optimal_parameters(
    symbol: str,
    lookback_days: int = Query(30, ge=7, le=90),
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Find optimal parameters for a specific symbol through parameter sweep."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)
    
    # Parameter ranges to test
    momentum_thresholds = [0.001, 0.002, 0.003, 0.005]
    stop_losses = [0.01, 0.015, 0.02, 0.03]
    take_profits = [0.03, 0.05, 0.08, 0.10]
    
    best_result = None
    best_params = None
    best_sharpe = -float('inf')
    
    results_grid = []
    
    for momentum in momentum_thresholds:
        for stop_loss in stop_losses:
            for take_profit in take_profits:
                if take_profit <= stop_loss:
                    continue  # Skip invalid combinations
                
                strategy_params = {
                    "momentum_enabled": True,
                    "momentum_threshold": momentum,
                    "technical_entries": True,
                    "technical_exits": True,
                    "min_confidence": 0.5,
                    "stop_loss_enabled": True,
                    "stop_loss_pct": stop_loss,
                    "take_profit_enabled": True,
                    "take_profit_pct": take_profit,
                    "trailing_stop_enabled": True,
                    "trail_pct": 0.02,
                    "position_size_pct": 0.02,
                    "dynamic_sizing": True,
                    "max_positions": 1  # Single symbol test
                }
                
                backtester = AggressiveBacktester()
                results = await backtester.run_backtest(
                    symbols=[symbol.upper()],
                    start_date=start_date,
                    end_date=end_date,
                    strategy_params=strategy_params
                )
                
                results_grid.append({
                    "momentum_threshold": momentum,
                    "stop_loss_pct": stop_loss,
                    "take_profit_pct": take_profit,
                    "total_return_pct": results.total_return_pct,
                    "sharpe_ratio": results.sharpe_ratio,
                    "win_rate": results.win_rate,
                    "num_trades": len(results.trades)
                })
                
                if results.sharpe_ratio > best_sharpe and len(results.trades) > 5:
                    best_sharpe = results.sharpe_ratio
                    best_result = results
                    best_params = strategy_params.copy()
    
    if not best_result:
        raise HTTPException(404, "No valid parameter combination found")
    
    return {
        "symbol": symbol.upper(),
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": lookback_days
        },
        "optimal_parameters": {
            "momentum_threshold": best_params["momentum_threshold"],
            "stop_loss_pct": best_params["stop_loss_pct"],
            "take_profit_pct": best_params["take_profit_pct"]
        },
        "optimal_results": {
            "total_return_pct": best_result.total_return_pct,
            "sharpe_ratio": best_result.sharpe_ratio,
            "win_rate": best_result.win_rate,
            "profit_factor": best_result.profit_factor,
            "max_drawdown_pct": best_result.max_drawdown_pct,
            "num_trades": len(best_result.trades)
        },
        "all_results": sorted(results_grid, key=lambda x: x["sharpe_ratio"], reverse=True)[:10]
    }


@router.get("/viewer", response_class=HTMLResponse)
async def get_backtest_viewer():
    """Serve the backtest viewer HTML page."""
    file_path = os.path.join(os.path.dirname(__file__), "..", "static", "backtest", "backtest_viewer.html")
    
    if not os.path.exists(file_path):
        return HTMLResponse("<h1>Backtest viewer not found</h1>", status_code=404)
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    return HTMLResponse(content)