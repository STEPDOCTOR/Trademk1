#!/bin/bash

# Ultra-quick start with zero configuration
# This script uses default paper trading mode without requiring Alpaca keys

echo "🚀 Trademk1 Quick Start (Demo Mode)"
echo "==================================="

# Create minimal .env if not exists
if [ ! -f .env ]; then
    cat > .env << EOF
# Minimal configuration for demo mode
APP_NAME=Trademk1
DEBUG=True
ENVIRONMENT=development
SECRET_KEY=demo-secret-key-change-in-production
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/trademk1
QUESTDB_URL=postgresql://admin:quest@questdb:8812/qdb
REDIS_URL=redis://redis:6379
CORS_ORIGINS=["http://localhost:3000"]
BINANCE_API_URL=wss://stream.binance.com:9443

# Alpaca - Leave empty for demo mode
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_KEY_ID=
ALPACA_SECRET_KEY=
EOF
fi

# Start services
echo "Starting services..."
docker compose up -d --build

# Wait for services
echo "Waiting for services to be ready..."
sleep 30

# Create demo user automatically
echo "Creating demo user account..."
curl -s -X POST "http://localhost:8000/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d '{
        "email": "demo@trademk1.local",
        "password": "DemoUser123!",
        "full_name": "Demo User"
    }' > /dev/null 2>&1

# Get token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "demo@trademk1.local",
        "password": "DemoUser123!"
    }' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

# Save quick access info
cat > DEMO_ACCESS.txt << EOF
🎯 TRADEMK1 DEMO ACCESS
======================

📧 Email: demo@trademk1.local
🔑 Password: DemoUser123!
🎫 Token: $TOKEN

🌐 Web Interfaces:
- API Docs: http://localhost:8000/api/docs/
- Health Check: http://localhost:8000/api/health/detailed
- QuestDB Console: http://localhost:9000

📝 Quick Commands:
# Check Bitcoin price
curl http://localhost:8000/api/v1/market-data/latest/BTCUSDT | jq

# View all symbols
curl http://localhost:8000/api/v1/market-data/symbols | jq

# Check your portfolio (requires token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/portfolio/summary | jq

🛑 Stop Demo:
docker compose down

EOF

clear
cat DEMO_ACCESS.txt

echo ""
echo "✅ Demo is running! Check DEMO_ACCESS.txt for credentials."
echo ""
echo "Try this command to see Bitcoin price:"
echo "curl http://localhost:8000/api/v1/market-data/latest/BTCUSDT | jq"