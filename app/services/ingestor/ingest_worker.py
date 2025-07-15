"""Worker for ingesting market data into QuestDB."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from app.db.questdb import execute_batch, get_questdb_pool
from app.services.ingestor.models import Tick

logger = logging.getLogger(__name__)


class IngestWorker:
    """Worker that consumes ticks from queue and batch inserts into QuestDB."""
    
    def __init__(self, queue: asyncio.Queue, batch_size: int = 100, batch_timeout: float = 1.0):
        """Initialize ingest worker.
        
        Args:
            queue: Queue to consume ticks from
            batch_size: Maximum batch size for inserts
            batch_timeout: Maximum time to wait before flushing batch (seconds)
        """
        self.queue = queue
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.running = False
        self.batch: List[Tick] = []
        self.last_flush = datetime.utcnow()
        self.stats = {
            "total_ticks": 0,
            "total_batches": 0,
            "errors": 0,
        }
        
    async def flush_batch(self) -> None:
        """Flush current batch to QuestDB."""
        if not self.batch:
            return
            
        try:
            # Prepare data for batch insert
            market_ticks_data = []
            
            for tick in self.batch:
                tick_data = tick.to_dict()
                market_ticks_data.append((
                    tick_data["symbol"],
                    tick_data["exchange"],
                    tick_data["price"],
                    tick_data["bid_price"],
                    tick_data["ask_price"],
                    tick_data["bid_size"],
                    tick_data["ask_size"],
                    tick_data["volume"],
                    tick_data["timestamp"],
                ))
            
            # Batch insert using prepared statement
            query = """
                INSERT INTO market_ticks (
                    symbol, exchange, price, bid_price, ask_price,
                    bid_size, ask_size, volume, timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """
            
            await execute_batch(query, market_ticks_data)
            
            # Update stats
            self.stats["total_ticks"] += len(self.batch)
            self.stats["total_batches"] += 1
            
            logger.debug(f"Flushed batch of {len(self.batch)} ticks to QuestDB")
            
        except Exception as e:
            logger.error(f"Failed to flush batch to QuestDB: {e}")
            self.stats["errors"] += 1
            # TODO: Implement dead letter queue or retry logic
        finally:
            # Clear batch and reset timer
            self.batch.clear()
            self.last_flush = datetime.utcnow()
            
    async def should_flush(self) -> bool:
        """Check if batch should be flushed."""
        # Flush if batch is full
        if len(self.batch) >= self.batch_size:
            return True
            
        # Flush if timeout reached
        if (datetime.utcnow() - self.last_flush).total_seconds() >= self.batch_timeout:
            return True
            
        return False
        
    async def run(self) -> None:
        """Run the ingest worker."""
        self.running = True
        logger.info("Starting ingest worker")
        
        try:
            while self.running:
                try:
                    # Try to get tick with timeout
                    tick = await asyncio.wait_for(
                        self.queue.get(), 
                        timeout=self.batch_timeout
                    )
                    
                    # Add to batch
                    self.batch.append(tick)
                    
                    # Check if we should flush
                    if await self.should_flush():
                        await self.flush_batch()
                        
                except asyncio.TimeoutError:
                    # Timeout reached, flush if we have data
                    if self.batch:
                        await self.flush_batch()
                except Exception as e:
                    logger.error(f"Error in ingest worker: {e}")
                    self.stats["errors"] += 1
                    
        finally:
            # Flush any remaining data
            if self.batch:
                await self.flush_batch()
                
            logger.info(f"Ingest worker stopped. Stats: {self.stats}")
            
    async def stop(self) -> None:
        """Stop the ingest worker."""
        logger.info("Stopping ingest worker")
        self.running = False
        
    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            **self.stats,
            "batch_size": len(self.batch),
            "last_flush": self.last_flush.isoformat(),
        }