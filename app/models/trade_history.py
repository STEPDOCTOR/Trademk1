"""Trade history model for tracking all executed trades."""
from sqlalchemy import Column, String, Float, DateTime, Enum, JSON, ForeignKey, Integer
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from app.models.base import Base


class TradeType(enum.Enum):
    """Trade type enumeration."""
    BUY = "buy"
    SELL = "sell"


class TradeReason(enum.Enum):
    """Reason for trade execution."""
    MOMENTUM = "momentum"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    MANUAL = "manual"
    TRAILING_STOP = "trailing_stop"
    DAILY_TARGET = "daily_target"


class TradeHistory(Base):
    """Model for tracking all executed trades."""
    
    __tablename__ = "trade_history"
    
    # Trade details
    symbol = Column(String, nullable=False, index=True)
    trade_type = Column(Enum(TradeType), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    
    # Execution details
    executed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    alpaca_order_id = Column(String, index=True)
    reason = Column(Enum(TradeReason), nullable=False)
    strategy_name = Column(String)
    
    # Performance metrics
    entry_price = Column(Float)  # For sells, what was the buy price
    exit_price = Column(Float)   # For buys, will be filled on sell
    profit_loss = Column(Float)  # Realized P&L for sells
    profit_loss_pct = Column(Float)  # Realized P&L percentage
    
    # Market conditions at time of trade
    market_conditions = Column(JSON)  # Store momentum, volatility, etc.
    
    # Position details
    position_size_before = Column(Float)
    position_size_after = Column(Float)
    portfolio_value_at_trade = Column(Float)
    
    # Risk metrics
    stop_loss_price = Column(Float)
    take_profit_price = Column(Float)
    risk_amount = Column(Float)  # Dollar amount at risk
    
    # Daily tracking
    trading_day = Column(DateTime(timezone=True), index=True)
    daily_trade_number = Column(Integer)  # Which trade of the day
    
    # User relationship
    user_id = Column(ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="trade_history")
    
    def __repr__(self):
        return f"<Trade {self.trade_type.value} {self.quantity} {self.symbol} @ {self.price}>"