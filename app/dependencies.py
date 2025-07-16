"""Application dependencies for dependency injection."""

from typing import Optional
import asyncio

# Global references to be set by main.py
market_data_queue: Optional[asyncio.Queue] = None
binance_client = None
alpaca_client = None
ingest_worker = None
execution_engine = None
portfolio_manager = None
position_sync_service = None
autonomous_trader = None


def get_binance_client():
    """Get the global Binance client instance."""
    return binance_client


def get_ingest_worker():
    """Get the global ingest worker instance."""
    return ingest_worker


def get_market_data_queue():
    """Get the global market data queue."""
    return market_data_queue