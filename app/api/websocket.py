"""WebSocket API for real-time data streaming."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.security import HTTPBearer
from jose import JWTError
import redis.asyncio as redis

from app.auth.security import decode_token
from app.config.settings import get_settings
from app.db.postgres import get_db_session
from app.services.cache import cache_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections and subscriptions."""
    
    def __init__(self):
        # Active connections by user
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Subscriptions by connection
        self.subscriptions: Dict[WebSocket, Set[str]] = {}
        # Subscription channels
        self.channels: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new connection."""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        self.subscriptions[websocket] = set()
        
        logger.info(f"WebSocket connected for user: {user_id}")
        
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a connection and its subscriptions."""
        # Remove from active connections
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                
        # Remove subscriptions
        if websocket in self.subscriptions:
            for channel in self.subscriptions[websocket]:
                if channel in self.channels:
                    self.channels[channel].discard(websocket)
                    if not self.channels[channel]:
                        del self.channels[channel]
            del self.subscriptions[websocket]
            
        logger.info(f"WebSocket disconnected for user: {user_id}")
        
    async def subscribe(self, websocket: WebSocket, channel: str):
        """Subscribe a connection to a channel."""
        if websocket not in self.subscriptions:
            return
            
        self.subscriptions[websocket].add(channel)
        
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(websocket)
        
        logger.debug(f"WebSocket subscribed to channel: {channel}")
        
    async def unsubscribe(self, websocket: WebSocket, channel: str):
        """Unsubscribe a connection from a channel."""
        if websocket in self.subscriptions:
            self.subscriptions[websocket].discard(channel)
            
        if channel in self.channels:
            self.channels[channel].discard(websocket)
            if not self.channels[channel]:
                del self.channels[channel]
                
    async def send_personal_message(self, message: dict, user_id: str):
        """Send message to all connections of a specific user."""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
                    
            # Clean up disconnected
            for conn in disconnected:
                self.active_connections[user_id].discard(conn)
                
    async def broadcast_to_channel(self, channel: str, message: dict):
        """Broadcast message to all subscribers of a channel."""
        if channel in self.channels:
            disconnected = []
            for connection in self.channels[channel]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
                    
            # Clean up disconnected
            for conn in disconnected:
                self.channels[channel].discard(conn)


# Global connection manager
manager = ConnectionManager()


# Message types
class MessageType:
    # Client -> Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    
    # Server -> Client
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"
    ERROR = "error"
    
    # Data messages
    MARKET_DATA = "market_data"
    ORDER_UPDATE = "order_update"
    POSITION_UPDATE = "position_update"
    PORTFOLIO_UPDATE = "portfolio_update"
    STRATEGY_UPDATE = "strategy_update"
    NOTIFICATION = "notification"


# Available channels
class Channel:
    @staticmethod
    def market_data(symbol: str) -> str:
        return f"market:{symbol}"
        
    @staticmethod
    def orders(user_id: str) -> str:
        return f"orders:{user_id}"
        
    @staticmethod
    def positions(user_id: str) -> str:
        return f"positions:{user_id}"
        
    @staticmethod
    def portfolio(user_id: str) -> str:
        return f"portfolio:{user_id}"
        
    @staticmethod
    def strategies(user_id: str) -> str:
        return f"strategies:{user_id}"
        
    @staticmethod
    def notifications(user_id: str) -> str:
        return f"notifications:{user_id}"


async def authenticate_websocket(websocket: WebSocket, token: str) -> Optional[Dict[str, Any]]:
    """Authenticate WebSocket connection using JWT token."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return payload
    except (JWTError, ValueError):
        return None


@router.websocket("/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time data streaming.
    
    Authentication: Pass JWT token as query parameter
    
    Message format:
    {
        "type": "subscribe|unsubscribe|ping",
        "channel": "market:AAPL|orders|positions|etc",
        "data": {...}  # Optional additional data
    }
    """
    # Authenticate
    auth_payload = await authenticate_websocket(websocket, token)
    if not auth_payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return
        
    user_id = auth_payload.get("sub")
    
    # Connect
    await manager.connect(websocket, user_id)
    
    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id
    })
    
    # Auto-subscribe to user channels
    user_channels = [
        Channel.orders(user_id),
        Channel.positions(user_id),
        Channel.portfolio(user_id),
        Channel.notifications(user_id)
    ]
    
    for channel in user_channels:
        await manager.subscribe(websocket, channel)
        
    try:
        # Start Redis subscription task
        redis_task = asyncio.create_task(
            handle_redis_messages(websocket, user_id)
        )
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                await handle_client_message(websocket, user_id, data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": MessageType.ERROR,
                    "error": "Invalid JSON"
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        # Cancel Redis task
        redis_task.cancel()
        
        # Disconnect
        manager.disconnect(websocket, user_id)


async def handle_client_message(
    websocket: WebSocket,
    user_id: str,
    message: dict
):
    """Handle messages from client."""
    msg_type = message.get("type")
    
    if msg_type == MessageType.SUBSCRIBE:
        channel = message.get("channel")
        if channel and is_valid_channel(channel, user_id):
            await manager.subscribe(websocket, channel)
            await websocket.send_json({
                "type": MessageType.SUBSCRIBED,
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            await websocket.send_json({
                "type": MessageType.ERROR,
                "error": "Invalid channel"
            })
            
    elif msg_type == MessageType.UNSUBSCRIBE:
        channel = message.get("channel")
        if channel:
            await manager.unsubscribe(websocket, channel)
            await websocket.send_json({
                "type": MessageType.UNSUBSCRIBED,
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat()
            })
            
    elif msg_type == MessageType.PING:
        await websocket.send_json({
            "type": MessageType.PONG,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    else:
        await websocket.send_json({
            "type": MessageType.ERROR,
            "error": f"Unknown message type: {msg_type}"
        })


def is_valid_channel(channel: str, user_id: str) -> bool:
    """Validate if user can subscribe to channel."""
    # Market data channels are public
    if channel.startswith("market:"):
        return True
        
    # User-specific channels
    if channel in [
        Channel.orders(user_id),
        Channel.positions(user_id),
        Channel.portfolio(user_id),
        Channel.strategies(user_id),
        Channel.notifications(user_id)
    ]:
        return True
        
    return False


async def handle_redis_messages(websocket: WebSocket, user_id: str):
    """Subscribe to Redis pub/sub and forward messages to WebSocket."""
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        pubsub = redis_client.pubsub()
        
        # Subscribe to user-specific channels
        await pubsub.subscribe(
            f"ws:user:{user_id}",
            f"ws:orders:{user_id}",
            f"ws:positions:{user_id}",
            f"ws:portfolio:{user_id}"
        )
        
        # Listen for messages
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    
                    # Determine channel from Redis channel
                    redis_channel = message["channel"]
                    if redis_channel.startswith("ws:orders:"):
                        channel = Channel.orders(user_id)
                        msg_type = MessageType.ORDER_UPDATE
                    elif redis_channel.startswith("ws:positions:"):
                        channel = Channel.positions(user_id)
                        msg_type = MessageType.POSITION_UPDATE
                    elif redis_channel.startswith("ws:portfolio:"):
                        channel = Channel.portfolio(user_id)
                        msg_type = MessageType.PORTFOLIO_UPDATE
                    else:
                        channel = Channel.notifications(user_id)
                        msg_type = MessageType.NOTIFICATION
                        
                    # Check if websocket is subscribed to this channel
                    if websocket in manager.subscriptions and channel in manager.subscriptions[websocket]:
                        await websocket.send_json({
                            "type": msg_type,
                            "channel": channel,
                            "data": data,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in Redis message: {message['data']}")
                except Exception as e:
                    logger.error(f"Error forwarding Redis message: {e}")
                    
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe()
        await redis_client.close()


# Service functions to publish updates
async def publish_order_update(user_id: str, order_data: dict):
    """Publish order update to WebSocket subscribers."""
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        await redis_client.publish(
            f"ws:orders:{user_id}",
            json.dumps(order_data)
        )
    finally:
        await redis_client.close()


async def publish_position_update(user_id: str, position_data: dict):
    """Publish position update to WebSocket subscribers."""
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        await redis_client.publish(
            f"ws:positions:{user_id}",
            json.dumps(position_data)
        )
    finally:
        await redis_client.close()


async def publish_portfolio_update(user_id: str, portfolio_data: dict):
    """Publish portfolio update to WebSocket subscribers."""
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        await redis_client.publish(
            f"ws:portfolio:{user_id}",
            json.dumps(portfolio_data)
        )
    finally:
        await redis_client.close()


async def publish_notification(user_id: str, notification: dict):
    """Publish notification to user."""
    settings = get_settings()
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        await redis_client.publish(
            f"ws:user:{user_id}",
            json.dumps(notification)
        )
    finally:
        await redis_client.close()