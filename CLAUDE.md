# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trademk1 - A FastAPI-based trading application with Docker infrastructure.

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
# Start all services
docker compose up --build

# Start with file watch (recommended for development)
docker compose watch
```

## Project Structure

```
/app
├── api/          # API endpoints
│   └── health.py # Health check endpoints
├── config/       # Configuration
│   └── settings.py # Pydantic settings from .env
└── main.py       # FastAPI app factory

/docker
└── app.dockerfile # FastAPI container definition

/tests
└── test_health.py # Pytest tests with httpx
```

## Testing

```bash
# Run tests locally
source .venv/bin/activate
pytest tests/

# Run with coverage
pytest tests/ --cov=app
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
- `GET /api/health/detailed` - Detailed health with service statuses

## Environment Variables

Configure in `.env` file:
- `APP_NAME` - Application name
- `DEBUG` - Debug mode
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `SECRET_KEY` - Secret key for security

## TODO/Roadmap

- [ ] Implement actual database health checks
- [ ] Implement actual Redis health checks
- [ ] Add uptime tracking
- [ ] Add user authentication
- [ ] Add trading endpoints
- [ ] Add WebSocket support for real-time data