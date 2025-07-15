"""Base model with common fields for all database models."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base model class with common fields."""
    
    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower() + "s"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True
    )
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=sa.text("CURRENT_TIMESTAMP")
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=sa.text("CURRENT_TIMESTAMP")
    )