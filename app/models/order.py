"""Order model for tracking trading orders."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy import Column, String, Float, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import enum

from app.models.base import BaseModel


class OrderSide(str, enum.Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, enum.Enum):
    """Order status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Order(BaseModel):
    """Order model for tracking all trading orders."""
    
    __tablename__ = "orders"
    
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(SQLEnum(OrderSide), nullable=False)
    qty = Column(Float, nullable=False)
    type = Column(SQLEnum(OrderType), nullable=False, default=OrderType.MARKET)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING, index=True)
    
    # Price fields
    price = Column(Float, nullable=True)  # Limit price
    stop_price = Column(Float, nullable=True)  # Stop price
    filled_price = Column(Float, nullable=True)  # Average fill price
    
    # Alpaca integration
    alpaca_id = Column(String(100), nullable=True, unique=True, index=True)
    
    # Timestamps
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Additional fields
    reason = Column(String(500), nullable=True)  # Trading signal reason
    error_message = Column(String(500), nullable=True)  # Error if rejected