"""User model for authentication and authorization."""

from sqlalchemy import Boolean, Column, String, DateTime
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class User(BaseModel):
    """User model for storing user accounts."""
    
    __tablename__ = "users"
    
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    
    password_hash = Column(
        String(255),
        nullable=False
    )
    
    # User information
    full_name = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
    
    # Account status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )
    
    is_superuser = Column(
        Boolean,
        default=False,
        nullable=False
    )
    
    is_verified = Column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # Timestamps
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Account limits
    max_daily_trades = Column(String(10), default="100", nullable=False)
    max_position_size = Column(String(20), default="10000", nullable=False)
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    portfolio = relationship("UserPortfolio", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(email={self.email}, is_active={self.is_active})>"