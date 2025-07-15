"""Audit logging service for compliance and security."""
import json
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4, UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogger:
    """Service for logging audit events."""
    
    async def log_event(
        self,
        db: AsyncSession,
        event_type: str,
        event_category: str,
        action: str,
        user_id: Optional[UUID] = None,
        event_severity: str = "info",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        description: Optional[str] = None,
        request: Optional[Request] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Log an audit event."""
        # Extract request information
        ip_address = None
        user_agent = None
        request_method = None
        request_path = None
        request_data = None
        
        if request:
            # Get client IP
            ip_address = request.client.host if request.client else None
            # Check for forwarded IP
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()
                
            user_agent = request.headers.get("User-Agent")
            request_method = request.method
            request_path = str(request.url.path)
            
            # Sanitize request data (remove sensitive info)
            if request_method in ["POST", "PUT", "PATCH"]:
                try:
                    # Get request body if available
                    # Note: In production, be careful with await request.json()
                    # as it can only be called once
                    request_data = {"method": request_method}
                except:
                    request_data = None
                    
        # Create audit log entry
        audit_log = AuditLog(
            id=uuid4(),
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=event_type,
            event_category=event_category,
            event_severity=event_severity,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            description=description,
            request_method=request_method,
            request_path=request_path,
            request_data=request_data,
            metadata=metadata or {}
        )
        
        db.add(audit_log)
        # Don't commit here - let the caller handle transaction
        await db.flush()
        
        return audit_log
        
    async def log_trade_event(
        self,
        db: AsyncSession,
        user_id: UUID,
        order_id: str,
        action: str,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        request: Optional[Request] = None
    ):
        """Log trading-related events."""
        metadata = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity
        }
        if price:
            metadata["price"] = price
            
        await self.log_event(
            db=db,
            user_id=user_id,
            event_type="trade_order",
            event_category="trading",
            action=action,
            resource_type="order",
            resource_id=order_id,
            description=f"{action.capitalize()} {side} order for {quantity} {symbol}",
            request=request,
            metadata=metadata
        )
        
    async def log_strategy_event(
        self,
        db: AsyncSession,
        user_id: UUID,
        strategy_id: str,
        action: str,
        description: str,
        request: Optional[Request] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log strategy-related events."""
        await self.log_event(
            db=db,
            user_id=user_id,
            event_type="strategy_management",
            event_category="trading",
            action=action,
            resource_type="strategy",
            resource_id=strategy_id,
            description=description,
            request=request,
            metadata=metadata
        )
        
    async def log_security_event(
        self,
        db: AsyncSession,
        user_id: Optional[UUID],
        event_type: str,
        description: str,
        severity: str = "warning",
        request: Optional[Request] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events."""
        await self.log_event(
            db=db,
            user_id=user_id,
            event_type=event_type,
            event_category="security",
            event_severity=severity,
            action="detect",
            description=description,
            request=request,
            metadata=metadata
        )
        
    async def log_api_key_event(
        self,
        db: AsyncSession,
        user_id: UUID,
        api_key_id: str,
        action: str,
        description: str,
        request: Optional[Request] = None
    ):
        """Log API key related events."""
        await self.log_event(
            db=db,
            user_id=user_id,
            event_type="api_key_management",
            event_category="auth",
            action=action,
            resource_type="api_key",
            resource_id=api_key_id,
            description=description,
            request=request
        )