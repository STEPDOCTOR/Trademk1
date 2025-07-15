"""Alembic environment configuration."""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Add project root to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import models to ensure they're registered with Base
from app.models import Base, Config, Symbol, User  # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL from environment variable."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
    
    # Convert postgres:// to postgresql:// for compatibility
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    # Convert to asyncpg URL if needed
    if "postgresql://" in url and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()
    
    connectable = create_async_engine(
        configuration["sqlalchemy.url"],
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())