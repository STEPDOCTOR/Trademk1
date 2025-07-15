"""Trading API endpoints for order management and positions."""
import json
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.config.settings import get_settings
from app.db.postgres import get_db
from app.models.order import Order, OrderStatus
from app.models.position import Position
from app.services.trading.position_manager import PositionManager

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])


class TradeSignal(BaseModel):
    """Trade signal request model."""
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSDT)")
    side: str = Field(..., pattern="^(buy|sell)$", description="Order side: buy or sell")
    qty: float = Field(..., gt=0, description="Order quantity")
    reason: Optional[str] = Field(None, description="Reason for the trade signal")


class OrderResponse(BaseModel):
    """Order response model."""
    id: UUID
    symbol: str
    side: str
    qty: float
    type: str
    status: str
    price: Optional[float]
    filled_price: Optional[float]
    alpaca_id: Optional[str]
    created_at: datetime
    submitted_at: Optional[datetime]
    filled_at: Optional[datetime]
    reason: Optional[str]
    error_message: Optional[str]


class PositionResponse(BaseModel):
    """Position response model."""
    symbol: str
    qty: float
    avg_price: float
    last_price: Optional[float]
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    realized_pnl: float
    last_price_updated: Optional[datetime]


class PortfolioSnapshot(BaseModel):
    """Portfolio snapshot response model."""
    total_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_pnl: float
    positions: List[PositionResponse]
    timestamp: datetime


@router.post("/signal", response_model=dict)
async def submit_trade_signal(signal: TradeSignal):
    """
    Submit a trade signal to the execution engine.
    
    The signal will be processed asynchronously by the execution engine,
    which will perform risk checks and submit the order to Alpaca.
    """
    settings = get_settings()
    
    # Connect to Redis
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        # Publish signal to Redis
        signal_data = {
            "symbol": signal.symbol,
            "side": signal.side,
            "qty": signal.qty,
            "reason": signal.reason or f"API signal at {datetime.utcnow().isoformat()}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await redis_client.publish("trade_signals", json.dumps(signal_data))
        
        return {
            "status": "accepted",
            "message": "Trade signal submitted for processing",
            "signal": signal_data
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit trade signal: {str(e)}"
        )
    finally:
        await redis_client.close()


@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=1000),
    status: Optional[OrderStatus] = None,
    symbol: Optional[str] = None,
    days: int = Query(default=7, ge=1, le=30)
):
    """
    Get recent orders with optional filtering.
    
    Parameters:
    - limit: Maximum number of orders to return (1-1000)
    - status: Filter by order status
    - symbol: Filter by trading symbol
    - days: Number of days to look back (1-30)
    """
    # Build query
    query = select(Order)
    
    # Apply filters
    if status:
        query = query.where(Order.status == status)
    if symbol:
        query = query.where(Order.symbol == symbol)
        
    # Time filter
    since = datetime.utcnow() - timedelta(days=days)
    query = query.where(Order.created_at >= since)
    
    # Order by most recent first
    query = query.order_by(desc(Order.created_at)).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return [
        OrderResponse(
            id=order.id,
            symbol=order.symbol,
            side=order.side.value,
            qty=order.qty,
            type=order.type.value,
            status=order.status.value,
            price=order.price,
            filled_price=order.filled_price,
            alpaca_id=order.alpaca_id,
            created_at=order.created_at,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            reason=order.reason,
            error_message=order.error_message
        )
        for order in orders
    ]


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    db: AsyncSession = Depends(get_db),
    include_closed: bool = Query(default=False)
):
    """
    Get current positions.
    
    Parameters:
    - include_closed: Include positions with zero quantity
    """
    query = select(Position)
    
    if not include_closed:
        query = query.where(Position.qty != 0)
        
    result = await db.execute(query)
    positions = result.scalars().all()
    
    return [
        PositionResponse(
            symbol=pos.symbol,
            qty=pos.qty,
            avg_price=pos.avg_price,
            last_price=pos.last_price,
            market_value=pos.market_value,
            cost_basis=pos.cost_basis,
            unrealized_pnl=pos.unrealized_pnl,
            realized_pnl=pos.realized_pnl,
            last_price_updated=pos.last_price_updated
        )
        for pos in positions
    ]


@router.get("/portfolio", response_model=PortfolioSnapshot)
async def get_portfolio_snapshot():
    """Get a complete portfolio snapshot with P&L calculations."""
    position_manager = PositionManager()
    snapshot = await position_manager.get_portfolio_snapshot()
    
    return PortfolioSnapshot(
        total_value=snapshot["total_value"],
        total_unrealized_pnl=snapshot["total_unrealized_pnl"],
        total_realized_pnl=snapshot["total_realized_pnl"],
        total_pnl=snapshot["total_pnl"],
        positions=[
            PositionResponse(**pos) for pos in snapshot["positions"]
        ],
        timestamp=snapshot["timestamp"]
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific order by ID."""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    return OrderResponse(
        id=order.id,
        symbol=order.symbol,
        side=order.side.value,
        qty=order.qty,
        type=order.type.value,
        status=order.status.value,
        price=order.price,
        filled_price=order.filled_price,
        alpaca_id=order.alpaca_id,
        created_at=order.created_at,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        reason=order.reason,
        error_message=order.error_message
    )