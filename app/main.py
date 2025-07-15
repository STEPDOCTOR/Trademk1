import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.market_data import router as market_data_router
from app.config.settings import settings
from app.db.postgres import close_postgres, init_postgres
from app.db.questdb import close_questdb, init_questdb
from app.services.ingestor.alpaca_client import AlpacaStreamingClient
from app.services.ingestor.binance_client import BinanceWebSocketClient
from app.services.ingestor.ingest_worker import IngestWorker

# Global references to background tasks
market_data_queue: Optional[asyncio.Queue] = None
binance_client: Optional[BinanceWebSocketClient] = None
alpaca_client: Optional[AlpacaStreamingClient] = None
ingest_worker: Optional[IngestWorker] = None
background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_data_queue, binance_client, alpaca_client, ingest_worker, background_tasks
    
    # Initialize databases
    await init_postgres()
    await init_questdb()
    
    # Initialize market data ingestion
    market_data_queue = asyncio.Queue(maxsize=10000)
    
    # Create clients and worker
    binance_client = BinanceWebSocketClient(market_data_queue)
    alpaca_client = AlpacaStreamingClient(market_data_queue)
    ingest_worker = IngestWorker(market_data_queue)
    
    # Start background tasks
    background_tasks = [
        asyncio.create_task(binance_client.run()),
        asyncio.create_task(ingest_worker.run()),
    ]
    
    # Only start Alpaca if credentials are configured
    if settings.ALPACA_API_KEY and settings.ALPACA_API_SECRET:
        background_tasks.append(asyncio.create_task(alpaca_client.run()))
    else:
        print("Warning: Alpaca credentials not configured, skipping Alpaca client")
    
    print("Starting up...")
    yield
    
    # Stop all background tasks
    print("Shutting down...")
    
    # Stop clients
    if binance_client:
        await binance_client.stop()
    if alpaca_client and settings.ALPACA_API_KEY:
        await alpaca_client.stop()
    if ingest_worker:
        await ingest_worker.stop()
        
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()
        
    # Wait for tasks to complete
    await asyncio.gather(*background_tasks, return_exceptions=True)
    
    # Close database connections
    await close_postgres()
    await close_questdb()
    
    print("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(market_data_router, prefix="/api/v1/market-data", tags=["market-data"])
    
    @app.get("/")
    async def root():
        return {"message": "Trademk1 API", "version": "0.1.0"}
    
    return app


app = create_app()