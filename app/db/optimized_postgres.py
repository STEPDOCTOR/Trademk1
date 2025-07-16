"""Optimized PostgreSQL database configuration with connection pooling and performance enhancements."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.orm import selectinload, joinedload, subqueryload
from sqlalchemy import event

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class OptimizedDatabase:
    """Optimized database manager with connection pooling and performance features."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._connection_stats: Dict[str, Any] = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0,
            "connection_errors": 0,
            "last_error": None
        }
        
    def get_database_url(self) -> str:
        """Get properly formatted database URL for asyncpg."""
        settings = get_settings()
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
        
    async def init(self):
        """Initialize database with optimized connection pooling."""
        settings = get_settings()
        database_url = self.get_database_url()
        
        # Optimized engine configuration
        self.engine = create_async_engine(
            database_url,
            echo=settings.DEBUG and settings.ENVIRONMENT == "development",
            # Connection pool configuration
            poolclass=AsyncAdaptedQueuePool,
            pool_size=20,  # Number of persistent connections
            max_overflow=10,  # Maximum overflow connections
            pool_timeout=30,  # Timeout for getting connection from pool
            pool_recycle=3600,  # Recycle connections after 1 hour
            pool_pre_ping=True,  # Verify connections before using
            # Engine options
            connect_args={
                # asyncpg-specific optimizations
                "server_settings": {
                    "application_name": settings.APP_NAME,
                    "jit": "off"  # Disable JIT for consistent performance
                },
                "command_timeout": 60,
                "prepared_statement_cache_size": 0,  # Disable to avoid cache bloat
                # Generate unique statement names to avoid conflicts
                "prepared_statement_name_func": lambda: f"stmt_{uuid4().hex[:8]}",
            },
            # Query execution options
            execution_options={
                "isolation_level": "READ COMMITTED",
                "postgresql_readonly": False,
                "postgresql_deferrable": False,
            },
        )
        
        # Session factory with optimized settings
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
            autoflush=False,  # Manual flush for better control
            autocommit=False,
        )
        
        # Set up event listeners for monitoring
        self._setup_event_listeners()
        
        logger.info(f"Optimized PostgreSQL connection pool initialized (size={20}, overflow={10})")
        
    def _setup_event_listeners(self):
        """Set up SQLAlchemy event listeners for monitoring and optimization."""
        # Monitor connection checkout
        @event.listens_for(self.engine.sync_engine.pool, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            self._connection_stats["active_connections"] += 1
            self._connection_stats["total_connections"] += 1
            
        # Monitor connection checkin
        @event.listens_for(self.engine.sync_engine.pool, "checkin")
        def receive_checkin(dbapi_conn, connection_record):
            self._connection_stats["active_connections"] -= 1
            self._connection_stats["idle_connections"] = (
                self.engine.pool.size() - self._connection_stats["active_connections"]
            )
            
        # Monitor connection errors
        @event.listens_for(self.engine.sync_engine.pool, "invalidate")
        def receive_invalidate(dbapi_conn, connection_record, exception):
            self._connection_stats["connection_errors"] += 1
            if exception:
                self._connection_stats["last_error"] = str(exception)
                
    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("PostgreSQL connection pool closed")
            
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an optimized database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call init() first.")
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
                
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        if self.engine:
            pool = self.engine.pool
            self._connection_stats.update({
                "pool_size": pool.size(),
                "checked_in_connections": pool.checkedin(),
                "overflow": pool.overflow(),
                "total": pool.total(),
            })
        return self._connection_stats
        
    async def health_check(self) -> bool:
        """Check database health with timeout."""
        if not self.engine:
            return False
            
        try:
            async with asyncio.timeout(5):  # 5 second timeout
                async with self.engine.connect() as conn:
                    result = await conn.execute(sa.text("SELECT 1"))
                    await conn.commit()
            return True
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False


# Query optimization utilities
class QueryOptimizer:
    """Utilities for query optimization."""
    
    @staticmethod
    def with_joined_load(*relationships):
        """Create query options for joined loading (fewer queries, more data)."""
        return [joinedload(rel) for rel in relationships]
    
    @staticmethod
    def with_subquery_load(*relationships):
        """Create query options for subquery loading (balanced approach)."""
        return [subqueryload(rel) for rel in relationships]
    
    @staticmethod
    def with_select_in_load(*relationships):
        """Create query options for select-in loading (more queries, less data)."""
        return [selectinload(rel) for rel in relationships]
    
    @staticmethod
    def paginate_query(query, page: int = 1, per_page: int = 50):
        """Add pagination to query."""
        return query.limit(per_page).offset((page - 1) * per_page)
    
    @staticmethod
    def add_index_hints(query, table, index_name: str, hint_type: str = "USE"):
        """Add index hints to query (PostgreSQL specific)."""
        # PostgreSQL doesn't support index hints directly, but we can use CTEs
        # or query rewriting to influence the planner
        return query


# Connection pool monitoring
class ConnectionPoolMonitor:
    """Monitor and log connection pool statistics."""
    
    def __init__(self, db: OptimizedDatabase):
        self.db = db
        self._monitoring = False
        self._task = None
        
    async def start_monitoring(self, interval: int = 60):
        """Start monitoring connection pool statistics."""
        self._monitoring = True
        self._task = asyncio.create_task(self._monitor_loop(interval))
        
    async def stop_monitoring(self):
        """Stop monitoring."""
        self._monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
    async def _monitor_loop(self, interval: int):
        """Monitor loop that logs statistics."""
        while self._monitoring:
            try:
                stats = await self.db.get_connection_stats()
                logger.info(f"Connection pool stats: {stats}")
                
                # Warn if connection usage is high
                if stats.get("active_connections", 0) > 25:  # 80% of pool_size + overflow
                    logger.warning(f"High connection usage: {stats['active_connections']}/30")
                    
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring connection pool: {e}")
                await asyncio.sleep(interval)


# Batch query executor for bulk operations
class BatchQueryExecutor:
    """Execute queries in batches for better performance."""
    
    def __init__(self, session: AsyncSession, batch_size: int = 1000):
        self.session = session
        self.batch_size = batch_size
        
    async def bulk_insert(self, model_class, records: list):
        """Bulk insert records in batches."""
        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            self.session.add_all(batch)
            await self.session.flush()
            
    async def bulk_update(self, model_class, updates: list):
        """Bulk update records in batches."""
        for i in range(0, len(updates), self.batch_size):
            batch = updates[i:i + self.batch_size]
            await self.session.execute(
                sa.update(model_class),
                batch
            )
            await self.session.flush()


# Global optimized database instance
optimized_db = OptimizedDatabase()


# Dependency for FastAPI
async def get_optimized_db() -> AsyncGenerator[AsyncSession, None]:
    """Get optimized database session for FastAPI dependency injection."""
    async with optimized_db.get_session() as session:
        yield session