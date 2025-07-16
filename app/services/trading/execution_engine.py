"""Trade execution engine that processes signals from Redis."""
import asyncio
import json
import logging
from datetime import datetime, time
from typing import Optional, Dict, Any
from uuid import uuid4

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.postgres import get_db_session
from app.db.optimized_postgres import optimized_db
from app.models.order import Order, OrderSide, OrderType, OrderStatus
from app.models.config import Config
from app.services.trading.alpaca_client import AlpacaClient
from app.services.trading.position_manager import PositionManager

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Execution engine that listens to trade signals and executes orders."""
    
    def __init__(self):
        settings = get_settings()
        self.redis_url = settings.REDIS_URL
        self.redis_client: Optional[redis.Redis] = None
        self.alpaca_client = AlpacaClient()
        self.position_manager = PositionManager()
        self._running = False
        self._tasks = []
        
    async def initialize(self):
        """Initialize execution engine components."""
        # Connect to Redis
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        
        # Initialize Alpaca WebSocket
        await self.alpaca_client.initialize_stream(self._handle_order_update)
        
        # Initialize position manager
        await self.position_manager.initialize()
        
        logger.info("Execution engine initialized")
        
    async def run(self):
        """Main execution loop."""
        if not self.redis_client:
            raise RuntimeError("Execution engine not initialized")
            
        self._running = True
        
        # Start Alpaca WebSocket connection
        alpaca_task = asyncio.create_task(self.alpaca_client.connect_stream())
        self._tasks.append(alpaca_task)
        
        # Start signal listener
        signal_task = asyncio.create_task(self._listen_for_signals())
        self._tasks.append(signal_task)
        
        # Start position updater
        position_task = asyncio.create_task(self.position_manager.start_price_updates())
        self._tasks.append(position_task)
        
        logger.info("Execution engine started")
        
        # Wait for tasks
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Execution engine tasks cancelled")
            
    async def _listen_for_signals(self):
        """Listen for trade signals from Redis."""
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe("trade_signals")
        
        logger.info("Listening for trade signals on Redis channel 'trade_signals'")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    signal = json.loads(message["data"])
                    await self._process_signal(signal)
                except json.JSONDecodeError:
                    logger.error(f"Invalid signal format: {message['data']}")
                except Exception as e:
                    logger.error(f"Error processing signal: {e}")
                    
    async def _process_signal(self, signal: Dict[str, Any]):
        """Process a trade signal."""
        logger.info(f"Processing signal: {signal}")
        
        # Validate signal
        required_fields = ["symbol", "side", "qty"]
        if not all(field in signal for field in required_fields):
            logger.error(f"Invalid signal: missing required fields. Got: {signal}")
            return
            
        symbol = signal["symbol"]
        side = signal["side"].lower()
        qty = float(signal["qty"])
        reason = signal.get("reason", "Manual signal")
        
        async with optimized_db.get_session() as db:
            # Validate market hours for stocks
            if not symbol.endswith("USDT") and not self._is_market_open():
                logger.warning(f"Market closed for stock {symbol}")
                await self._create_rejected_order(
                    db, symbol, side, qty, reason,
                    "Market closed for stock trading"
                )
                return
                
            # Risk checks
            risk_check = await self._check_risk_limits(db, symbol, side, qty)
            if not risk_check["allowed"]:
                logger.warning(f"Risk check failed: {risk_check['reason']}")
                await self._create_rejected_order(
                    db, symbol, side, qty, reason,
                    risk_check["reason"]
                )
                return
                
            # Create order record
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            logger.info(f"Creating order with side: {order_side}, value: {order_side.value}")
            order = Order(
                id=uuid4(),
                symbol=symbol,
                side=order_side,
                qty=qty,
                type=OrderType.MARKET,
                status=OrderStatus.PENDING,
                reason=reason
            )
            db.add(order)
            await db.flush()
            
            try:
                # Submit to Alpaca
                # Crypto orders need GTC time_in_force
                time_in_force = "gtc" if symbol.endswith("USDT") else "day"
                alpaca_result = await self.alpaca_client.submit_order(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    order_type="market",
                    time_in_force=time_in_force
                )
                
                # Update order with Alpaca info
                order.alpaca_id = alpaca_result["alpaca_id"]
                order.status = OrderStatus.SUBMITTED
                order.submitted_at = datetime.utcnow()
                
                await db.commit()
                logger.info(f"Order submitted: {order.id} / Alpaca: {order.alpaca_id}")
                
            except Exception as e:
                logger.error(f"Error submitting order to Alpaca: {e}")
                order.status = OrderStatus.REJECTED
                order.error_message = str(e)
                await db.commit()
                
    async def _handle_order_update(self, update: Dict[str, Any]):
        """Handle order update from Alpaca WebSocket."""
        logger.info(f"Order update received: {update}")
        
        try:
            alpaca_id = update.get("order", {}).get("id")
            if not alpaca_id:
                return
                
            async with optimized_db.get_session() as db:
                # Find order
                result = await db.execute(
                    select(Order).where(Order.alpaca_id == alpaca_id)
                )
                order = result.scalar_one_or_none()
                
                if not order:
                    logger.warning(f"Order not found for Alpaca ID: {alpaca_id}")
                    return
                    
                # Update order status
                event = update.get("event")
                order_data = update.get("order", {})
                
                if event == "fill":
                    order.status = OrderStatus.FILLED
                    order.filled_at = datetime.utcnow()
                    order.filled_price = float(order_data.get("filled_avg_price", 0))
                    
                    # Update position
                    await self.position_manager.update_position_on_fill(
                        db,
                        symbol=order.symbol,
                        side=order.side.value,
                        qty=order.qty,
                        price=order.filled_price
                    )
                    
                elif event == "partial_fill":
                    order.status = OrderStatus.PARTIAL
                    
                elif event == "canceled":
                    order.status = OrderStatus.CANCELLED
                    order.cancelled_at = datetime.utcnow()
                    
                elif event == "rejected":
                    order.status = OrderStatus.REJECTED
                    order.error_message = order_data.get("reject_reason", "Unknown")
                    
                await db.commit()
                logger.info(f"Order {order.id} updated to status: {order.status}")
                
        except Exception as e:
            logger.error(f"Error handling order update: {e}")
            
    async def _check_risk_limits(
        self, db: AsyncSession, symbol: str, side: str, qty: float
    ) -> Dict[str, Any]:
        """Check if order passes risk limits."""
        # Get risk configs
        configs = await self._get_risk_configs(db)
        
        # Check quantity limits
        if symbol.endswith("USDT"):  # Crypto
            max_qty = float(configs.get("max_order_qty_crypto", 1.0))
            if qty > max_qty:
                return {
                    "allowed": False,
                    "reason": f"Order quantity {qty} exceeds crypto limit {max_qty}"
                }
        else:  # Stock
            max_qty = float(configs.get("max_order_qty_stock", 100))
            if qty > max_qty:
                return {
                    "allowed": False,
                    "reason": f"Order quantity {qty} exceeds stock limit {max_qty}"
                }
                
        # Check position size limit
        max_position_usd = float(configs.get("max_position_size_usd", 10000))
        
        # Get current position value
        position_value = await self.position_manager.get_position_value(db, symbol)
        
        # Estimate new position value (rough estimate using last price)
        # In production, we'd get real-time price first
        estimated_order_value = qty * 100  # Placeholder estimate
        
        if side == "buy":
            new_position_value = position_value + estimated_order_value
        else:
            new_position_value = abs(position_value - estimated_order_value)
            
        if new_position_value > max_position_usd:
            return {
                "allowed": False,
                "reason": f"Position value ${new_position_value:.2f} would exceed limit ${max_position_usd}"
            }
            
        return {"allowed": True}
        
    async def _get_risk_configs(self, db: AsyncSession) -> Dict[str, str]:
        """Get risk management configs."""
        result = await db.execute(
            select(Config).where(Config.scope == "risk")
        )
        configs = result.scalars().all()
        return {config.key: config.value for config in configs}
        
    async def _create_rejected_order(
        self,
        db: AsyncSession,
        symbol: str,
        side: str,
        qty: float,
        reason: str,
        error_message: str
    ):
        """Create a rejected order record."""
        order = Order(
            id=uuid4(),
            symbol=symbol,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            qty=qty,
            type=OrderType.MARKET,
            status=OrderStatus.REJECTED,
            reason=reason,
            error_message=error_message
        )
        db.add(order)
        await db.commit()
        
    def _is_market_open(self) -> bool:
        """Check if US stock market is open."""
        now = datetime.utcnow()
        
        # Check if weekend
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
            
        # Convert to Eastern Time (simplified check)
        # In production, use proper timezone handling
        et_hour = (now.hour - 5) % 24  # Rough EST conversion
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        current_time = time(et_hour, now.minute)
        return market_open <= current_time <= market_close
        
    async def stop(self):
        """Stop the execution engine."""
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            
        # Close connections
        if self.redis_client:
            await self.redis_client.close()
            
        await self.alpaca_client.close()
        await self.position_manager.stop()
        
        logger.info("Execution engine stopped")