"""Position synchronization service to sync Alpaca positions with local database."""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.optimized_postgres import optimized_db
from app.models.position import Position
from app.services.trading.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


class PositionSyncService:
    """Service to synchronize positions between Alpaca and local database."""
    
    def __init__(self, alpaca_client: AlpacaClient):
        """Initialize position sync service.
        
        Args:
            alpaca_client: Alpaca client instance
        """
        self.alpaca_client = alpaca_client
        self.running = False
        self.sync_interval = 30  # Sync every 30 seconds
        
    async def sync_positions(self):
        """Sync positions from Alpaca to local database."""
        try:
            # Get positions from Alpaca
            alpaca_positions = await self.alpaca_client.get_positions()
            
            async with optimized_db.get_session() as db:
                # Get existing positions from database
                result = await db.execute(select(Position))
                db_positions = {pos.symbol: pos for pos in result.scalars().all()}
                
                # Track which positions we've seen
                seen_symbols = set()
                
                # Update or create positions
                for symbol, pos_data in alpaca_positions.items():
                    seen_symbols.add(symbol)
                    
                    if symbol in db_positions:
                        # Update existing position
                        position = db_positions[symbol]
                        position.qty = pos_data["qty"]
                        position.avg_price = pos_data["avg_price"]
                        position.market_value = pos_data["market_value"]
                        position.cost_basis = pos_data["cost_basis"]
                        position.unrealized_pnl = pos_data["unrealized_pnl"]
                        position.last_price = pos_data["current_price"]
                        position.last_price_updated = datetime.utcnow()
                    else:
                        # Create new position
                        position = Position(
                            id=uuid4(),
                            symbol=symbol,
                            qty=pos_data["qty"],
                            avg_price=pos_data["avg_price"],
                            market_value=pos_data["market_value"],
                            cost_basis=pos_data["cost_basis"],
                            unrealized_pnl=pos_data["unrealized_pnl"],
                            realized_pnl=0.0,
                            last_price=pos_data["current_price"],
                            last_price_updated=datetime.utcnow()
                        )
                        db.add(position)
                
                # Remove positions that no longer exist in Alpaca
                for symbol, position in db_positions.items():
                    if symbol not in seen_symbols and position.qty != 0:
                        position.qty = 0
                        position.market_value = 0
                        position.unrealized_pnl = 0
                        logger.info(f"Closed position: {symbol}")
                
                await db.commit()
                logger.info(f"Synced {len(alpaca_positions)} positions from Alpaca")
                
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            
    async def get_position_summary(self) -> Dict[str, any]:
        """Get summary of all positions."""
        async with optimized_db.get_session() as db:
            result = await db.execute(
                select(Position).where(Position.qty != 0)
            )
            positions = result.scalars().all()
            
            total_value = sum(pos.market_value for pos in positions)
            total_cost = sum(pos.cost_basis for pos in positions)
            total_pnl = sum(pos.unrealized_pnl for pos in positions)
            
            stocks = [p for p in positions if not p.symbol.endswith("USD")]
            crypto = [p for p in positions if p.symbol.endswith("USD")]
            
            return {
                "total_positions": len(positions),
                "total_value": total_value,
                "total_cost": total_cost,
                "total_unrealized_pnl": total_pnl,
                "total_pnl_pct": (total_pnl / total_cost * 100) if total_cost > 0 else 0,
                "stock_positions": len(stocks),
                "crypto_positions": len(crypto),
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "qty": pos.qty,
                        "value": pos.market_value,
                        "pnl": pos.unrealized_pnl,
                        "pnl_pct": (pos.unrealized_pnl / pos.cost_basis * 100) if pos.cost_basis > 0 else 0
                    }
                    for pos in positions
                ]
            }
            
    async def run(self):
        """Run the position sync service."""
        self.running = True
        logger.info("Starting position sync service")
        
        # Initial sync
        await self.sync_positions()
        
        while self.running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self.sync_positions()
            except Exception as e:
                logger.error(f"Error in position sync loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying
                
    async def stop(self):
        """Stop the position sync service."""
        logger.info("Stopping position sync service")
        self.running = False