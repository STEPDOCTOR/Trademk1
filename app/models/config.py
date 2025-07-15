"""Config model for application settings."""

from sqlalchemy import Column, String, Text

from app.models.base import Base


class Config(Base):
    """Config model for storing application configuration."""
    
    key = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    
    value = Column(
        Text,
        nullable=False
    )
    
    scope = Column(
        String(50),
        nullable=False,
        default="global",
        index=True
    )
    
    description = Column(
        Text,
        nullable=True
    )
    
    def __repr__(self) -> str:
        """String representation of Config."""
        return f"<Config(key={self.key}, scope={self.scope})>"