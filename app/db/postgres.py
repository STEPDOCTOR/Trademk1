"""PostgreSQL database session configuration with optimized pooling."""

import logging
import os
from typing import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config.settings import settings
from app.db.optimized_postgres import optimized_db, get_optimized_db
from app.db.query_analyzer import query_analyzer, QueryMonitoringMiddleware

logger = logging.getLogger(__name__)

# Global engine and session factory (legacy support)
_engine = None
_async_session = None

# Export optimized components
__all__ = ['get_db', 'init_postgres', 'close_postgres', 'check_postgres_health',
           'optimized_db', 'get_optimized_db', 'query_analyzer']


def get_database_url() -> str:
    """Get properly formatted database URL for asyncpg."""
    return optimized_db.get_database_url()


async def init_postgres() -> None:
    """Initialize PostgreSQL connection with optimized pooling."""
    global _engine, _async_session
    
    # Initialize optimized database
    await optimized_db.init()
    
    # Set legacy globals for compatibility
    _engine = optimized_db.engine
    _async_session = optimized_db.session_factory
    
    # Start query monitoring in development
    if settings.DEBUG:
        query_analyzer.start_monitoring()
        monitoring_middleware = QueryMonitoringMiddleware(query_analyzer)
        monitoring_middleware.register(_engine)
    
    # Start connection pool monitoring
    if settings.ENVIRONMENT in ["development", "staging"]:
        from app.db.optimized_postgres import ConnectionPoolMonitor
        monitor = ConnectionPoolMonitor(optimized_db)
        await monitor.start_monitoring(interval=300)  # Log every 5 minutes
    
    logger.info("Optimized PostgreSQL connection initialized")


async def close_postgres() -> None:
    """Close PostgreSQL connection."""
    global _engine
    
    # Stop query monitoring
    if query_analyzer._monitoring:
        query_analyzer.stop_monitoring()
    
    # Close optimized database
    await optimized_db.close()
    
    # Legacy cleanup
    if _engine:
        await _engine.dispose()
        logger.info("PostgreSQL connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session (optimized version)."""
    async with optimized_db.get_session() as session:
        yield session


# Legacy function for compatibility
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Legacy function - use get_db() instead."""
    async with get_db() as session:
        yield session


async def check_postgres_health() -> bool:
    """Check if PostgreSQL is healthy by executing a simple query."""
    return await optimized_db.health_check()