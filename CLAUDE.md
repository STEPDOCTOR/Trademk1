# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trademk1 - An autonomous real-time trading platform for U.S. stocks and top-15 cryptocurrencies, built with FastAPI, PostgreSQL, and Docker.

## Development Setup

### Virtual Environment
The project uses a Python virtual environment located at `.venv/`. Always ensure the virtual environment is activated before running any Python commands:
```bash
source .venv/bin/activate
```

### Python Version
This project uses Python 3.12.

### Docker Setup
The application runs in Docker with PostgreSQL and Redis:
```bash
# Start all services (migrations run automatically)
docker compose up --build

# Start with file watch (recommended for development)
docker compose watch

# Stop all services
docker compose down
```

## Project Structure

```
/app
├── api/              # API endpoints
│   ├── health.py     # Health check endpoints with DB status
│   └── market_data.py # Market data query endpoints
├── config/           # Configuration
│   └── settings.py   # Pydantic settings from .env
├── db/               # Database layer
│   ├── postgres.py   # Async PostgreSQL session management
│   └── questdb.py    # QuestDB connection and tables
├── models/           # SQLAlchemy models
│   ├── base.py       # Base model with id, created_at, updated_at
│   ├── user.py       # User model for authentication
│   ├── symbol.py     # Symbol model for trading assets
│   ├── config.py     # Config model for app settings
│   ├── order.py      # Order model for trade execution
│   └── position.py   # Position model for portfolio tracking
├── services/         # Business logic services
│   ├── ingestor/     # Market data ingestion
│   │   ├── models.py         # Tick dataclass and constants
│   │   ├── binance_client.py # Binance WebSocket client
│   │   ├── alpaca_client.py  # Alpaca streaming client
│   │   └── ingest_worker.py  # Batch processing worker
│   └── trading/      # Order management system
│       ├── alpaca_client.py  # Alpaca paper trading wrapper
│       ├── execution_engine.py # Trade signal processor
│       └── position_manager.py # Position & P&L tracker
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
- **User**: email, password_hash, is_active, is_superuser
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

## API Endpoints

### Health
- `GET /` - Root endpoint
- `GET /api/health` - Basic health check
- `GET /api/health/detailed` - Detailed health with PostgreSQL status

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

### Phase 3 - Order Management System (Milestone 1)
- ✅ Order management system with Alpaca integration
- ✅ Position tracking and P&L calculation
- ✅ Risk management rules (position limits, order size)
- ✅ Redis-based signal processing
- ✅ Real-time order status updates via WebSocket
- ✅ Trading API endpoints
- ✅ Comprehensive OMS tests
- ✅ Market hours validation

## TODO/Roadmap

### Phase 3 - Trading Engine (Remaining)
- [ ] Trading strategies framework
- [ ] Strategy backtesting engine
- [ ] Advanced risk management (drawdown, correlation)
- [ ] Multi-strategy portfolio management

### Phase 4 - User Management
- [ ] User authentication (JWT)
- [ ] Role-based access control
- [ ] API key management
- [ ] User portfolio tracking

### Phase 5 - Real-time Features
- [ ] WebSocket API for live data streaming
- [ ] Real-time position updates
- [ ] Price alerts system
- [ ] Live strategy performance metrics

### Infrastructure Improvements
- [ ] Redis health checks and caching layer
- [ ] API rate limiting
- [ ] Monitoring and alerting (Prometheus/Grafana)
- [ ] Admin dashboard
- [ ] Horizontal scaling support

## Order Management System (OMS)

### Quick Start
```bash
# Set Alpaca credentials in .env
ALPACA_API_KEY=your_paper_api_key
ALPACA_API_SECRET=your_paper_api_secret

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