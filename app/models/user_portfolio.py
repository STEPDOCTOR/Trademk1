"""User portfolio tracking models."""
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class UserPortfolio(BaseModel):
    """User portfolio summary and statistics."""
    
    __tablename__ = "user_portfolios"
    
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Portfolio value
    total_value = Column(Float, default=0.0, nullable=False)
    cash_balance = Column(Float, default=0.0, nullable=False)
    positions_value = Column(Float, default=0.0, nullable=False)
    
    # Performance metrics
    total_pnl = Column(Float, default=0.0, nullable=False)
    total_pnl_percent = Column(Float, default=0.0, nullable=False)
    daily_pnl = Column(Float, default=0.0, nullable=False)
    daily_pnl_percent = Column(Float, default=0.0, nullable=False)
    
    # Risk metrics
    current_drawdown = Column(Float, default=0.0, nullable=False)
    max_drawdown = Column(Float, default=0.0, nullable=False)
    sharpe_ratio = Column(Float, default=0.0, nullable=False)
    win_rate = Column(Float, default=0.0, nullable=False)
    
    # Activity metrics
    total_trades = Column(String(10), default="0", nullable=False)
    winning_trades = Column(String(10), default="0", nullable=False)
    losing_trades = Column(String(10), default="0", nullable=False)
    active_positions = Column(String(10), default="0", nullable=False)
    
    # Strategy allocation
    strategy_allocations = Column(JSON, nullable=False, default={})
    
    # Last update
    last_calculated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="portfolio")


class UserPreferences(BaseModel):
    """User preferences and settings."""
    
    __tablename__ = "user_preferences"
    
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Trading preferences
    default_order_type = Column(String(20), default="market", nullable=False)
    default_time_in_force = Column(String(20), default="day", nullable=False)
    risk_level = Column(String(20), default="medium", nullable=False)  # low, medium, high
    
    # Notification preferences
    email_notifications = Column(Boolean, default=True, nullable=False)
    push_notifications = Column(Boolean, default=False, nullable=False)
    sms_notifications = Column(Boolean, default=False, nullable=False)
    
    # Notification events
    notify_on_fill = Column(Boolean, default=True, nullable=False)
    notify_on_rejection = Column(Boolean, default=True, nullable=False)
    notify_on_high_risk = Column(Boolean, default=True, nullable=False)
    notify_daily_summary = Column(Boolean, default=True, nullable=False)
    
    # UI preferences
    theme = Column(String(20), default="light", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    language = Column(String(10), default="en", nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    
    # Data preferences
    default_chart_interval = Column(String(10), default="1h", nullable=False)
    default_market_view = Column(String(20), default="watchlist", nullable=False)
    
    # Advanced settings
    advanced_mode = Column(Boolean, default=False, nullable=False)
    beta_features = Column(Boolean, default=False, nullable=False)
    
    # Custom settings
    custom_settings = Column(JSON, nullable=False, default={})
    
    # Relationships
    user = relationship("User", back_populates="preferences")