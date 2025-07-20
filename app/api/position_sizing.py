"""Position sizing API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, AuthUser
from app.services.position_sizing import position_sizing, PositionSizeRecommendation
from app.services.trading.alpaca_client import get_alpaca_client
from app.db.optimized_postgres import optimized_db
from app.models.position import Position
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/position-sizing", tags=["position-sizing"])


class PositionSizeRequest(BaseModel):
    """Request model for position size calculation."""
    symbol: str
    signal_confidence: float = 0.5
    risk_per_trade: float = 0.01  # 1% default


class PositionSizeResponse(BaseModel):
    """Response model for position size recommendation."""
    symbol: str
    recommended_shares: int
    position_value: float
    risk_adjusted_size: float
    volatility: float
    risk_score: float
    confidence_multiplier: float
    reasoning: List[str]
    scale_in_levels: Optional[List[int]] = None
    
    @classmethod
    def from_recommendation(cls, rec: PositionSizeRecommendation, price: float) -> "PositionSizeResponse":
        """Create response from recommendation."""
        return cls(
            symbol=rec.symbol,
            recommended_shares=rec.shares,
            position_value=rec.shares * price,
            risk_adjusted_size=rec.risk_adjusted_size,
            volatility=rec.volatility,
            risk_score=rec.risk_score,
            confidence_multiplier=rec.confidence_multiplier,
            reasoning=rec.reasoning
        )


@router.post("/calculate")
async def calculate_position_size(
    request: PositionSizeRequest,
    current_user: AuthUser = Depends(get_current_user)
) -> PositionSizeResponse:
    """Calculate optimal position size for a symbol."""
    # Get account info
    alpaca_client = get_alpaca_client()
    account_info = await alpaca_client.get_account()
    portfolio_value = float(account_info["portfolio_value"])
    
    # Get current positions count
    async with optimized_db.get_session() as db:
        result = await db.execute(
            select(Position).where(Position.qty > 0)
        )
        num_positions = len(list(result.scalars().all()))
    
    # Get current price
    last_trade = await alpaca_client.get_latest_trade(request.symbol)
    current_price = last_trade["price"]
    
    # Calculate position size
    recommendation = await position_sizing.calculate_position_size(
        symbol=request.symbol,
        account_value=portfolio_value,
        current_price=current_price,
        signal_confidence=request.signal_confidence,
        existing_positions=num_positions,
        max_positions=20,
        risk_per_trade=request.risk_per_trade
    )
    
    response = PositionSizeResponse.from_recommendation(recommendation, current_price)
    
    # Add scale-in levels if requested
    if recommendation.shares > 100:
        scale_in = position_sizing.scale_in_strategy(recommendation.shares, levels=3)
        response.scale_in_levels = [int(qty) for qty in scale_in]
    
    return response


@router.get("/scale-out/{symbol}")
async def get_scale_out_recommendation(
    symbol: str,
    profit_pct: float = Query(..., description="Current profit percentage"),
    current_user: AuthUser = Depends(get_current_user)
) -> dict:
    """Get scale-out recommendation based on profit level."""
    # Get position
    async with optimized_db.get_session() as db:
        position = await db.scalar(
            select(Position).where(
                Position.symbol == symbol.upper(),
                Position.qty > 0
            )
        )
    
    if not position:
        return {
            "symbol": symbol,
            "error": "No position found"
        }
    
    sell_qty = position_sizing.scale_out_strategy(position.qty, profit_pct / 100)
    
    return {
        "symbol": symbol,
        "current_shares": position.qty,
        "profit_pct": profit_pct,
        "recommended_sell_qty": int(sell_qty),
        "remaining_shares": position.qty - int(sell_qty),
        "action": "sell" if sell_qty > 0 else "hold"
    }


@router.get("/portfolio-allocation")
async def get_portfolio_allocation_recommendations(
    current_user: AuthUser = Depends(get_current_user)
) -> dict:
    """Get position sizing recommendations for entire portfolio."""
    # Get account info
    alpaca_client = get_alpaca_client()
    account_info = await alpaca_client.get_account()
    portfolio_value = float(account_info["portfolio_value"])
    buying_power = float(account_info["buying_power"])
    
    # Get current positions
    async with optimized_db.get_session() as db:
        result = await db.execute(
            select(Position).where(Position.qty > 0)
        )
        positions = list(result.scalars().all())
    
    # Calculate allocations
    allocations = []
    total_market_value = sum(p.market_value for p in positions)
    
    for position in positions:
        allocation_pct = (position.market_value / portfolio_value) * 100 if portfolio_value > 0 else 0
        allocations.append({
            "symbol": position.symbol,
            "shares": position.qty,
            "market_value": position.market_value,
            "allocation_pct": allocation_pct,
            "unrealized_pnl": position.unrealized_pnl,
            "unrealized_pnl_pct": position.unrealized_pnl_pct
        })
    
    # Sort by allocation
    allocations.sort(key=lambda x: x["allocation_pct"], reverse=True)
    
    return {
        "portfolio_value": portfolio_value,
        "buying_power": buying_power,
        "total_positions": len(positions),
        "cash_allocation_pct": (buying_power / portfolio_value * 100) if portfolio_value > 0 else 0,
        "positions": allocations,
        "recommendations": {
            "max_position_pct": position_sizing.max_position_pct * 100,
            "target_position_pct": position_sizing.default_position_pct * 100,
            "min_position_pct": position_sizing.min_position_pct * 100,
            "overweight_positions": [p for p in allocations if p["allocation_pct"] > position_sizing.max_position_pct * 100],
            "underweight_positions": [p for p in allocations if p["allocation_pct"] < position_sizing.min_position_pct * 100]
        }
    }