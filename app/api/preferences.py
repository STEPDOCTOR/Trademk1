"""User preferences and notification management API endpoints."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, AuthUser
from app.db.postgres import get_db
from app.models.user_portfolio import UserPreferences
from app.services.notifications import (
    notification_service, NotificationType, NotificationChannel, 
    NotificationPriority, Notification
)
from app.services.cache import cache_service, cache_result

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])


# Request/Response models
class UserPreferencesUpdate(BaseModel):
    """User preferences update request."""
    default_order_type: Optional[str] = Field(None, pattern="^(market|limit|stop|stop_limit)$")
    default_time_in_force: Optional[str] = Field(None, pattern="^(day|gtc|ioc|fok)$")
    risk_level: Optional[str] = Field(None, pattern="^(low|medium|high)$")
    email_notifications: Optional[bool] = None
    theme: Optional[str] = Field(None, pattern="^(light|dark|auto)$")
    timezone: Optional[str] = None
    language: Optional[str] = Field(None, pattern="^(en|es|fr|de|zh|ja)$")
    currency: Optional[str] = Field(None, pattern="^(USD|EUR|GBP|JPY|CAD|AUD)$")


class UserPreferencesResponse(BaseModel):
    """User preferences response."""
    id: str
    user_id: str
    default_order_type: str
    default_time_in_force: str
    risk_level: str
    email_notifications: bool
    theme: str
    timezone: str
    language: str
    currency: str
    created_at: datetime
    updated_at: datetime


class NotificationPreferencesUpdate(BaseModel):
    """Notification preferences update."""
    trade_notifications: bool = True
    order_notifications: bool = True
    price_alerts: bool = True
    portfolio_milestones: bool = True
    risk_warnings: bool = True
    strategy_signals: bool = True
    system_alerts: bool = True
    security_alerts: bool = True
    email_enabled: bool = True
    push_enabled: bool = True
    quiet_hours_start: Optional[str] = Field(None, pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    quiet_hours_end: Optional[str] = Field(None, pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")


class NotificationResponse(BaseModel):
    """Notification response."""
    id: str
    type: str
    priority: str
    title: str
    message: str
    data: Dict[str, Any]
    created_at: datetime
    read_at: Optional[datetime]
    expires_at: Optional[datetime]


class NotificationStatsResponse(BaseModel):
    """Notification statistics response."""
    total_notifications: int
    unread_notifications: int
    recent_notifications: int
    notifications_by_type: Dict[str, int]
    last_notification: Optional[datetime]


class PriceAlertRequest(BaseModel):
    """Price alert creation request."""
    symbol: str = Field(..., min_length=1, max_length=20)
    target_price: float = Field(..., gt=0)
    condition: str = Field(..., pattern="^(above|below)$")
    enabled: bool = True


class PriceAlertResponse(BaseModel):
    """Price alert response."""
    id: str
    user_id: str
    symbol: str
    target_price: float
    condition: str
    enabled: bool
    triggered_at: Optional[datetime]
    created_at: datetime


@router.get("/", response_model=UserPreferencesResponse)
@cache_result(expire=300, key_prefix="user_preferences")
async def get_user_preferences(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user preferences."""
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
    )
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User preferences not found"
        )
    
    return UserPreferencesResponse(
        id=str(preferences.id),
        user_id=str(preferences.user_id),
        default_order_type=preferences.default_order_type,
        default_time_in_force=preferences.default_time_in_force,
        risk_level=preferences.risk_level,
        email_notifications=preferences.email_notifications,
        theme=preferences.theme,
        timezone=preferences.timezone,
        language=preferences.language,
        currency=preferences.currency,
        created_at=preferences.created_at,
        updated_at=preferences.updated_at
    )


@router.patch("/", response_model=UserPreferencesResponse)
async def update_user_preferences(
    preferences_update: UserPreferencesUpdate,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences."""
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
    )
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User preferences not found"
        )
    
    # Update fields
    update_data = preferences_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preferences, field, value)
    
    await db.commit()
    await db.refresh(preferences)
    
    # Clear cache
    await cache_service.flush_pattern(f"user_preferences:{current_user.user_id}*")
    
    return UserPreferencesResponse(
        id=str(preferences.id),
        user_id=str(preferences.user_id),
        default_order_type=preferences.default_order_type,
        default_time_in_force=preferences.default_time_in_force,
        risk_level=preferences.risk_level,
        email_notifications=preferences.email_notifications,
        theme=preferences.theme,
        timezone=preferences.timezone,
        language=preferences.language,
        currency=preferences.currency,
        created_at=preferences.created_at,
        updated_at=preferences.updated_at
    )


@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = Query(False, description="Return only unread notifications"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of notifications"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user notifications."""
    notifications = await notification_service.get_user_notifications(
        db, current_user.user_id, unread_only, limit, offset
    )
    
    return [
        NotificationResponse(
            id=notif.id,
            type=notif.type,
            priority=notif.priority,
            title=notif.title,
            message=notif.message,
            data=notif.data,
            created_at=notif.created_at,
            read_at=notif.read_at,
            expires_at=notif.expires_at
        )
        for notif in notifications
    ]


@router.get("/notifications/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics."""
    stats = await notification_service.get_notification_stats(db, current_user.user_id)
    
    return NotificationStatsResponse(**stats)


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Mark a notification as read."""
    success = await notification_service.mark_notification_read(
        notification_id, current_user.user_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    return {"message": "Notification marked as read"}


@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    current_user: AuthUser = Depends(get_current_user)
):
    """Mark all notifications as read."""
    count = await notification_service.mark_all_read(current_user.user_id)
    
    return {"message": f"Marked {count} notifications as read"}


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Delete a notification."""
    success = await notification_service.delete_notification(
        notification_id, current_user.user_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    return {"message": "Notification deleted"}


@router.post("/notifications/test")
async def send_test_notification(
    notification_type: NotificationType = Query(NotificationType.SYSTEM_ALERT),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a test notification (for testing purposes)."""
    
    test_data = {
        "message": "This is a test notification",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    notification = await notification_service.send_notification(
        db=db,
        user_id=current_user.user_id,
        notification_type=notification_type,
        data=test_data,
        custom_title="Test Notification",
        custom_message="This is a test notification to verify your notification settings."
    )
    
    if notification:
        return {
            "message": "Test notification sent",
            "notification_id": notification.id
        }
    else:
        return {"message": "Test notification was filtered by your preferences"}


@router.get("/price-alerts", response_model=List[PriceAlertResponse])
async def get_price_alerts(
    current_user: AuthUser = Depends(get_current_user)
):
    """Get user's price alerts."""
    # This is a placeholder - in a real implementation, you'd store price alerts in the database
    # For now, return empty list
    return []


@router.post("/price-alerts", response_model=PriceAlertResponse)
async def create_price_alert(
    alert_request: PriceAlertRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new price alert."""
    # This is a placeholder implementation
    # In a real system, you'd:
    # 1. Store the alert in the database
    # 2. Set up monitoring to check prices
    # 3. Send notifications when conditions are met
    
    from uuid import uuid4
    
    alert_id = str(uuid4())
    
    # Simulate storing the alert
    alert_data = {
        "id": alert_id,
        "user_id": str(current_user.user_id),
        "symbol": alert_request.symbol,
        "target_price": alert_request.target_price,
        "condition": alert_request.condition,
        "enabled": alert_request.enabled,
        "triggered_at": None,
        "created_at": datetime.utcnow()
    }
    
    # Send confirmation notification
    await notification_service.send_notification(
        db=db,
        user_id=current_user.user_id,
        notification_type=NotificationType.SYSTEM_ALERT,
        data={
            "symbol": alert_request.symbol,
            "target_price": alert_request.target_price,
            "condition": alert_request.condition
        },
        custom_title="Price Alert Created",
        custom_message=f"Price alert created for {alert_request.symbol} {alert_request.condition} ${alert_request.target_price}"
    )
    
    return PriceAlertResponse(**alert_data)


@router.delete("/price-alerts/{alert_id}")
async def delete_price_alert(
    alert_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Delete a price alert."""
    # Placeholder implementation
    return {"message": f"Price alert {alert_id} deleted"}


@router.get("/notification-settings")
async def get_notification_settings(
    current_user: AuthUser = Depends(get_current_user)
):
    """Get notification settings."""
    # This would typically come from user preferences or a separate notification settings table
    return {
        "trade_notifications": True,
        "order_notifications": True,
        "price_alerts": True,
        "portfolio_milestones": True,
        "risk_warnings": True,
        "strategy_signals": True,
        "system_alerts": True,
        "security_alerts": True,
        "email_enabled": True,
        "push_enabled": True,
        "quiet_hours_start": None,
        "quiet_hours_end": None
    }


@router.patch("/notification-settings")
async def update_notification_settings(
    settings: NotificationPreferencesUpdate,
    current_user: AuthUser = Depends(get_current_user)
):
    """Update notification settings."""
    # In a real implementation, you'd store these in the database
    # For now, just return success
    
    return {
        "message": "Notification settings updated",
        "settings": settings.dict()
    }