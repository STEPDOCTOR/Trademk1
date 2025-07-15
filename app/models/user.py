"""User model for authentication and authorization."""

from sqlalchemy import Boolean, Column, String

from app.models.base import Base


class User(Base):
    """User model for storing user accounts."""
    
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
    
    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(email={self.email}, is_active={self.is_active})>"