"""API Key model for programmatic access."""
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class APIKey(Base):
    """API Key for programmatic access."""
    
    __tablename__ = "api_keys"
    
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True, index=True)
    
    # Permissions
    scopes = Column(String(500), nullable=False, default="read:market_data")  # Comma-separated scopes
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Rate limiting
    rate_limit_per_minute = Column(String(10), default="60", nullable=False)
    rate_limit_per_hour = Column(String(10), default="3600", nullable=False)
    
    # Metadata
    description = Column(String(500), nullable=True)
    allowed_ips = Column(String(500), nullable=True)  # Comma-separated IP whitelist
    
    # Relationships
    user = relationship("User", back_populates="api_keys")