"""Audit log model for compliance and security tracking."""
from sqlalchemy import Column, String, JSON, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import BaseModel


class AuditLog(BaseModel):
    """Audit log for tracking user actions and system events."""
    
    __tablename__ = "audit_logs"
    
    # Actor information
    user_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)  # Null for system events
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Event information
    event_type = Column(String(50), nullable=False, index=True)  # login, trade, config_change, etc.
    event_category = Column(String(50), nullable=False, index=True)  # auth, trading, admin, system
    event_severity = Column(String(20), nullable=False, default="info")  # info, warning, error, critical
    
    # Resource information
    resource_type = Column(String(50), nullable=True, index=True)  # order, position, user, etc.
    resource_id = Column(String(100), nullable=True)
    
    # Action details
    action = Column(String(100), nullable=False)  # create, update, delete, execute, etc.
    description = Column(Text, nullable=True)
    
    # Request/Response data
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)
    request_data = Column(JSON, nullable=True)  # Sanitized request data
    response_status = Column(String(3), nullable=True)
    
    # Additional metadata
    metadata = Column(JSON, nullable=False, default={})
    
    # Search optimization
    __table_args__ = (
        Index('idx_audit_user_time', 'user_id', 'created_at'),
        Index('idx_audit_event_time', 'event_type', 'created_at'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )