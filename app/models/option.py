"""Options trading models."""
from sqlalchemy import Column, String, Float, DateTime, Integer, Boolean, Enum as SQLEnum, ForeignKey, JSON
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

from app.models.base import Base


class OptionType(str, enum.Enum):
    """Option types."""
    CALL = "call"
    PUT = "put"


class OptionStyle(str, enum.Enum):
    """Option exercise styles."""
    AMERICAN = "american"
    EUROPEAN = "european"


class OptionStatus(str, enum.Enum):
    """Option position status."""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    EXERCISED = "exercised"
    ASSIGNED = "assigned"


class Option(Base):
    """Option contract model."""
    __tablename__ = "options"
    
    # Contract specifications
    symbol = Column(String, nullable=False, index=True)  # Underlying symbol
    option_symbol = Column(String, nullable=False, unique=True)  # OCC option symbol
    type = Column(SQLEnum(OptionType), nullable=False)
    strike_price = Column(Float, nullable=False)
    expiration_date = Column(DateTime, nullable=False, index=True)
    style = Column(SQLEnum(OptionStyle), default=OptionStyle.AMERICAN)
    
    # Pricing data
    last_price = Column(Float)
    bid = Column(Float)
    ask = Column(Float)
    mid_price = Column(Float)
    volume = Column(Integer, default=0)
    open_interest = Column(Integer, default=0)
    
    # Greeks
    delta = Column(Float)
    gamma = Column(Float)
    theta = Column(Float)
    vega = Column(Float)
    rho = Column(Float)
    implied_volatility = Column(Float)
    
    # Additional data
    underlying_price = Column(Float)
    time_to_expiry_days = Column(Float)
    in_the_money = Column(Boolean, default=False)
    intrinsic_value = Column(Float, default=0)
    extrinsic_value = Column(Float, default=0)
    
    # Metadata
    exchange = Column(String)
    contract_size = Column(Integer, default=100)  # Usually 100 shares
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    positions = relationship("OptionPosition", back_populates="option")
    trades = relationship("OptionTrade", back_populates="option")


class OptionPosition(Base):
    """Option position tracking."""
    __tablename__ = "option_positions"
    
    # Position details
    option_id = Column(String, ForeignKey("options.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    quantity = Column(Integer, nullable=False)  # Positive for long, negative for short
    avg_price = Column(Float, nullable=False)
    current_price = Column(Float)
    
    # P&L tracking
    unrealized_pnl = Column(Float, default=0)
    unrealized_pnl_pct = Column(Float, default=0)
    realized_pnl = Column(Float, default=0)
    
    # Position management
    status = Column(SQLEnum(OptionStatus), default=OptionStatus.OPEN)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    
    # Risk metrics
    position_delta = Column(Float)  # Position delta (delta * quantity * 100)
    position_gamma = Column(Float)
    position_theta = Column(Float)
    position_vega = Column(Float)
    max_loss = Column(Float)  # Maximum possible loss
    max_profit = Column(Float)  # Maximum possible profit
    breakeven_price = Column(Float)
    
    # Strategy info
    strategy_name = Column(String)  # e.g., "covered_call", "iron_condor"
    strategy_legs = Column(JSON)  # Other legs in multi-leg strategies
    
    # Relationships
    option = relationship("Option", back_populates="positions")
    user = relationship("User", back_populates="option_positions")
    trades = relationship("OptionTrade", back_populates="position")


class OptionTrade(Base):
    """Option trade history."""
    __tablename__ = "option_trades"
    
    # Trade details
    option_id = Column(String, ForeignKey("options.id"), nullable=False)
    position_id = Column(String, ForeignKey("option_positions.id"))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Execution details
    side = Column(String, nullable=False)  # "buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0)
    total_cost = Column(Float, nullable=False)
    
    # Trade metadata
    executed_at = Column(DateTime, default=datetime.utcnow)
    order_id = Column(String)
    execution_id = Column(String)
    
    # P&L for closing trades
    realized_pnl = Column(Float)
    realized_pnl_pct = Column(Float)
    
    # Strategy and reasoning
    strategy_name = Column(String)
    trade_reason = Column(String)
    market_conditions = Column(JSON)
    
    # Risk at time of trade
    trade_delta = Column(Float)
    trade_iv = Column(Float)
    underlying_price_at_trade = Column(Float)
    
    # Relationships
    option = relationship("Option", back_populates="trades")
    position = relationship("OptionPosition", back_populates="trades")
    user = relationship("User", back_populates="option_trades")


class OptionStrategy(Base):
    """Predefined option strategies."""
    __tablename__ = "option_strategies"
    
    name = Column(String, nullable=False, unique=True)
    description = Column(String)
    strategy_type = Column(String)  # "single", "spread", "complex"
    
    # Strategy configuration
    legs = Column(JSON, nullable=False)  # List of leg configurations
    """
    Example legs format:
    [
        {
            "leg_name": "long_call",
            "option_type": "call",
            "position": "long",
            "strike_offset": 0,  # ATM
            "expiry_days": 30,
            "quantity_ratio": 1
        },
        {
            "leg_name": "short_call",
            "option_type": "call", 
            "position": "short",
            "strike_offset": 5,  # 5 points OTM
            "expiry_days": 30,
            "quantity_ratio": 1
        }
    ]
    """
    
    # Risk parameters
    max_loss = Column(String)  # Formula or fixed value
    max_profit = Column(String)  # Formula or fixed value
    breakeven_formula = Column(String)
    
    # Entry/exit rules
    entry_conditions = Column(JSON)
    exit_conditions = Column(JSON)
    adjustment_rules = Column(JSON)
    
    # Performance tracking
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0)
    avg_return = Column(Float, default=0)
    
    # Suitable market conditions
    ideal_iv_rank = Column(JSON)  # {"min": 30, "max": 70}
    ideal_market_trend = Column(String)  # "bullish", "bearish", "neutral"
    
    is_active = Column(Boolean, default=True)