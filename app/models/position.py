"""Position model for tracking portfolio positions."""
from sqlalchemy import Column, String, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import BaseModel


class Position(BaseModel):
    """Position model for tracking current portfolio positions."""
    
    __tablename__ = "positions"
    
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    qty = Column(Float, nullable=False, default=0.0)
    avg_price = Column(Float, nullable=False, default=0.0)
    
    # P&L fields
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    
    # Market data
    last_price = Column(Float, nullable=True)
    last_price_updated = Column(DateTime(timezone=True), nullable=True)
    
    # Position value
    market_value = Column(Float, nullable=False, default=0.0)
    cost_basis = Column(Float, nullable=False, default=0.0)