"""Strategy configuration model for database storage."""
from sqlalchemy import Column, String, JSON, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import BaseModel


class StrategyConfiguration(BaseModel):
    """Strategy configuration stored in database."""
    
    __tablename__ = "strategy_configs"
    
    strategy_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    strategy_type = Column(String(50), nullable=False)  # sma_crossover, momentum, etc.
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Configuration
    symbols = Column(JSON, nullable=False)  # List of symbols
    parameters = Column(JSON, nullable=False, default={})  # Strategy-specific parameters
    risk_parameters = Column(JSON, nullable=False, default={})  # Risk management parameters
    
    # Portfolio allocation
    allocation = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0
    
    # Performance tracking
    performance_score = Column(Float, default=0.5, nullable=False)  # 0.0 to 1.0
    last_signal_time = Column(String(50), nullable=True)
    total_signals = Column(String(10), default="0", nullable=False)
    
    # Metadata
    metadata_json = Column(JSON, nullable=False, default={})