"""Market data API endpoints."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.db.questdb import execute_query
from app import dependencies

router = APIRouter()


class StreamStatus(BaseModel):
    """Stream status response model."""
    binance: dict
    alpaca: dict
    ingest_worker: dict
    queue_size: int


class MarketTick(BaseModel):
    """Market tick response model."""
    symbol: str
    exchange: str
    price: float
    bid_price: Optional[float]
    ask_price: Optional[float]
    bid_size: Optional[float]
    ask_size: Optional[float]
    volume: Optional[float]
    timestamp: datetime


@router.get("/stream_status", response_model=StreamStatus)
async def get_stream_status():
    """Get the status of market data streams."""
    binance_client = dependencies.binance_client
    alpaca_client = dependencies.alpaca_client
    ingest_worker = dependencies.ingest_worker
    market_data_queue = dependencies.market_data_queue
    
    status_data = {
        "binance": {
            "connected": binance_client.websocket is not None if binance_client else False,
            "running": binance_client.running if binance_client else False,
            "symbols_count": len(binance_client.symbols) if binance_client else 0,
            "reconnect_delay": binance_client.reconnect_delay if binance_client else 0,
        },
        "alpaca": {
            "connected": alpaca_client.websocket is not None if alpaca_client else False,
            "running": alpaca_client.running if alpaca_client else False,
            "authenticated": alpaca_client.authenticated if alpaca_client else False,
            "symbols_count": len(alpaca_client.symbols) if alpaca_client else 0,
            "reconnect_delay": alpaca_client.reconnect_delay if alpaca_client else 0,
        },
        "ingest_worker": ingest_worker.get_stats() if ingest_worker else {},
        "queue_size": market_data_queue.qsize() if market_data_queue else 0,
    }
    
    return StreamStatus(**status_data)


@router.get("/ticks/{symbol}", response_model=list[MarketTick])
async def get_symbol_ticks(
    symbol: str,
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    start_time: Optional[datetime] = Query(None, description="Start time for data"),
    end_time: Optional[datetime] = Query(None, description="End time for data"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of ticks to return"),
):
    """Get recent market ticks for a symbol."""
    # Build query
    query = """
        SELECT symbol, exchange, price, bid_price, ask_price, 
               bid_size, ask_size, volume, timestamp
        FROM market_ticks
        WHERE symbol = $1
    """
    params = [symbol]
    param_count = 2
    
    if exchange:
        query += f" AND exchange = ${param_count}"
        params.append(exchange)
        param_count += 1
    
    if start_time:
        query += f" AND timestamp >= ${param_count}"
        params.append(start_time)
        param_count += 1
    
    if end_time:
        query += f" AND timestamp <= ${param_count}"
        params.append(end_time)
        param_count += 1
    
    query += f" ORDER BY timestamp DESC LIMIT {limit}"
    
    try:
        rows = await execute_query(query, *params)
        return [MarketTick(**dict(row)) for row in rows]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch market data: {str(e)}"
        )


@router.get("/latest/{symbol}", response_model=MarketTick)
async def get_latest_tick(symbol: str, exchange: Optional[str] = None):
    """Get the latest tick for a symbol."""
    query = """
        SELECT symbol, exchange, price, bid_price, ask_price, 
               bid_size, ask_size, volume, timestamp
        FROM market_ticks
        WHERE symbol = $1
    """
    params = [symbol]
    
    if exchange:
        query += " AND exchange = $2"
        params.append(exchange)
    
    query += " ORDER BY timestamp DESC LIMIT 1"
    
    try:
        rows = await execute_query(query, *params)
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data found for symbol {symbol}"
            )
        return MarketTick(**dict(rows[0]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch latest tick: {str(e)}"
        )


@router.get("/symbols", response_model=list[str])
async def get_active_symbols():
    """Get list of symbols with recent data."""
    # Get symbols with data in the last hour
    query = """
        SELECT DISTINCT symbol
        FROM market_ticks
        WHERE timestamp > dateadd('h', -1, now())
        ORDER BY symbol
    """
    
    try:
        rows = await execute_query(query)
        return [row["symbol"] for row in rows]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch symbols: {str(e)}"
        )