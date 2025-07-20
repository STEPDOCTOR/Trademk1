import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.rate_limiter import RateLimitMiddleware, RateLimitTiers
from app.middleware.security import SecurityMiddleware, SecurityConfig
from app.middleware.monitoring import RequestMonitoringMiddleware, DatabaseMonitoringMiddleware, CacheMonitoringDecorator
from app.middleware.compression import (
    CompressionMiddleware, ResponseOptimizationMiddleware, 
    ContentOptimizationMiddleware, ResponseSizeLimitMiddleware
)
from app.monitoring.logger import setup_logging, get_main_logger
from app.monitoring.metrics import metrics_collector, SystemMetricsCollector

from app.api.health import router as health_router
from app.api.market_data import router as market_data_router
from app.api.trading import router as trading_router
from app.api.strategies import router as strategies_router
from app.api.auth import router as auth_router
from app.api.api_keys import router as api_keys_router
from app.api.websocket import router as websocket_router
from app.api.admin import router as admin_router
from app.api.portfolio import router as portfolio_router
from app.api.preferences import router as preferences_router
from app.api.versioning import check_api_version
from app.api.documentation import router as docs_router
from app.api.autonomous import router as autonomous_router
from app.api.performance import router as performance_router
from app.api.dashboard import router as dashboard_router
from app.config.settings import settings
from app.db.postgres import close_postgres, init_postgres
from app.db.questdb import close_questdb, init_questdb
from app.services.cache import cache_service
from app.services.ingestor.alpaca_client import AlpacaStreamingClient
from app.services.ingestor.binance_client import BinanceWebSocketClient
from app.services.ingestor.ingest_worker import IngestWorker
from app.services.trading.execution_engine import ExecutionEngine
from app.services.strategies.portfolio_manager import MultiStrategyPortfolioManager
from app.services.trading.position_sync import PositionSyncService
from app.services.strategies.autonomous_trader import AutonomousTrader
from app.services.performance_tracker import performance_tracker
from app import dependencies

# Global references to background tasks
market_data_queue: Optional[asyncio.Queue] = None
binance_client: Optional[BinanceWebSocketClient] = None
alpaca_client: Optional[AlpacaStreamingClient] = None
ingest_worker: Optional[IngestWorker] = None
execution_engine: Optional[ExecutionEngine] = None
portfolio_manager: Optional[MultiStrategyPortfolioManager] = None
position_sync_service: Optional[PositionSyncService] = None
autonomous_trader: Optional[AutonomousTrader] = None
background_tasks: list[asyncio.Task] = []

# Initialize logging
logger = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_data_queue, binance_client, alpaca_client, ingest_worker, execution_engine, portfolio_manager, position_sync_service, autonomous_trader, background_tasks, logger
    
    # Setup logging first
    setup_logging(
        log_level=settings.DEBUG and "DEBUG" or "INFO",
        enable_json_logging=settings.ENVIRONMENT == "production"
    )
    logger = get_main_logger()
    logger.info("Starting Trademk1 application")
    
    # Initialize metrics restoration
    await metrics_collector.restore_from_redis()
    
    # Start system metrics collection
    system_metrics = SystemMetricsCollector(metrics_collector)
    await system_metrics.start_monitoring()
    
    # Initialize databases
    await init_postgres()
    await init_questdb()
    logger.info("Databases initialized")
    
    # Initialize cache
    try:
        await cache_service.connect()
        
        # Apply cache monitoring
        cache_monitor = CacheMonitoringDecorator(cache_service)
        cache_monitor.apply_monitoring()
        
        logger.info("Cache service connected")
    except Exception as e:
        logger.error(f"Cache service connection failed: {e}")
    
    # Initialize market data ingestion
    market_data_queue = asyncio.Queue(maxsize=10000)
    
    # Create clients and worker
    binance_client = BinanceWebSocketClient(market_data_queue)
    alpaca_client = AlpacaStreamingClient(market_data_queue)
    ingest_worker = IngestWorker(market_data_queue)
    
    # Update dependencies for other modules
    dependencies.market_data_queue = market_data_queue
    dependencies.binance_client = binance_client
    dependencies.alpaca_client = alpaca_client
    dependencies.ingest_worker = ingest_worker
    
    # Start background tasks
    background_tasks = []
    
    # Try to start Binance client (may be blocked in some regions)
    try:
        binance_task = asyncio.create_task(binance_client.run())
        background_tasks.append(binance_task)
        logger.info("Starting Binance WebSocket client")
    except Exception as e:
        logger.warning(f"Binance client failed to start (may be region blocked): {e}")
    
    # Always start the ingest worker
    background_tasks.append(asyncio.create_task(ingest_worker.run()))
    
    # Only start Alpaca if credentials are configured
    if settings.ALPACA_API_KEY and settings.ALPACA_API_SECRET:
        background_tasks.append(asyncio.create_task(alpaca_client.run()))
        
        # Initialize and start execution engine
        execution_engine = ExecutionEngine()
        await execution_engine.initialize()
        background_tasks.append(asyncio.create_task(execution_engine.run()))
        dependencies.execution_engine = execution_engine
        print("OMS execution engine started")
        
        # Initialize and start portfolio manager
        portfolio_manager = MultiStrategyPortfolioManager()
        await portfolio_manager.initialize()
        dependencies.portfolio_manager = portfolio_manager
        # Portfolio manager runs on-demand, not as a background task
        logger.info("Portfolio manager initialized")
        
        # Initialize position sync service
        position_sync_service = PositionSyncService(execution_engine.alpaca_client)
        background_tasks.append(asyncio.create_task(position_sync_service.run()))
        dependencies.position_sync_service = position_sync_service
        logger.info("Position sync service started")
        
        # Initialize performance tracker
        await performance_tracker.initialize()
        background_tasks.append(performance_tracker._update_task)
        logger.info("Performance tracker initialized")
        
        # Initialize autonomous trader
        autonomous_trader = AutonomousTrader(execution_engine)
        dependencies.autonomous_trader = autonomous_trader
        
        # Configure aggressive settings for immediate trading
        logger.info("Configuring aggressive autonomous trading settings...")
        
        # Ultra-aggressive momentum settings
        autonomous_trader.update_strategy('momentum',
            enabled=True,
            momentum_threshold=0.001,      # 0.1% - extremely sensitive
            momentum_lookback_hours=1,     # Just look at last hour
            position_size_pct=0.03,        # 3% of portfolio (~$2,200)
            max_positions=25
        )
        
        # Tighter risk management
        autonomous_trader.update_strategy('stop_loss',
            enabled=True,
            stop_loss_pct=0.02  # 2% stop loss
        )
        
        autonomous_trader.update_strategy('take_profit',
            enabled=True,
            take_profit_pct=0.05  # 5% take profit
        )
        
        # Disable rebalancing to focus on momentum
        autonomous_trader.update_strategy('portfolio_rebalance', enabled=False)
        
        # Set very frequent checking
        autonomous_trader.check_interval = 15  # Check every 15 seconds
        
        logger.info("Autonomous trader settings:")
        logger.info("  • Momentum: 0.1% threshold (ultra-sensitive)")
        logger.info("  • Check interval: 15 seconds")
        logger.info("  • Position size: 3% (~$2,200)")
        logger.info("  • Stop loss: 2%")
        logger.info("  • Take profit: 5%")
        
        # Start autonomous trader automatically
        autonomous_trader_task = asyncio.create_task(autonomous_trader.run())
        background_tasks.append(autonomous_trader_task)
        logger.info("🚀 Autonomous trader started with aggressive settings!")
    else:
        logger.warning("Alpaca credentials not configured, skipping Alpaca client, OMS, and portfolio manager")
    
    logger.info("Application startup complete")
    yield
    
    # Stop all background tasks
    logger.info("Shutting down application")
    
    # Persist metrics before shutdown
    await metrics_collector.persist_to_redis()
    
    # Stop system metrics collection
    await system_metrics.stop_monitoring()
    
    # Stop clients
    if binance_client:
        await binance_client.stop()
    if alpaca_client and settings.ALPACA_API_KEY:
        await alpaca_client.stop()
    if ingest_worker:
        await ingest_worker.stop()
    if execution_engine:
        await execution_engine.stop()
    if portfolio_manager:
        await portfolio_manager.stop()
    if position_sync_service:
        await position_sync_service.stop()
    if autonomous_trader:
        await autonomous_trader.stop()
        
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()
        
    # Wait for tasks to complete
    await asyncio.gather(*background_tasks, return_exceptions=True)
    
    # Close database connections
    await close_postgres()
    await close_questdb()
    
    # Close cache connection
    try:
        await cache_service.disconnect()
        logger.info("Cache service disconnected")
    except Exception as e:
        logger.warning(f"Cache disconnect failed: {e}")
    
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan
    )
    
    # Content optimization middleware (first - closest to the app)
    app.add_middleware(
        ContentOptimizationMiddleware,
        minify_json=settings.ENVIRONMENT == "production",
        remove_null_fields=True
    )
    
    # Response size limiting
    app.add_middleware(
        ResponseSizeLimitMiddleware,
        max_response_size=10 * 1024 * 1024,  # 10MB
        enable_streaming_threshold=1024 * 1024  # 1MB
    )
    
    # Response optimization
    app.add_middleware(
        ResponseOptimizationMiddleware,
        enable_etag=True,
        enable_caching_headers=True,
        max_age=300
    )
    
    # Compression middleware
    compression_enabled = settings.ENVIRONMENT == "production"
    if compression_enabled:
        app.add_middleware(
            CompressionMiddleware,
            minimum_size=500,
            compression_level=6
        )
    
    # Request monitoring middleware
    app.add_middleware(
        RequestMonitoringMiddleware,
        enable_detailed_logging=settings.DEBUG
    )
    
    # Security middleware
    security_config = SecurityConfig()
    if settings.ENVIRONMENT == "production":
        # Stricter settings for production
        security_config.max_requests_per_second = 5
        security_config.ddos_threshold = 50
        security_config.max_concurrent_requests_per_ip = 3
    
    app.add_middleware(SecurityMiddleware, config=security_config)
    
    # Rate limiting middleware
    rate_limit_config = RateLimitTiers.BASIC
    if settings.ENVIRONMENT == "production":
        rate_limit_config = RateLimitTiers.FREE  # More conservative for production
    
    app.add_middleware(
        RateLimitMiddleware,
        default_config=rate_limit_config,
        exempt_paths=["/docs", "/redoc", "/openapi.json", "/api/health", "/"]
    )
    
    # CORS middleware (last - furthest from the app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.ENVIRONMENT != "production" else settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    
    # Core API routes
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(market_data_router, prefix="/api/v1/market-data", tags=["market-data"])
    
    # Authentication and user management
    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(preferences_router)
    
    # Trading and strategies
    app.include_router(trading_router)
    app.include_router(strategies_router)
    
    # Portfolio analytics
    app.include_router(portfolio_router)
    
    # Autonomous trading
    app.include_router(autonomous_router, prefix="/api/v1/autonomous", tags=["autonomous"])
    
    # Performance tracking
    app.include_router(performance_router)
    
    # Real-time and admin
    app.include_router(websocket_router)
    app.include_router(admin_router)
    
    # Documentation and versioning
    app.include_router(docs_router)
    
    # Dashboard
    app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
    
    # Mount static files for dashboard
    from fastapi.staticfiles import StaticFiles
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static", "dashboard")
    if os.path.exists(static_dir):
        app.mount("/static/dashboard", StaticFiles(directory=static_dir), name="dashboard-static")
    
    @app.get("/")
    async def root():
        return {"message": "Trademk1 API", "version": "0.1.0"}
    
    return app


app = create_app()