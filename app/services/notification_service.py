"""Notification service for Telegram and Discord alerts."""
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import json

from app.config.settings import get_settings
from app.monitoring.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class NotificationType(Enum):
    """Types of notifications."""
    TRADE_EXECUTED = "trade_executed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    TRAILING_STOP_HIT = "trailing_stop_hit"
    DAILY_LIMIT_WARNING = "daily_limit_warning"
    DAILY_LIMIT_HIT = "daily_limit_hit"
    PROFIT_TARGET_HIT = "profit_target_hit"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    ERROR = "error"
    INFO = "info"


class NotificationService:
    """Service for sending notifications to Telegram and Discord."""
    
    def __init__(self):
        self.telegram_bot_token = settings.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = settings.get("TELEGRAM_CHAT_ID")
        self.discord_webhook_url = settings.get("DISCORD_WEBHOOK_URL")
        
        self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
        self.discord_enabled = bool(self.discord_webhook_url)
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        
        # Emoji mappings
        self.emojis = {
            NotificationType.TRADE_EXECUTED: "💱",
            NotificationType.STOP_LOSS_HIT: "🛑",
            NotificationType.TAKE_PROFIT_HIT: "🎯",
            NotificationType.TRAILING_STOP_HIT: "📉",
            NotificationType.DAILY_LIMIT_WARNING: "⚠️",
            NotificationType.DAILY_LIMIT_HIT: "🚫",
            NotificationType.PROFIT_TARGET_HIT: "🎉",
            NotificationType.POSITION_OPENED: "📈",
            NotificationType.POSITION_CLOSED: "📊",
            NotificationType.BOT_STARTED: "🤖",
            NotificationType.BOT_STOPPED: "⏹️",
            NotificationType.ERROR: "❌",
            NotificationType.INFO: "ℹ️"
        }
        
    async def initialize(self):
        """Initialize the notification service."""
        if not self._session:
            self._session = aiohttp.ClientSession()
            
        # Start worker
        self._worker_task = asyncio.create_task(self._process_queue())
        
        logger.info(
            f"Notification service initialized - "
            f"Telegram: {'enabled' if self.telegram_enabled else 'disabled'}, "
            f"Discord: {'enabled' if self.discord_enabled else 'disabled'}"
        )
        
        # Send startup notification
        if self.telegram_enabled or self.discord_enabled:
            await self.send_notification(
                NotificationType.BOT_STARTED,
                "🚀 Aggressive Trading Bot Started",
                "The bot is now monitoring markets and executing trades."
            )
    
    async def shutdown(self):
        """Shutdown the notification service."""
        # Send shutdown notification
        await self.send_notification(
            NotificationType.BOT_STOPPED,
            "Trading Bot Stopped",
            "The bot has been shut down."
        )
        
        # Stop worker
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
                
        # Close session
        if self._session:
            await self._session.close()
    
    async def send_notification(
        self, 
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """Queue a notification for sending."""
        await self._queue.put({
            "type": notification_type,
            "title": title,
            "message": message,
            "data": data or {},
            "timestamp": datetime.utcnow()
        })
    
    async def send_trade_notification(self, trade_data: Dict[str, Any]):
        """Send notification for executed trade."""
        symbol = trade_data.get("symbol", "Unknown")
        side = trade_data.get("side", "").upper()
        quantity = trade_data.get("quantity", 0)
        price = trade_data.get("price", 0)
        reason = trade_data.get("reason", "Manual")
        pnl = trade_data.get("profit_loss")
        
        title = f"{side} {symbol}"
        
        message_lines = [
            f"Quantity: {quantity}",
            f"Price: ${price:.2f}",
            f"Reason: {reason}"
        ]
        
        if pnl is not None:
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            message_lines.append(f"P&L: {pnl_emoji} ${pnl:.2f}")
        
        await self.send_notification(
            NotificationType.TRADE_EXECUTED,
            title,
            "\n".join(message_lines),
            trade_data
        )
    
    async def send_limit_notification(self, limit_data: Dict[str, Any]):
        """Send notification for daily limits."""
        current_pnl = limit_data.get("current_pnl", 0)
        limit_type = limit_data.get("type", "loss")
        
        if limit_type == "loss":
            title = "Daily Loss Limit Hit!"
            message = f"Current loss: ${abs(current_pnl):.2f}\nTrading has been stopped."
            notification_type = NotificationType.DAILY_LIMIT_HIT
        elif limit_type == "profit":
            title = "Daily Profit Target Reached!"
            message = f"Current profit: ${current_pnl:.2f}\nCongratulations! 🎉"
            notification_type = NotificationType.PROFIT_TARGET_HIT
        elif limit_type == "warning":
            pct = limit_data.get("percentage", 0)
            title = "Approaching Daily Loss Limit"
            message = f"Currently at {pct:.0f}% of daily loss limit\nCurrent P&L: ${current_pnl:.2f}"
            notification_type = NotificationType.DAILY_LIMIT_WARNING
        else:
            return
            
        await self.send_notification(notification_type, title, message, limit_data)
    
    async def send_position_notification(self, position_data: Dict[str, Any], opened: bool = True):
        """Send notification for position changes."""
        symbol = position_data.get("symbol", "Unknown")
        quantity = position_data.get("quantity", 0)
        price = position_data.get("price", 0)
        
        if opened:
            title = f"Position Opened: {symbol}"
            message = f"Quantity: {quantity}\nEntry Price: ${price:.2f}"
            notification_type = NotificationType.POSITION_OPENED
        else:
            pnl = position_data.get("profit_loss", 0)
            pnl_pct = position_data.get("profit_loss_pct", 0)
            title = f"Position Closed: {symbol}"
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            message = f"Quantity: {quantity}\nP&L: {pnl_emoji} ${pnl:.2f} ({pnl_pct:.2f}%)"
            notification_type = NotificationType.POSITION_CLOSED
            
        await self.send_notification(notification_type, title, message, position_data)
    
    async def _process_queue(self):
        """Process notification queue."""
        while True:
            try:
                notification = await self._queue.get()
                
                # Send to Telegram
                if self.telegram_enabled:
                    await self._send_telegram(notification)
                
                # Send to Discord  
                if self.discord_enabled:
                    await self._send_discord(notification)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing notification: {e}")
    
    async def _send_telegram(self, notification: Dict[str, Any]):
        """Send notification to Telegram."""
        try:
            emoji = self.emojis.get(notification["type"], "")
            
            # Format message
            text = f"{emoji} **{notification['title']}**\n\n{notification['message']}"
            
            # Add timestamp
            timestamp = notification["timestamp"].strftime("%H:%M:%S UTC")
            text += f"\n\n__{timestamp}__"
            
            # Telegram API URL
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            async with self._session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram API error: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
    
    async def _send_discord(self, notification: Dict[str, Any]):
        """Send notification to Discord via webhook."""
        try:
            emoji = self.emojis.get(notification["type"], "")
            
            # Create embed
            embed = {
                "title": f"{emoji} {notification['title']}",
                "description": notification['message'],
                "color": self._get_discord_color(notification["type"]),
                "timestamp": notification["timestamp"].isoformat(),
                "footer": {
                    "text": "Aggressive Trading Bot"
                }
            }
            
            # Add fields for data
            if notification["data"]:
                fields = []
                for key, value in notification["data"].items():
                    if key in ["symbol", "quantity", "price", "profit_loss"]:
                        fields.append({
                            "name": key.replace("_", " ").title(),
                            "value": str(value),
                            "inline": True
                        })
                if fields:
                    embed["fields"] = fields[:25]  # Discord limit
            
            payload = {
                "embeds": [embed]
            }
            
            async with self._session.post(self.discord_webhook_url, json=payload) as response:
                if response.status not in [200, 204]:
                    error_text = await response.text()
                    logger.error(f"Discord webhook error: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
    
    def _get_discord_color(self, notification_type: NotificationType) -> int:
        """Get Discord embed color based on notification type."""
        colors = {
            NotificationType.TRADE_EXECUTED: 0x3498db,  # Blue
            NotificationType.STOP_LOSS_HIT: 0xe74c3c,  # Red
            NotificationType.TAKE_PROFIT_HIT: 0x2ecc71,  # Green
            NotificationType.TRAILING_STOP_HIT: 0xe67e22,  # Orange
            NotificationType.DAILY_LIMIT_WARNING: 0xf39c12,  # Yellow
            NotificationType.DAILY_LIMIT_HIT: 0xc0392b,  # Dark Red
            NotificationType.PROFIT_TARGET_HIT: 0x27ae60,  # Dark Green
            NotificationType.POSITION_OPENED: 0x3498db,  # Blue
            NotificationType.POSITION_CLOSED: 0x95a5a6,  # Gray
            NotificationType.BOT_STARTED: 0x2ecc71,  # Green
            NotificationType.BOT_STOPPED: 0x95a5a6,  # Gray
            NotificationType.ERROR: 0xe74c3c,  # Red
            NotificationType.INFO: 0x3498db  # Blue
        }
        return colors.get(notification_type, 0x95a5a6)


# Global instance
notification_service = NotificationService()