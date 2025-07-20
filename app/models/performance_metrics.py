"""Performance metrics model for tracking trading performance."""
from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime, date
from app.models.base import Base


class DailyPerformance(Base):
    """Model for tracking daily trading performance."""
    
    __tablename__ = "daily_performance"
    
    # Date tracking
    trading_date = Column(Date, nullable=False, index=True)
    
    # Trade statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    
    # P&L metrics
    total_profit_loss = Column(Float, default=0.0)
    total_profit_loss_pct = Column(Float, default=0.0)
    best_trade = Column(Float, default=0.0)
    worst_trade = Column(Float, default=0.0)
    average_win = Column(Float, default=0.0)
    average_loss = Column(Float, default=0.0)
    
    # Volume metrics
    total_volume_traded = Column(Float, default=0.0)
    total_commission = Column(Float, default=0.0)
    
    # Portfolio metrics
    starting_balance = Column(Float)
    ending_balance = Column(Float)
    high_water_mark = Column(Float)
    max_drawdown = Column(Float, default=0.0)
    max_drawdown_pct = Column(Float, default=0.0)
    
    # Risk metrics
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    profit_factor = Column(Float)  # Total wins / Total losses
    
    # Position metrics
    positions_opened = Column(Integer, default=0)
    positions_closed = Column(Integer, default=0)
    max_positions_held = Column(Integer, default=0)
    average_position_size = Column(Float, default=0.0)
    
    # Strategy breakdown
    trades_by_strategy = Column(JSON)  # {"momentum": 10, "stop_loss": 5, etc}
    pnl_by_strategy = Column(JSON)     # {"momentum": 1000, "stop_loss": -500, etc}
    
    # Market conditions
    market_volatility = Column(Float)
    market_trend = Column(String)  # "bullish", "bearish", "neutral"
    
    # Alerts and limits
    daily_loss_limit_hit = Column(DateTime(timezone=True))
    daily_profit_target_hit = Column(DateTime(timezone=True))
    
    # User relationship
    user_id = Column(ForeignKey("users.id"), nullable=True)
    user = relationship("User")
    
    # Timestamps
    calculated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    def __repr__(self):
        return f"<DailyPerformance {self.trading_date} P&L: {self.total_profit_loss}>"


class RealtimeMetrics(Base):
    """Model for tracking real-time performance metrics."""
    
    __tablename__ = "realtime_metrics"
    
    # Current session metrics
    session_start = Column(DateTime(timezone=True), nullable=False)
    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Live P&L
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)
    
    # Position metrics
    open_positions = Column(Integer, default=0)
    total_position_value = Column(Float, default=0.0)
    cash_available = Column(Float, default=0.0)
    buying_power = Column(Float, default=0.0)
    
    # Today's metrics
    trades_today = Column(Integer, default=0)
    winning_trades_today = Column(Integer, default=0)
    losing_trades_today = Column(Integer, default=0)
    volume_today = Column(Float, default=0.0)
    
    # Risk metrics
    current_risk_exposure = Column(Float, default=0.0)  # Total $ at risk
    risk_exposure_pct = Column(Float, default=0.0)     # % of portfolio at risk
    largest_position_pct = Column(Float, default=0.0)
    
    # Alert thresholds
    approaching_daily_loss_limit = Column(Float)  # % until limit
    approaching_position_limit = Column(Integer)  # positions until limit
    
    # Active strategies
    active_strategies = Column(JSON)  # List of active strategy names
    pending_signals = Column(Integer, default=0)
    
    # Market status
    market_status = Column(String)  # "open", "closed", "pre-market", "after-hours"
    next_market_open = Column(DateTime(timezone=True))
    next_market_close = Column(DateTime(timezone=True))
    
    # User relationship
    user_id = Column(ForeignKey("users.id"), nullable=True)
    user = relationship("User")
    
    def __repr__(self):
        return f"<RealtimeMetrics P&L: {self.total_pnl} Positions: {self.open_positions}>"