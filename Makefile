# Trademk1 Makefile - Simplified project management

.PHONY: help start stop restart logs clean test setup dev prod shell db-shell redis-cli status backup

# Default target
help:
	@echo "Trademk1 Project Commands"
	@echo "========================"
	@echo "Quick Start:"
	@echo "  make setup     - First-time setup (interactive)"
	@echo "  make start     - Start all services"
	@echo "  make stop      - Stop all services"
	@echo ""
	@echo "Development:"
	@echo "  make dev       - Start in development mode (with auto-reload)"
	@echo "  make logs      - Follow application logs"
	@echo "  make shell     - Open shell in app container"
	@echo "  make test      - Run test suite"
	@echo ""
	@echo "Database:"
	@echo "  make db-shell  - Connect to PostgreSQL"
	@echo "  make redis-cli - Connect to Redis"
	@echo "  make migrate   - Run database migrations"
	@echo ""
	@echo "Management:"
	@echo "  make status    - Show service status"
	@echo "  make clean     - Clean up containers and volumes"
	@echo "  make backup    - Backup databases"
	@echo ""
	@echo "Trading:"
	@echo "  make positions - Show current positions"
	@echo "  make orders    - Show recent orders"
	@echo "  make portfolio - Show portfolio summary"

# First-time setup
setup:
	@echo "🚀 Running first-time setup..."
	@./autostart.sh

# Start services
start:
	@echo "🚀 Starting Trademk1..."
	@docker compose up -d
	@echo "✅ Services started. Waiting for health checks..."
	@sleep 5
	@make status

# Start in development mode
dev:
	@echo "🚀 Starting in development mode..."
	@docker compose -f compose.yaml -f docker-compose-dev.yaml up

# Stop services
stop:
	@echo "🛑 Stopping services..."
	@docker compose down

# Restart services
restart: stop start

# View logs
logs:
	@docker compose logs -f app

# Run tests
test:
	@echo "🧪 Running tests..."
	@docker compose exec app pytest tests/ -v

# Shell access
shell:
	@docker compose exec app /bin/bash

# Database shell
db-shell:
	@docker compose exec db psql -U postgres -d trademk1

# Redis CLI
redis-cli:
	@docker compose exec redis redis-cli

# Run migrations
migrate:
	@echo "📦 Running database migrations..."
	@docker compose exec app alembic upgrade head

# Show status
status:
	@echo "📊 Service Status:"
	@echo "=================="
	@docker compose ps
	@echo ""
	@echo "🏥 Health Checks:"
	@curl -s http://localhost:8000/api/health/detailed | jq . || echo "API not responding"

# Clean everything
clean:
	@echo "🧹 Cleaning up..."
	@docker compose down -v
	@rm -f .credentials
	@echo "✅ Cleanup complete"

# Backup databases
backup:
	@echo "💾 Creating backup..."
	@mkdir -p backups
	@docker compose exec db pg_dump -U postgres trademk1 > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql
	@docker compose exec redis redis-cli BGSAVE
	@echo "✅ Backup created in backups/"

# Trading shortcuts (requires .credentials file)
positions:
	@./api.sh positions

orders:
	@./api.sh orders

portfolio:
	@./api.sh portfolio

strategies:
	@./api.sh strategies

# Development database reset
db-reset:
	@echo "⚠️  Resetting database..."
	@docker compose down -v
	@docker compose up -d db
	@sleep 5
	@docker compose up -d
	@sleep 5
	@make migrate
	@echo "✅ Database reset complete"

# Production deployment (example)
deploy:
	@echo "📦 Building for production..."
	@docker compose -f compose.yaml build
	@echo "✅ Build complete. Ready for deployment."

# Quick health check
health:
	@curl -s http://localhost:8000/api/health/detailed | jq .

# Monitor market data ingestion
monitor:
	@watch -n 2 "curl -s http://localhost:8000/api/v1/market-data/stream_status | jq ."