"""Symbol model for trading assets."""

from sqlalchemy import Boolean, Column, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


class Symbol(Base):
    """Symbol model for storing tradable assets."""
    
    ticker = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True
    )
    
    name = Column(
        String(255),
        nullable=False
    )
    
    exchange = Column(
        String(50),
        nullable=False,
        index=True
    )
    
    asset_type = Column(
        String(20),
        nullable=False,
        index=True
    )
    
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    
    metadata_json = Column(
        JSONB,
        default={},
        nullable=False
    )
    
    def __repr__(self) -> str:
        """String representation of Symbol."""
        return f"<Symbol(ticker={self.ticker}, exchange={self.exchange}, asset_type={self.asset_type})>"