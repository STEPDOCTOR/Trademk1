# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trademk1 - An autonomous real-time trading platform for U.S. stocks and cryptocurrencies, built with FastAPI, PostgreSQL, and Docker. Features automated trading strategies with stop loss, take profit, momentum trading, and portfolio rebalancing.

## Development Setup

### Quick Start Options

#### Option 1: Automated Setup (Recommended)
```bash
# Interactive setup with user creation and optional demo strategy
./autostart.sh

# Or use Make commands
make setup  # First-time setup
make start  # Start services
```

#### Option 2: Quick Demo Mode
```bash
# Zero-configuration demo mode (no Alpaca keys required)
./quickstart.sh
```

#### Option 3: Manual Docker Setup
```bash
# Start all services (migrations run automatically)
docker compose up --build

# Start with file watch (recommended for development)
docker compose watch

# Stop all services
docker compose down
```

#### Option 4: Aggressive Autonomous Trading Mode (Active)
```bash
# Currently configured with ultra-aggressive settings
# - Momentum threshold: 0.1% (very sensitive)
# - Check interval: 15 seconds
# - Stop loss: 2%
# - Take profit: 5%
# - Auto-starts on docker compose up

# To activate manually:
python3 ACTIVATE_BOT.py
# or
./START_AUTONOMOUS_BOT.sh
```

### Helper Scripts
- `autostart.sh` - Interactive setup with user creation
- `quickstart.sh` - Zero-config demo mode
- `api.sh` - API helper for common operations
- `Makefile` - Comprehensive project management

### Python Version
This project uses Python 3.12.

## Project Structure

```
/app
├── api/              # API endpoints
│   ├── autonomous.py # Autonomous trading control
│   ├── health.py     # Health check endpoints with DB status
│   ├── market_data.py # Market data query endpoints
│   ├── auth.py       # Authentication (login, register, JWT)
│   ├── api_keys.py   # API key management
│   ├── trading.py    # Trading and order management
│   ├── strategies.py # Strategy management and backtesting
│   ├── portfolio.py  # Portfolio analytics and tracking
│   ├── preferences.py # User preferences and notifications
│   ├── websocket.py  # Real-time WebSocket streaming
│   ├── admin.py      # Admin tools and system monitoring
│   ├── versioning.py # API versioning and compatibility
│   └── documentation.py # Enhanced OpenAPI documentation
├── auth/             # Authentication system
│   ├── dependencies.py # Auth dependencies and user validation
│   └── security.py   # JWT tokens, password hashing, API keys
├── config/           # Configuration
│   └── settings.py   # Pydantic settings from .env
├── db/               # Database layer
│   ├── postgres.py   # Optimized PostgreSQL with connection pooling
│   ├── optimized_postgres.py # Advanced connection management
│   ├── query_analyzer.py # Query performance analysis
│   └── questdb.py    # QuestDB connection and tables
├── middleware/       # HTTP middleware
│   ├── rate_limiter.py # Rate limiting and API throttling
│   ├── security.py   # IP filtering, DDoS protection
│   ├── monitoring.py # Request monitoring and metrics
│   └── compression.py # Response compression and optimization
├── models/           # SQLAlchemy models
│   ├── base.py       # Base model with id, created_at, updated_at
│   ├── user.py       # Enhanced user model with relationships
│   ├── user_portfolio.py # User portfolio and preferences
│   ├── api_key.py    # API key management model
│   ├── audit_log.py  # Audit logging for compliance
│   ├── symbol.py     # Symbol model for trading assets
│   ├── config.py     # Config model for app settings
│   ├── order.py      # Order model for trade execution
│   └── position.py   # Position model for portfolio tracking
├── monitoring/       # Monitoring and observability
│   ├── logger.py     # Structured logging system
│   └── metrics.py    # Application metrics collection
├── services/         # Business logic services
│   ├── ingestor/     # Market data ingestion
│   │   ├── models.py         # Tick dataclass and constants
│   │   ├── binance_client.py # Binance WebSocket client
│   │   ├── alpaca_client.py  # Alpaca streaming client
│   │   └── ingest_worker.py  # Batch processing worker
│   ├── trading/      # Order management system
│   │   ├── alpaca_client.py  # Alpaca paper trading wrapper
│   │   ├── execution_engine.py # Trade signal processor
│   │   ├── position_manager.py # Position & P&L tracker
│   │   └── position_sync.py  # Alpaca position synchronization
│   ├── strategies/   # Trading strategy framework
│   │   ├── base.py           # Abstract strategy base classes
│   │   ├── sma_crossover.py  # SMA crossover strategy
│   │   ├── momentum.py       # Momentum strategy
│   │   ├── backtesting.py    # Backtesting engine
│   │   ├── risk_manager.py   # Advanced risk management
│   │   ├── portfolio_manager.py # Multi-strategy management
│   │   └── autonomous_trader.py # Autonomous trading system
│   ├── cache.py      # Redis caching service
│   ├── portfolio_analytics.py # Portfolio performance analytics
│   ├── notifications.py # User notification system
│   └── audit_logger.py # Audit logging service
└── main.py           # FastAPI app with background tasks

/alembic
├── versions/         # Database migrations
│   ├── 0001_initial.py # Initial schema with triggers
│   └── 0002_orders_positions.py # OMS tables and risk configs
└── env.py            # Async migration configuration

/docker
├── app.dockerfile    # FastAPI container definition
├── entrypoint.sh     # Startup script with migrations
└── wait-for-it.sh    # Database readiness check

/tests
├── test_health.py    # Health endpoint tests
├── test_db_models.py # Database CRUD tests
├── test_market_ingestion.py # WebSocket ingestion tests
└── test_oms.py       # Order management system tests
```

## Database Schema

### PostgreSQL (Application Data)

#### Base Model
All models inherit:
- `id`: UUID primary key
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone (auto-updated via trigger)

#### Models
- **User**: Enhanced with full_name, phone, verification, relationships
- **UserPortfolio**: Portfolio tracking with P&L and allocations
- **UserPreferences**: User settings, notifications, trading preferences
- **APIKey**: API key management with scoped permissions and rate limits
- **AuditLog**: Comprehensive audit trail for compliance
- **Symbol**: ticker, name, exchange, asset_type, is_active, metadata_json
- **Config**: key, value, scope, description
- **Order**: symbol, side, qty, type, status, alpaca_id, filled_price, reason
- **Position**: symbol, qty, avg_price, unrealized_pnl, realized_pnl, market_value

### QuestDB (Time-Series Market Data)

#### Tables
- **market_ticks**: Real-time price data (symbol, exchange, price, bid/ask, volume, timestamp)
- **trades**: Executed trades log
- **positions**: Current trading positions with P&L tracking

## Testing

```bash
# Run all tests
source .venv/bin/activate
pytest tests/

# Run specific test file
pytest tests/test_db_models.py -v
pytest tests/test_market_ingestion.py -v
pytest tests/test_oms.py -v

# Run with coverage
pytest tests/ --cov=app
```

## Market Data Ingestion

```bash
# Monitor ingestion status
curl http://localhost:8000/api/v1/market-data/stream_status | jq

# Get latest Bitcoin price
curl http://localhost:8000/api/v1/market-data/latest/BTCUSDT | jq

# Get historical ticks
curl "http://localhost:8000/api/v1/market-data/ticks/BTCUSDT?limit=100" | jq

# List active symbols
curl http://localhost:8000/api/v1/market-data/symbols | jq

# Access QuestDB Web Console
open http://localhost:9000
```

## Database Migrations

```bash
# Migrations run automatically on startup in development

# Manual migration commands:
docker compose exec app alembic upgrade head
docker compose exec app alembic revision --autogenerate -m "description"
docker compose exec app alembic current
docker compose exec app alembic downgrade -1
```

## Git Workflow

Repository: https://github.com/STEPDOCTOR/Trademk1

Always ask user before committing. To update GitHub:
```bash
git add .
git commit -m "Description of changes"
git push
```

## Quick Reference

### Using Make Commands
```bash
# Service management
make start      # Start all services
make stop       # Stop services
make restart    # Restart services
make status     # Check health
make logs       # Follow logs

# Development
make dev        # Start with auto-reload
make test       # Run tests
make shell      # App container shell
make db-shell   # PostgreSQL shell
make redis-cli  # Redis CLI

# Trading operations
make positions  # View positions
make orders     # View orders
make portfolio  # Portfolio summary
make strategies # List strategies
```

### Using API Helper
```bash
# After running autostart.sh or make setup
./api.sh positions              # View positions
./api.sh orders                 # View orders
./api.sh portfolio              # Portfolio summary
./api.sh strategies             # List strategies
./api.sh buy AAPL 10           # Buy 10 shares of AAPL
./api.sh sell BTCUSDT 0.1      # Sell 0.1 Bitcoin
```

## API Endpoints

### Health & Documentation
- `GET /` - Root endpoint
- `GET /api/health` - Basic health check
- `GET /api/health/detailed` - Detailed health with PostgreSQL status
- `GET /api/docs/` - Interactive API documentation
- `GET /api/docs/openapi.json` - OpenAPI schema
- `GET /api/docs/examples` - API usage examples

### Authentication & User Management
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login (JWT tokens)
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user info
- `POST /api/v1/auth/logout` - User logout

### API Keys
- `POST /api/v1/api-keys/` - Create API key
- `GET /api/v1/api-keys/` - List user's API keys
- `PATCH /api/v1/api-keys/{key_id}` - Update API key
- `DELETE /api/v1/api-keys/{key_id}` - Delete API key

### Market Data
- `GET /api/v1/market-data/stream_status` - WebSocket connection and ingestion status
- `GET /api/v1/market-data/ticks/{symbol}` - Historical market ticks with filtering
- `GET /api/v1/market-data/latest/{symbol}` - Latest tick for a symbol
- `GET /api/v1/market-data/symbols` - List of actively traded symbols

### Trading (OMS)
- `POST /api/v1/trading/signal` - Submit trade signal for execution
- `GET /api/v1/trading/orders` - List orders with filtering
- `GET /api/v1/trading/orders/{order_id}` - Get specific order details
- `GET /api/v1/trading/positions` - View current positions
- `GET /api/v1/trading/portfolio` - Portfolio snapshot with P&L

### Autonomous Trading
- `GET /api/v1/autonomous/status` - Autonomous trading system status
- `POST /api/v1/autonomous/start` - Start autonomous trading
- `POST /api/v1/autonomous/stop` - Stop autonomous trading
- `PATCH /api/v1/autonomous/strategy/{strategy_type}` - Update strategy configuration
- `POST /api/v1/autonomous/force-cycle` - Force immediate trading cycle
- `GET /api/v1/autonomous/position-summary` - Current position summary

### Strategies
- `POST /api/v1/strategies/create` - Create new strategy
- `GET /api/v1/strategies/list` - List user strategies
- `POST /api/v1/strategies/backtest` - Run strategy backtest
- `GET /api/v1/strategies/performance/{strategy_id}` - Get strategy performance
- `POST /api/v1/strategies/start/{strategy_id}` - Start strategy execution
- `POST /api/v1/strategies/stop/{strategy_id}` - Stop strategy execution

### Portfolio Analytics
- `GET /api/v1/portfolio/summary` - Portfolio overview
- `GET /api/v1/portfolio/snapshot` - Current portfolio snapshot
- `GET /api/v1/portfolio/allocation` - Asset allocation breakdown
- `GET /api/v1/portfolio/performance` - Performance metrics
- `GET /api/v1/portfolio/analytics/risk-metrics` - Risk analysis

### User Preferences & Notifications
- `GET /api/v1/preferences/` - Get user preferences
- `PATCH /api/v1/preferences/` - Update user preferences
- `GET /api/v1/preferences/notifications` - Get notifications
- `POST /api/v1/preferences/notifications/{id}/read` - Mark notification read
- `POST /api/v1/preferences/price-alerts` - Create price alert

### WebSocket Streaming
- `WS /ws/stream` - Real-time data streaming
  - Channels: market data, orders, positions, portfolio, notifications
  - Authentication via JWT token in query parameter

### Admin & Monitoring (Superuser only)
- `GET /api/v1/admin/health` - System health status
- `GET /api/v1/admin/database/stats` - Database statistics
- `GET /api/v1/admin/metrics/detailed` - Application metrics
- `GET /api/v1/admin/security/stats` - Security statistics
- `POST /api/v1/admin/security/block-ip` - Block IP address
- `GET /api/v1/admin/rate-limits/stats` - Rate limiting statistics

## Environment Variables

Configure in `.env` file (see `.env.example`):

### Application
- `APP_NAME` - Application name
- `DEBUG` - Debug mode
- `ENVIRONMENT` - Environment (development/production)
- `SECRET_KEY` - Secret key for security
- `CORS_ORIGINS` - Allowed CORS origins

### Databases
- `DATABASE_URL` - PostgreSQL connection (use asyncpg format)
- `REDIS_URL` - Redis connection
- `QUESTDB_URL` - QuestDB connection for time-series data

### Market Data & Trading
- `BINANCE_API_URL` - Binance WebSocket endpoint
- `ALPACA_API_KEY` - Alpaca API key (required for OMS)
- `ALPACA_API_SECRET` - Alpaca secret key
- `ALPACA_BASE_URL` - Alpaca API base URL
- `ALPACA_PAPER_BASE_URL` - Paper trading endpoint
- `ALPACA_KEY_ID` - Alpaca key ID (same as API_KEY)
- `ALPACA_SECRET_KEY` - Alpaca secret (same as API_SECRET)

## Docker Compose Configuration

- Uses `compose.yaml` (modern format)
- Watch mode configured for `app/`, `tests/`, and `alembic/`
- Services:
  - **app**: FastAPI application with auto-reload
  - **db**: PostgreSQL 15 for application data
  - **redis**: Redis 7 for caching/queuing
  - **questdb**: QuestDB 7.3.10 for time-series market data
- Automatic health checks and migrations
- QuestDB ports: 9000 (Web Console), 9009 (InfluxDB protocol), 8812 (PostgreSQL wire)

## Completed Features

### Phase 1 - Infrastructure
- ✅ FastAPI backend with async support
- ✅ PostgreSQL integration with asyncpg
- ✅ Alembic migrations with auto-update triggers
- ✅ Health endpoints with database status
- ✅ Docker Compose with hot-reload
- ✅ Comprehensive test setup
- ✅ Environment-based configuration

### Phase 2 - Market Data Ingestion
- ✅ QuestDB integration for time-series data
- ✅ Binance WebSocket client for top 15 cryptocurrencies
- ✅ Alpaca streaming client for US stocks (paper trading)
- ✅ Unified Tick dataclass for all exchanges
- ✅ Batch ingestion worker with configurable size/timeout
- ✅ Market data API endpoints
- ✅ Background task management in FastAPI
- ✅ Automatic reconnection with exponential backoff

### Phase 3 - Trading Engine (Complete)
- ✅ Order management system with Alpaca integration
- ✅ Position tracking and P&L calculation
- ✅ Risk management rules (position limits, order size)
- ✅ Redis-based signal processing
- ✅ Real-time order status updates via WebSocket
- ✅ Trading API endpoints
- ✅ Comprehensive OMS tests
- ✅ Market hours validation
- ✅ Trading strategies framework with base classes
- ✅ Example strategies (SMA Crossover, Momentum)
- ✅ Strategy backtesting engine with metrics
- ✅ Advanced risk management (drawdown, correlation, VaR)
- ✅ Multi-strategy portfolio management
- ✅ Performance analytics and reporting
- ✅ Strategy configuration system with database storage
- ✅ Strategy API endpoints
- ✅ Comprehensive strategy documentation

### Phase 4 - User Management & Infrastructure (Complete)
- ✅ **Authentication & Security**
  - ✅ JWT authentication with refresh tokens
  - ✅ User registration and login system
  - ✅ Role-based access control (RBAC)
  - ✅ API key management with scoped permissions
  - ✅ Audit logging for compliance
- ✅ **Performance & Scalability**
  - ✅ Redis caching layer for performance optimization
  - ✅ Connection pooling and query optimization
  - ✅ Rate limiting and API throttling
  - ✅ DDoS protection and IP filtering
  - ✅ Data compression and response optimization
- ✅ **Real-time & Analytics**
  - ✅ WebSocket API for real-time data streaming
  - ✅ Portfolio tracking and analytics
  - ✅ Performance metrics (Sharpe, Sortino, VaR)
  - ✅ Risk analysis and attribution
  - ✅ User preferences and notification system
- ✅ **Monitoring & Operations**
  - ✅ Comprehensive logging and monitoring
  - ✅ Application metrics collection
  - ✅ Admin tools and system monitoring
  - ✅ Security violation tracking
  - ✅ Query performance analysis
- ✅ **Developer Experience**
  - ✅ API versioning and backward compatibility
  - ✅ Enhanced OpenAPI documentation
  - ✅ Usage examples and migration guides
  - ✅ Interactive documentation interface
  - ✅ One-click startup scripts (autostart.sh, quickstart.sh)
  - ✅ API helper script (api.sh)
  - ✅ Comprehensive Makefile
  - ✅ Development-optimized Docker Compose

### Phase 5 - Autonomous Trading System (Complete)
- ✅ **Position Synchronization**
  - ✅ Automatic sync with Alpaca positions every 30 seconds
  - ✅ Real-time P&L tracking and updates
  - ✅ Support for both stocks and cryptocurrencies
- ✅ **Autonomous Trading Strategies**
  - ✅ Stop Loss Protection (5% default, configurable)
  - ✅ Take Profit Strategy (15% default, configurable)
  - ✅ Momentum Trading (3% threshold, configurable)
  - ✅ Portfolio Rebalancing (10% deviation threshold)
  - ✅ Mean Reversion Framework
- ✅ **Smart Features**
  - ✅ Market hours validation for stocks
  - ✅ Partial position management
  - ✅ Risk-based position sizing (2% per position)
  - ✅ Maximum position limits (20 positions)
  - ✅ Automatic error recovery and reconnection
- ✅ **API Control**
  - ✅ Start/stop autonomous trading
  - ✅ Configure strategies independently
  - ✅ Real-time status monitoring
  - ✅ Force immediate trading cycles

## Trading Symbols

### Configured Stocks (20 symbols)
- **Your Positions**: AMD, AMZN, GOOGL, HD, INTC, JNJ, META, NIO, NVDA, PYPL, SOFI, SPY, T, V
- **Additional**: AAPL, MSFT, TSLA, JPM, AVGO (Broadcom), MU (Micron Technology)

### Configured Cryptocurrencies (10 symbols)
- BTCUSD, ETHUSD, SOLUSD, ADAUSD, XRPUSD, MATICUSD, LINKUSD, DOTUSD, UNIUSD, LTCUSD

## Autonomous Trading System

### Quick Start
```bash
# View autonomous trading status
curl http://localhost:8000/api/v1/autonomous/status

# Start autonomous trading (requires authentication)
curl -X POST http://localhost:8000/api/v1/autonomous/start \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Configure stop loss to 10%
curl -X PATCH http://localhost:8000/api/v1/autonomous/strategy/stop_loss \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"stop_loss_pct": 0.10}'
```

### Autonomous Trading Features
1. **Position Monitoring**: Continuously monitors all positions for trading signals
2. **Stop Loss**: Automatically sells positions down by configured percentage
3. **Take Profit**: Takes profits on positions up by configured percentage
4. **Momentum Trading**: Identifies and trades on significant price movements
5. **Portfolio Rebalancing**: Maintains target allocations across positions
6. **Risk Management**: Position sizing, maximum positions, market hours validation

## TODO/Roadmap

### Phase 6 - Advanced Features (Next)
- [ ] Machine learning price prediction models
- [ ] Sentiment analysis from news/social media
- [ ] Advanced order types (stop-loss, trailing stop)
- [ ] Multi-exchange arbitrage detection
- [ ] Custom technical indicators framework
- [ ] Strategy marketplace

### Phase 7 - Enterprise Features
- [ ] Multi-tenant support
- [ ] Advanced compliance reporting
- [ ] Integration with traditional brokers
- [ ] Custom webhook integrations
- [ ] White-label support

### Infrastructure Enhancements
- [ ] Kubernetes deployment manifests
- [ ] Prometheus/Grafana monitoring stack
- [ ] ElasticSearch for log aggregation
- [ ] CDN integration for global access
- [ ] Disaster recovery and backup automation
- [ ] Multi-region deployment support

## Production Readiness

### Enterprise-Grade Features Completed ✅
- **Security**: Multi-layer authentication, audit trails, rate limiting
- **Performance**: Connection pooling, caching, compression, optimization
- **Scalability**: Redis pub/sub, WebSocket streaming, horizontal scaling ready
- **Monitoring**: Comprehensive metrics, logging, admin dashboards
- **Compliance**: Complete audit trails, security monitoring
- **Developer Experience**: Full API documentation, versioning, examples

### Future Enhancements (Optional)
- Email notification delivery (SMTP integration)
- Advanced charting and technical indicators
- Mobile app API endpoints
- Third-party broker integrations beyond Alpaca
- Machine learning strategy recommendations

## Order Management System (OMS)

### Quick Start
```bash
# Set Alpaca credentials in .env
ALPACA_API_KEY=PKQ5Q0YC4N4ODIX1JLXV
ALPACA_API_SECRET=aBUXxQpzLRQm89IWJgyDUd51kGM0rsB9xM3kHvuq

# Start services
docker compose up --build

# Submit a trade signal
curl -X POST http://localhost:8000/api/v1/trading/signal \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "side": "buy", "qty": 10, "reason": "Test trade"}'

# View orders
curl http://localhost:8000/api/v1/trading/orders | jq

# View positions
curl http://localhost:8000/api/v1/trading/positions | jq
```

### OMS Components
1. **Execution Engine**: Processes signals from Redis, validates risk limits, submits to Alpaca
2. **Position Manager**: Tracks positions, calculates P&L, updates prices from QuestDB
3. **Risk Management**: Configurable limits for position size and order quantities
4. **WebSocket Integration**: Real-time order status updates from Alpaca

See `OMS_README.md` for detailed documentation.

## Trading Strategy Framework

### Quick Start
```bash
# Create a new strategy
curl -X POST http://localhost:8000/api/v1/strategies/create \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "sma_crossover",
    "name": "BTC SMA Strategy",
    "symbols": ["BTCUSDT"],
    "parameters": {"fast_period": 10, "slow_period": 30},
    "allocation": 0.25
  }'

# Run backtest
curl -X POST http://localhost:8000/api/v1/strategies/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "sma_crossover_20241215_120000",
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-12-01T00:00:00"
  }'

# View strategies
curl http://localhost:8000/api/v1/strategies/list | jq
```

### Strategy Components
1. **Base Framework**: Abstract classes for strategy development
2. **Example Strategies**: SMA Crossover and Momentum strategies
3. **Backtesting Engine**: Historical simulation with comprehensive metrics
4. **Risk Manager**: Advanced drawdown, correlation, and VaR controls
5. **Portfolio Manager**: Multi-strategy allocation and rebalancing
6. **Performance Analytics**: Sharpe ratio, drawdown analysis, trade statistics

See `STRATEGY_README.md` for detailed documentation.

## Current Temporary Modifications

### Aggressive Bot Mode (Active)
The system currently has temporary modifications for aggressive autonomous trading:

1. **Modified Files**:
   - `app/main.py` - Auto-starts autonomous trader with aggressive settings
   - `app/api/autonomous.py` - Added internal endpoint without auth
   - `compose.yaml` - Uses temporary entrypoint that skips migrations

2. **Aggressive Settings**:
   - Momentum threshold: 0.1% (ultra-sensitive, down from 3%)
   - Check interval: 15 seconds (down from 60 seconds)
   - Stop loss: 2% (tighter than default 5%)
   - Take profit: 5% (down from 15%)
   - Position size: 3% of portfolio (~$2,200)
   - Max positions: 25

3. **Temporary Activation Scripts**:
   - `ACTIVATE_BOT.py` - Python script to activate bot via HTTP
   - `START_AUTONOMOUS_BOT.sh` - Shell script for bot activation
   - Multiple other activation scripts for various methods

4. **To Restore Normal Operation**:
   ```bash
   # Revert app/main.py to not auto-start bot
   # Remove internal endpoint from app/api/autonomous.py
   # Restore proper entrypoint in compose.yaml
   # Delete temporary activation scripts
   ```

**Note**: These modifications bypass authentication and normal safety checks. They should be removed before production deployment.

## Project Statistics

**Last Updated**: 2025-07-20

### Code Metrics
- **Total Files**: 136
- **Total Lines of Code**: 21,872

### Breakdown by Language
- **Python (.py)**: 19,493 lines (89%)
- **JavaScript (.js)**: 1,214 lines (6%)
- **HTML (.html)**: 647 lines (3%)
- **Shell Scripts (.sh)**: 1,106 lines (5%)
- **YAML (.yaml/.yml)**: 357 lines (2%)

### Key Components
- **API Endpoints**: 18 routers
- **Database Models**: 13 models
- **Services**: 15+ business logic services
- **Trading Strategies**: 7 autonomous strategies
- **Middleware**: 4 middleware components
- **Background Tasks**: 5 async workers

### Recent Additions
- Performance tracking system (1,404 lines)
- Web dashboard (1,412 lines)
- Trailing stop losses (323 lines)
- Daily limits and safety features (285 lines)