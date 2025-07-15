"""Position manager for tracking and calculating P&L."""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.db.postgres import get_db_session
from app.db.questdb import get_questdb_connection
from app.models.position import Position

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages portfolio positions and P&L calculations."""
    
    def __init__(self):
        self._running = False
        self._update_task: Optional[asyncio.Task] = None
        self.questdb_url = "http://questdb:9000"
        
    async def initialize(self):
        """Initialize position manager."""
        logger.info("Position manager initialized")
        
    async def update_position_on_fill(
        self,
        db: AsyncSession,
        symbol: str,
        side: str,
        qty: float,
        price: float
    ):
        """Update position when an order is filled."""
        # Get or create position
        result = await db.execute(
            select(Position).where(Position.symbol == symbol)
        )
        position = result.scalar_one_or_none()
        
        if not position:
            # Create new position
            position = Position(
                id=uuid4(),
                symbol=symbol,
                qty=0.0,
                avg_price=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                market_value=0.0,
                cost_basis=0.0
            )
            db.add(position)
            
        # Update position based on side
        if side == "buy":
            # Calculate new average price
            new_total_cost = (position.qty * position.avg_price) + (qty * price)
            new_total_qty = position.qty + qty
            
            position.qty = new_total_qty
            position.avg_price = new_total_cost / new_total_qty if new_total_qty > 0 else 0
            position.cost_basis = position.qty * position.avg_price
            
        else:  # sell
            if position.qty > 0:
                # Calculate realized P&L
                realized = qty * (price - position.avg_price)
                position.realized_pnl += realized
                
            position.qty -= qty
            
            # If position is closed
            if abs(position.qty) < 0.0001:
                position.qty = 0
                position.avg_price = 0
                position.cost_basis = 0
                position.unrealized_pnl = 0
            else:
                position.cost_basis = position.qty * position.avg_price
                
        # Update market value with fill price
        position.market_value = position.qty * price
        position.last_price = price
        position.last_price_updated = datetime.utcnow()
        
        # Calculate unrealized P&L
        if position.qty != 0:
            position.unrealized_pnl = position.market_value - position.cost_basis
            
        await db.flush()
        logger.info(f"Position updated for {symbol}: qty={position.qty}, avg_price={position.avg_price}")
        
    async def start_price_updates(self):
        """Start background task to update positions with latest prices."""
        self._running = True
        
        while self._running:
            try:
                await self._update_all_positions()
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logger.error(f"Error updating positions: {e}")
                await asyncio.sleep(10)
                
    async def _update_all_positions(self):
        """Update all positions with latest prices from QuestDB."""
        async with get_db_session() as db:
            # Get all open positions
            result = await db.execute(
                select(Position).where(Position.qty != 0)
            )
            positions = result.scalars().all()
            
            if not positions:
                return
                
            # Get latest prices from QuestDB
            symbols = [pos.symbol for pos in positions]
            latest_prices = await self._get_latest_prices(symbols)
            
            # Update positions
            for position in positions:
                if position.symbol in latest_prices:
                    price = latest_prices[position.symbol]
                    position.last_price = price
                    position.last_price_updated = datetime.utcnow()
                    position.market_value = position.qty * price
                    position.unrealized_pnl = position.market_value - position.cost_basis
                    
            await db.commit()
            
    async def _get_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get latest prices from QuestDB."""
        prices = {}
        
        async with httpx.AsyncClient() as client:
            for symbol in symbols:
                try:
                    # Query QuestDB REST API
                    query = f"""
                    SELECT price 
                    FROM market_ticks 
                    WHERE symbol = '{symbol}' 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                    """
                    
                    response = await client.get(
                        f"{self.questdb_url}/exec",
                        params={"query": query}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("dataset") and len(data["dataset"]) > 0:
                            prices[symbol] = float(data["dataset"][0][0])
                            
                except Exception as e:
                    logger.error(f"Error getting price for {symbol}: {e}")
                    
        return prices
        
    async def get_position_value(self, db: AsyncSession, symbol: str) -> float:
        """Get current position value in USD."""
        result = await db.execute(
            select(Position).where(Position.symbol == symbol)
        )
        position = result.scalar_one_or_none()
        
        if position:
            return abs(position.market_value)
        return 0.0
        
    async def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """Get current portfolio snapshot."""
        async with get_db_session() as db:
            result = await db.execute(select(Position))
            positions = result.scalars().all()
            
            total_value = 0.0
            total_unrealized_pnl = 0.0
            total_realized_pnl = 0.0
            position_list = []
            
            for pos in positions:
                if pos.qty != 0:  # Only include open positions
                    total_value += pos.market_value
                    total_unrealized_pnl += pos.unrealized_pnl
                    
                total_realized_pnl += pos.realized_pnl
                
                position_list.append({
                    "symbol": pos.symbol,
                    "qty": pos.qty,
                    "avg_price": pos.avg_price,
                    "last_price": pos.last_price,
                    "market_value": pos.market_value,
                    "cost_basis": pos.cost_basis,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "realized_pnl": pos.realized_pnl,
                    "last_price_updated": pos.last_price_updated.isoformat() if pos.last_price_updated else None
                })
                
            return {
                "total_value": total_value,
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_realized_pnl": total_realized_pnl,
                "total_pnl": total_unrealized_pnl + total_realized_pnl,
                "positions": position_list,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    async def stop(self):
        """Stop the position manager."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()