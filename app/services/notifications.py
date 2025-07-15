"""Notification service for user alerts and system notifications."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_portfolio import UserPreferences
from app.services.cache import cache_service
from app.api.websocket import publish_notification
from app.monitoring.logger import get_main_logger

logger = get_main_logger()


class NotificationType(str, Enum):
    """Notification types."""
    TRADE_EXECUTION = "trade_execution"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    PRICE_ALERT = "price_alert"
    PORTFOLIO_MILESTONE = "portfolio_milestone"
    RISK_WARNING = "risk_warning"
    STRATEGY_SIGNAL = "strategy_signal"
    SYSTEM_ALERT = "system_alert"
    SECURITY_ALERT = "security_alert"
    ACCOUNT_UPDATE = "account_update"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


@dataclass
class NotificationTemplate:
    """Notification template."""
    type: NotificationType
    title_template: str
    message_template: str
    default_channels: List[NotificationChannel]
    default_priority: NotificationPriority


@dataclass
class Notification:
    """Notification data structure."""
    id: str
    user_id: UUID
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    data: Dict[str, Any]
    channels: List[NotificationChannel]
    created_at: datetime
    read_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class NotificationService:
    """Service for managing user notifications."""
    
    # Notification templates
    TEMPLATES = {
        NotificationType.TRADE_EXECUTION: NotificationTemplate(
            type=NotificationType.TRADE_EXECUTION,
            title_template="Trade Executed: {side} {symbol}",
            message_template="Successfully {side} {quantity} shares of {symbol} at ${price}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.NORMAL
        ),
        NotificationType.ORDER_FILLED: NotificationTemplate(
            type=NotificationType.ORDER_FILLED,
            title_template="Order Filled: {symbol}",
            message_template="Your {side} order for {quantity} shares of {symbol} has been filled at ${price}",
            default_channels=[NotificationChannel.IN_APP],
            default_priority=NotificationPriority.NORMAL
        ),
        NotificationType.ORDER_REJECTED: NotificationTemplate(
            type=NotificationType.ORDER_REJECTED,
            title_template="Order Rejected: {symbol}",
            message_template="Your {side} order for {symbol} was rejected: {reason}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.HIGH
        ),
        NotificationType.PRICE_ALERT: NotificationTemplate(
            type=NotificationType.PRICE_ALERT,
            title_template="Price Alert: {symbol}",
            message_template="{symbol} has {direction} your target price of ${target_price}. Current price: ${current_price}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            default_priority=NotificationPriority.HIGH
        ),
        NotificationType.PORTFOLIO_MILESTONE: NotificationTemplate(
            type=NotificationType.PORTFOLIO_MILESTONE,
            title_template="Portfolio Milestone Reached",
            message_template="Congratulations! Your portfolio has reached ${milestone_value}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.NORMAL
        ),
        NotificationType.RISK_WARNING: NotificationTemplate(
            type=NotificationType.RISK_WARNING,
            title_template="Risk Warning: {risk_type}",
            message_template="Your portfolio risk level is {risk_level}: {message}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.HIGH
        ),
        NotificationType.STRATEGY_SIGNAL: NotificationTemplate(
            type=NotificationType.STRATEGY_SIGNAL,
            title_template="Strategy Signal: {strategy_name}",
            message_template="Strategy '{strategy_name}' generated a {signal_type} signal for {symbol} (confidence: {confidence}%)",
            default_channels=[NotificationChannel.IN_APP],
            default_priority=NotificationPriority.NORMAL
        ),
        NotificationType.SYSTEM_ALERT: NotificationTemplate(
            type=NotificationType.SYSTEM_ALERT,
            title_template="System Alert",
            message_template="System notification: {message}",
            default_channels=[NotificationChannel.IN_APP],
            default_priority=NotificationPriority.NORMAL
        ),
        NotificationType.SECURITY_ALERT: NotificationTemplate(
            type=NotificationType.SECURITY_ALERT,
            title_template="Security Alert",
            message_template="Security notification: {message}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.URGENT
        ),
        NotificationType.ACCOUNT_UPDATE: NotificationTemplate(
            type=NotificationType.ACCOUNT_UPDATE,
            title_template="Account Update",
            message_template="Your account has been updated: {message}",
            default_channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            default_priority=NotificationPriority.NORMAL
        )
    }
    
    def __init__(self):
        self.cache_ttl = 3600  # 1 hour
        
    async def send_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        notification_type: NotificationType,
        data: Dict[str, Any],
        custom_title: Optional[str] = None,
        custom_message: Optional[str] = None,
        custom_channels: Optional[List[NotificationChannel]] = None,
        custom_priority: Optional[NotificationPriority] = None,
        expires_in_hours: Optional[int] = 24
    ) -> Notification:
        """Send a notification to a user."""
        
        # Get notification template
        template = self.TEMPLATES.get(notification_type)
        if not template:
            raise ValueError(f"Unknown notification type: {notification_type}")
            
        # Get user preferences
        preferences = await self._get_user_notification_preferences(db, user_id)
        
        # Check if user wants this type of notification
        if not self._should_send_notification(preferences, notification_type):
            logger.info(f"Skipping notification {notification_type} for user {user_id} due to preferences")
            return None
            
        # Format title and message
        title = custom_title or template.title_template.format(**data)
        message = custom_message or template.message_template.format(**data)
        
        # Determine channels and priority
        channels = custom_channels or self._get_user_channels(preferences, template.default_channels)
        priority = custom_priority or template.default_priority
        
        # Create notification
        notification = Notification(
            id=str(uuid4()),
            user_id=user_id,
            type=notification_type,
            priority=priority,
            title=title,
            message=message,
            data=data,
            channels=channels,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours) if expires_in_hours else None
        )
        
        # Store notification
        await self._store_notification(notification)
        
        # Deliver notification
        await self._deliver_notification(notification)
        
        logger.info(f"Sent notification {notification.id} to user {user_id}: {title}")
        return notification
        
    async def get_user_notifications(
        self,
        db: AsyncSession,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """Get notifications for a user."""
        
        # Try cache first
        cache_key = f"notifications:{user_id}:unread={unread_only}:limit={limit}:offset={offset}"
        cached = await cache_service.get(cache_key)
        if cached:
            return [Notification(**notif) for notif in cached]
            
        # Get from storage (Redis for now, could be database)
        notifications = await self._get_stored_notifications(
            user_id, unread_only, limit, offset
        )
        
        # Cache result
        await cache_service.set(
            cache_key,
            [notif.__dict__ for notif in notifications],
            expire=300  # 5 minutes
        )
        
        return notifications
        
    async def mark_notification_read(
        self,
        notification_id: str,
        user_id: UUID
    ) -> bool:
        """Mark a notification as read."""
        
        # Get notification
        notification = await self._get_stored_notification(notification_id, user_id)
        if not notification:
            return False
            
        # Mark as read
        notification.read_at = datetime.utcnow()
        
        # Update storage
        await self._update_stored_notification(notification)
        
        # Clear relevant caches
        await self._clear_user_notification_cache(user_id)
        
        return True
        
    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all notifications as read for a user."""
        
        # Get all unread notifications
        notifications = await self.get_user_notifications(
            None, user_id, unread_only=True, limit=1000
        )
        
        count = 0
        for notification in notifications:
            if await self.mark_notification_read(notification.id, user_id):
                count += 1
                
        return count
        
    async def delete_notification(
        self,
        notification_id: str,
        user_id: UUID
    ) -> bool:
        """Delete a notification."""
        
        success = await self._delete_stored_notification(notification_id, user_id)
        if success:
            await self._clear_user_notification_cache(user_id)
            
        return success
        
    async def get_notification_stats(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Get notification statistics for a user."""
        
        # Get all notifications
        all_notifications = await self._get_stored_notifications(user_id, limit=1000)
        
        unread_count = sum(1 for n in all_notifications if not n.read_at)
        total_count = len(all_notifications)
        
        # Count by type
        type_counts = {}
        for notification in all_notifications:
            type_counts[notification.type] = type_counts.get(notification.type, 0) + 1
            
        # Recent activity (last 24 hours)
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_count = sum(1 for n in all_notifications if n.created_at >= recent_cutoff)
        
        return {
            "total_notifications": total_count,
            "unread_notifications": unread_count,
            "recent_notifications": recent_count,
            "notifications_by_type": type_counts,
            "last_notification": all_notifications[0].created_at if all_notifications else None
        }
        
    async def _get_user_notification_preferences(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[UserPreferences]:
        """Get user notification preferences."""
        
        result = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()
        
    def _should_send_notification(
        self,
        preferences: Optional[UserPreferences],
        notification_type: NotificationType
    ) -> bool:
        """Check if notification should be sent based on user preferences."""
        
        if not preferences:
            return True  # Default to sending if no preferences set
            
        # Check if email notifications are enabled
        if not preferences.email_notifications:
            return False
            
        # Add more specific preference checks here
        # For example, check for trading notifications, price alerts, etc.
        
        return True
        
    def _get_user_channels(
        self,
        preferences: Optional[UserPreferences],
        default_channels: List[NotificationChannel]
    ) -> List[NotificationChannel]:
        """Get notification channels based on user preferences."""
        
        if not preferences:
            return default_channels
            
        # Filter channels based on user preferences
        channels = []
        
        for channel in default_channels:
            if channel == NotificationChannel.EMAIL and preferences.email_notifications:
                channels.append(channel)
            elif channel == NotificationChannel.IN_APP:
                channels.append(channel)  # Always include in-app
            # Add more channel logic as needed
            
        return channels or [NotificationChannel.IN_APP]  # Always have at least in-app
        
    async def _store_notification(self, notification: Notification):
        """Store notification in Redis."""
        
        try:
            await cache_service.connect()
            
            # Store individual notification
            notif_key = f"notification:{notification.id}"
            await cache_service.set(
                notif_key,
                notification.__dict__,
                expire=timedelta(days=30)  # Keep for 30 days
            )
            
            # Add to user's notification list
            user_list_key = f"user_notifications:{notification.user_id}"
            await cache_service.client.lpush(user_list_key, notification.id)
            await cache_service.client.expire(user_list_key, 30 * 24 * 3600)  # 30 days
            
            # Trim list to keep only recent notifications
            await cache_service.client.ltrim(user_list_key, 0, 999)  # Keep last 1000
            
        except Exception as e:
            logger.error(f"Failed to store notification: {e}")
            
    async def _deliver_notification(self, notification: Notification):
        """Deliver notification through configured channels."""
        
        for channel in notification.channels:
            try:
                if channel == NotificationChannel.IN_APP:
                    await self._deliver_in_app(notification)
                elif channel == NotificationChannel.EMAIL:
                    await self._deliver_email(notification)
                elif channel == NotificationChannel.WEBHOOK:
                    await self._deliver_webhook(notification)
                # Add more delivery methods as needed
                    
            except Exception as e:
                logger.error(f"Failed to deliver notification {notification.id} via {channel}: {e}")
                
    async def _deliver_in_app(self, notification: Notification):
        """Deliver in-app notification via WebSocket."""
        
        # Send via WebSocket
        await publish_notification(str(notification.user_id), {
            "id": notification.id,
            "type": notification.type,
            "priority": notification.priority,
            "title": notification.title,
            "message": notification.message,
            "data": notification.data,
            "created_at": notification.created_at.isoformat()
        })
        
    async def _deliver_email(self, notification: Notification):
        """Deliver email notification."""
        
        # Placeholder for email delivery
        # In production, integrate with email service (SendGrid, SES, etc.)
        logger.info(f"Would send email notification {notification.id} to user {notification.user_id}")
        
    async def _deliver_webhook(self, notification: Notification):
        """Deliver webhook notification."""
        
        # Placeholder for webhook delivery
        # In production, send HTTP POST to user's webhook URL
        logger.info(f"Would send webhook notification {notification.id} to user {notification.user_id}")
        
    async def _get_stored_notifications(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """Get stored notifications from Redis."""
        
        try:
            await cache_service.connect()
            
            # Get notification IDs for user
            user_list_key = f"user_notifications:{user_id}"
            notification_ids = await cache_service.client.lrange(
                user_list_key, offset, offset + limit - 1
            )
            
            notifications = []
            for notif_id in notification_ids:
                notif_key = f"notification:{notif_id.decode() if isinstance(notif_id, bytes) else notif_id}"
                notif_data = await cache_service.get(notif_key)
                
                if notif_data:
                    # Convert datetime strings back to datetime objects
                    if isinstance(notif_data.get('created_at'), str):
                        notif_data['created_at'] = datetime.fromisoformat(notif_data['created_at'])
                    if notif_data.get('read_at') and isinstance(notif_data['read_at'], str):
                        notif_data['read_at'] = datetime.fromisoformat(notif_data['read_at'])
                    if notif_data.get('expires_at') and isinstance(notif_data['expires_at'], str):
                        notif_data['expires_at'] = datetime.fromisoformat(notif_data['expires_at'])
                        
                    notification = Notification(**notif_data)
                    
                    # Filter unread if requested
                    if unread_only and notification.read_at:
                        continue
                        
                    notifications.append(notification)
                    
            return notifications
            
        except Exception as e:
            logger.error(f"Failed to get stored notifications: {e}")
            return []
            
    async def _get_stored_notification(
        self,
        notification_id: str,
        user_id: UUID
    ) -> Optional[Notification]:
        """Get a single stored notification."""
        
        try:
            await cache_service.connect()
            
            notif_key = f"notification:{notification_id}"
            notif_data = await cache_service.get(notif_key)
            
            if notif_data and notif_data.get('user_id') == str(user_id):
                # Convert datetime strings back to datetime objects
                if isinstance(notif_data.get('created_at'), str):
                    notif_data['created_at'] = datetime.fromisoformat(notif_data['created_at'])
                if notif_data.get('read_at') and isinstance(notif_data['read_at'], str):
                    notif_data['read_at'] = datetime.fromisoformat(notif_data['read_at'])
                if notif_data.get('expires_at') and isinstance(notif_data['expires_at'], str):
                    notif_data['expires_at'] = datetime.fromisoformat(notif_data['expires_at'])
                    
                return Notification(**notif_data)
                
        except Exception as e:
            logger.error(f"Failed to get stored notification: {e}")
            
        return None
        
    async def _update_stored_notification(self, notification: Notification):
        """Update stored notification."""
        
        try:
            await cache_service.connect()
            
            notif_key = f"notification:{notification.id}"
            await cache_service.set(
                notif_key,
                notification.__dict__,
                expire=timedelta(days=30)
            )
            
        except Exception as e:
            logger.error(f"Failed to update stored notification: {e}")
            
    async def _delete_stored_notification(
        self,
        notification_id: str,
        user_id: UUID
    ) -> bool:
        """Delete stored notification."""
        
        try:
            await cache_service.connect()
            
            # Verify ownership
            notification = await self._get_stored_notification(notification_id, user_id)
            if not notification:
                return False
                
            # Delete notification
            notif_key = f"notification:{notification_id}"
            await cache_service.delete(notif_key)
            
            # Remove from user list
            user_list_key = f"user_notifications:{user_id}"
            await cache_service.client.lrem(user_list_key, 0, notification_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete stored notification: {e}")
            return False
            
    async def _clear_user_notification_cache(self, user_id: UUID):
        """Clear cached notifications for a user."""
        
        try:
            await cache_service.connect()
            await cache_service.flush_pattern(f"notifications:{user_id}:*")
        except Exception as e:
            logger.error(f"Failed to clear notification cache: {e}")


# Global notification service instance
notification_service = NotificationService()