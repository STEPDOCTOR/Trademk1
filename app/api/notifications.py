"""Notification API endpoints."""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, AuthUser
from app.services.notification_service import notification_service, NotificationType

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class TestNotificationRequest(BaseModel):
    """Request model for test notification."""
    message: str
    title: Optional[str] = "Test Notification"


class NotificationSettings(BaseModel):
    """Notification settings update model."""
    telegram_enabled: Optional[bool] = None
    discord_enabled: Optional[bool] = None
    trade_notifications: Optional[bool] = True
    limit_notifications: Optional[bool] = True
    position_notifications: Optional[bool] = True


@router.post("/test")
async def send_test_notification(
    request: TestNotificationRequest,
    current_user: Optional[AuthUser] = None  # Optional auth for testing
) -> Dict[str, str]:
    """Send a test notification to configured channels."""
    if not notification_service.telegram_enabled and not notification_service.discord_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No notification channels configured. Run setup_notifications.py"
        )
    
    await notification_service.send_notification(
        NotificationType.INFO,
        request.title,
        request.message
    )
    
    channels = []
    if notification_service.telegram_enabled:
        channels.append("Telegram")
    if notification_service.discord_enabled:
        channels.append("Discord")
    
    return {
        "status": "sent",
        "channels": channels,
        "message": f"Test notification sent to {', '.join(channels)}"
    }


@router.get("/status")
async def get_notification_status(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get notification service status."""
    return {
        "telegram_enabled": notification_service.telegram_enabled,
        "discord_enabled": notification_service.discord_enabled,
        "telegram_configured": bool(notification_service.telegram_bot_token),
        "discord_configured": bool(notification_service.discord_webhook_url),
        "queue_size": notification_service._queue.qsize() if notification_service._queue else 0
    }


@router.post("/send-custom")
async def send_custom_notification(
    title: str,
    message: str,
    notification_type: str = "info",
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, str]:
    """Send a custom notification."""
    # Map string to NotificationType
    type_map = {
        "info": NotificationType.INFO,
        "error": NotificationType.ERROR,
        "trade": NotificationType.TRADE_EXECUTED,
        "position": NotificationType.POSITION_OPENED
    }
    
    notif_type = type_map.get(notification_type.lower(), NotificationType.INFO)
    
    await notification_service.send_notification(
        notif_type,
        title,
        message
    )
    
    return {
        "status": "queued",
        "title": title,
        "message": message,
        "type": notif_type.value
    }