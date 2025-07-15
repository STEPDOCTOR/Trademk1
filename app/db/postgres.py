"""PostgreSQL database session configuration."""

import logging
import os
from typing import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_async_session = None


def get_database_url() -> str:
    """Get properly formatted database URL for asyncpg."""
    url = settings.DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL is not set")
    
    # Convert postgres:// to postgresql:// for compatibility
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    # Convert to asyncpg URL if needed
    if "postgresql://" in url and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


async def init_postgres() -> None:
    """Initialize PostgreSQL connection and run migrations in dev mode."""
    global _engine, _async_session
    
    database_url = get_database_url()
    
    _engine = create_async_engine(
        database_url,
        echo=settings.DEBUG,
        poolclass=NullPool,  # Disable pooling for better connection management
        future=True,
    )
    
    _async_session = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Auto-apply migrations in development mode
    # Note: Migrations are now handled by entrypoint.sh to ensure proper timing
    
    logger.info("PostgreSQL connection initialized")


async def close_postgres() -> None:
    """Close PostgreSQL connection."""
    global _engine
    
    if _engine:
        await _engine.dispose()
        logger.info("PostgreSQL connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    if not _async_session:
        raise RuntimeError("Database not initialized. Call init_postgres() first.")
    
    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_postgres_health() -> bool:
    """Check if PostgreSQL is healthy by executing a simple query."""
    if not _engine:
        return False
    
    try:
        async with _engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
            await conn.commit()
        return True
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return False