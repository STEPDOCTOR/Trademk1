"""QuestDB connection and table management."""

import asyncio
import logging
from typing import Optional

import asyncpg
from asyncpg.pool import Pool

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Global connection pool
_questdb_pool: Optional[Pool] = None


async def init_questdb() -> None:
    """Initialize QuestDB connection pool and create tables."""
    global _questdb_pool
    
    try:
        # Create connection pool
        _questdb_pool = await asyncpg.create_pool(
            settings.QUESTDB_URL,
            min_size=10,
            max_size=20,
            command_timeout=60,
        )
        
        # Create tables if they don't exist
        await create_tables()
        
        logger.info("QuestDB connection initialized")
    except Exception as e:
        logger.error(f"Failed to initialize QuestDB: {e}")
        raise


async def close_questdb() -> None:
    """Close QuestDB connection pool."""
    global _questdb_pool
    
    if _questdb_pool:
        await _questdb_pool.close()
        logger.info("QuestDB connection closed")


async def create_tables() -> None:
    """Create QuestDB tables for market data."""
    async with _questdb_pool.acquire() as conn:
        # Market ticks table - stores real-time price data
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_ticks (
                symbol SYMBOL capacity 256 cache,
                exchange SYMBOL capacity 16 cache,
                price DOUBLE,
                bid_price DOUBLE,
                ask_price DOUBLE,
                bid_size DOUBLE,
                ask_size DOUBLE,
                volume DOUBLE,
                timestamp TIMESTAMP
            ) timestamp(timestamp) PARTITION BY DAY WAL;
        """)
        
        # Trades table - stores executed trades
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id VARCHAR,
                symbol SYMBOL capacity 256 cache,
                exchange SYMBOL capacity 16 cache,
                side SYMBOL capacity 8 cache,
                price DOUBLE,
                quantity DOUBLE,
                timestamp TIMESTAMP
            ) timestamp(timestamp) PARTITION BY DAY WAL;
        """)
        
        # Positions table - tracks current positions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                position_id VARCHAR,
                symbol SYMBOL capacity 256 cache,
                exchange SYMBOL capacity 16 cache,
                side SYMBOL capacity 8 cache,
                quantity DOUBLE,
                entry_price DOUBLE,
                current_price DOUBLE,
                pnl DOUBLE,
                status SYMBOL capacity 16 cache,
                opened_at TIMESTAMP,
                closed_at TIMESTAMP,
                timestamp TIMESTAMP
            ) timestamp(timestamp) PARTITION BY MONTH WAL;
        """)
        
        logger.info("QuestDB tables created successfully")


def get_questdb_pool() -> Pool:
    """Get QuestDB connection pool."""
    if not _questdb_pool:
        raise RuntimeError("QuestDB not initialized. Call init_questdb() first.")
    return _questdb_pool


async def execute_query(query: str, *args) -> list:
    """Execute a query and return results."""
    pool = get_questdb_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute_batch(query: str, data: list) -> None:
    """Execute batch insert."""
    pool = get_questdb_pool()
    async with pool.acquire() as conn:
        await conn.executemany(query, data)