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
│   └── health.py     # Health check endpoints with DB status
├── config/           # Configuration
│   └── settings.py   # Pydantic settings from .env
├── db/               # Database layer
│   └── postgres.py   # Async PostgreSQL session management
├── models/           # SQLAlchemy models
│   ├── base.py       # Base model with id, created_at, updated_at
│   ├── user.py       # User model for authentication
│   ├── symbol.py     # Symbol model for trading assets
│   └── config.py     # Config model for app settings
└── main.py           # FastAPI app factory with lifespan

/alembic
├── versions/         # Database migrations
│   └── 0001_initial.py # Initial schema with triggers
└── env.py            # Async migration configuration

/docker
├── app.dockerfile    # FastAPI container definition
├── entrypoint.sh     # Startup script with migrations
└── wait-for-it.sh    # Database readiness check

/tests
├── test_health.py    # Health endpoint tests
└── test_db_models.py # Database CRUD tests
```

## Database Schema

### Base Model
All models inherit:
- `id`: UUID primary key
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone (auto-updated via trigger)

### Models
- **User**: email, password_hash, is_active, is_superuser
- **Symbol**: ticker, name, exchange, asset_type, is_active, metadata_json
- **Config**: key, value, scope, description

## Testing

```bash
# Run all tests
source .venv/bin/activate
pytest tests/

# Run specific test file
pytest tests/test_db_models.py -v

# Run with coverage
pytest tests/ --cov=app
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

- `GET /` - Root endpoint
- `GET /api/health` - Basic health check
- `GET /api/health/detailed` - Detailed health with PostgreSQL status

## Environment Variables

Configure in `.env` file (see `.env.example`):
- `APP_NAME` - Application name
- `DEBUG` - Debug mode
- `ENVIRONMENT` - Environment (development/production)
- `DATABASE_URL` - PostgreSQL connection (use asyncpg format)
- `REDIS_URL` - Redis connection
- `SECRET_KEY` - Secret key for security
- `CORS_ORIGINS` - Allowed CORS origins

## Docker Compose Configuration

- Uses `compose.yaml` (modern format)
- Watch mode configured for `app/`, `tests/`, and `alembic/`
- PostgreSQL 15 and Redis 7 services included
- Automatic health checks and migrations

## Completed Features

- ✅ FastAPI backend with async support
- ✅ PostgreSQL integration with asyncpg
- ✅ Alembic migrations with auto-update triggers
- ✅ Health endpoints with database status
- ✅ Docker Compose with hot-reload
- ✅ Comprehensive test setup
- ✅ Environment-based configuration

## TODO/Roadmap

- [ ] Implement Redis health checks
- [ ] Add uptime tracking
- [ ] User authentication (JWT)
- [ ] Trading API endpoints
- [ ] WebSocket support for real-time data
- [ ] QuestDB integration for time-series data
- [ ] Trading strategies implementation
- [ ] Admin dashboard
- [ ] API rate limiting
- [ ] Monitoring and alerting