# 🚀 Trademk1 Trading Bot Startup Guide

## Prerequisites

### 1. Alpaca Paper Trading Account (Required)
1. Go to [https://alpaca.markets/](https://alpaca.markets/)
2. Sign up for a **free paper trading account**
3. Go to **API Keys** section in your dashboard
4. Generate new API keys (save these securely!)

### 2. System Requirements
- Docker and Docker Compose installed
- At least 4GB RAM available
- Stable internet connection

## Quick Start (5 Minutes)

### Step 1: Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your Alpaca credentials
nano .env
```

**Required .env settings:**
```bash
# Application
APP_NAME=Trademk1
DEBUG=True
ENVIRONMENT=development
SECRET_KEY=your-secret-key-change-this-to-something-secure

# Alpaca Paper Trading (REQUIRED)
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_API_SECRET=your_alpaca_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_KEY_ID=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here

# Leave other settings as default for development
```

### Step 2: Start the Platform
```bash
# Start all services (this will take 2-3 minutes first time)
docker compose up --build

# Or run in background
docker compose up --build -d
```

### Step 3: Verify Everything is Running
Open these URLs in your browser:
- **API Documentation**: http://localhost:8000/api/docs/
- **Health Check**: http://localhost:8000/api/health/detailed
- **QuestDB Console**: http://localhost:9000

### Step 4: Create Your First User Account
```bash
# Register a new user
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "password": "SecurePassword123!",
    "full_name": "Trading Bot User"
  }'
```

### Step 5: Get Your Authentication Token
```bash
# Login to get JWT token
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader@example.com",
    "password": "SecurePassword123!"
  }'
```

**Save the `access_token` from the response - you'll need it for all API calls!**

## Trading Bot Operation

### Option A: Manual Trading Signals

**Submit a buy signal:**
```bash
# Replace YOUR_JWT_TOKEN with the token from login
curl -X POST "http://localhost:8000/api/v1/trading/signal" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL", 
    "side": "buy", 
    "qty": 1, 
    "reason": "Manual buy signal"
  }'
```

**Check your orders:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/trading/orders"
```

**View your positions:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/trading/positions"
```

### Option B: Automated Strategy Trading

**1. Create a trading strategy:**
```bash
curl -X POST "http://localhost:8000/api/v1/strategies/create" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "sma_crossover",
    "name": "AAPL SMA Strategy",
    "symbols": ["AAPL"],
    "parameters": {
      "fast_period": 10,
      "slow_period": 30,
      "position_size": 0.1
    },
    "allocation": 0.25,
    "enabled": true
  }'
```

**2. Start the strategy:**
```bash
# Get strategy ID from the create response, then:
curl -X POST "http://localhost:8000/api/v1/strategies/start/your_strategy_id" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**3. Monitor strategy performance:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/strategies/list"
```

### Option C: Portfolio Analytics

**Get portfolio summary:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/portfolio/summary"
```

**Get detailed analytics:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/portfolio/performance?period_days=30"
```

## Real-Time Monitoring

### WebSocket Connection (Live Updates)
```javascript
// Connect to real-time stream
const ws = new WebSocket('ws://localhost:8000/ws/stream?token=YOUR_JWT_TOKEN');

// Subscribe to order updates
ws.send(JSON.stringify({
  "type": "subscribe",
  "channel": "orders"
}));

// Subscribe to market data
ws.send(JSON.stringify({
  "type": "subscribe", 
  "channel": "market:AAPL"
}));
```

### Monitoring Dashboard
Access the admin monitoring dashboard (requires superuser):
```bash
# First, make your user a superuser
# Connect to the database and update the user table
# Or use the admin API endpoints at:
# http://localhost:8000/api/v1/admin/health
```

## Common Operations

### Check System Health
```bash
curl "http://localhost:8000/api/v1/admin/health"
```

### View Market Data
```bash
# Get latest price for AAPL
curl "http://localhost:8000/api/v1/market-data/latest/AAPL"

# Get recent Bitcoin price  
curl "http://localhost:8000/api/v1/market-data/latest/BTCUSDT"

# List all available symbols
curl "http://localhost:8000/api/v1/market-data/symbols"
```

### Manage Notifications
```bash
# Get notifications
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v1/preferences/notifications"

# Send test notification
curl -X POST "http://localhost:8000/api/v1/preferences/notifications/test" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Safety Features

### Paper Trading Only
- All trades execute on Alpaca's paper trading environment
- No real money is involved
- Perfect for testing and learning

### Risk Management
- Position size limits automatically enforced
- Market hours validation
- Order size restrictions
- Real-time P&L tracking

### Security Features
- Rate limiting (60 requests/minute by default)
- IP-based security filtering
- Complete audit logging
- Secure JWT authentication

## Troubleshooting

### Common Issues

**1. "Database not initialized" error:**
```bash
# Restart services
docker compose down
docker compose up --build
```

**2. "Alpaca authentication failed":**
- Verify your API keys in `.env` file
- Ensure you're using paper trading keys
- Check Alpaca account is active

**3. "WebSocket connection failed":**
- Check if all services are running
- Verify JWT token is valid
- Ensure Redis is connected

**4. Check logs:**
```bash
# View application logs
docker compose logs app

# View specific service logs
docker compose logs db
docker compose logs redis
```

### Support Commands
```bash
# Restart specific service
docker compose restart app

# View system resource usage
docker stats

# Clean up and restart everything
docker compose down
docker system prune -f
docker compose up --build
```

## Next Steps

1. **Start with manual signals** to understand the system
2. **Create simple strategies** using the SMA crossover example
3. **Monitor performance** using the portfolio analytics
4. **Set up notifications** for important events
5. **Scale up** by creating multiple strategies

## Important Notes

⚠️  **This is PAPER TRADING only** - no real money is involved
🔒  **Keep your API keys secure** - never commit them to version control
📊  **Monitor your strategies** - automated trading requires oversight
🔄  **Start small** - begin with small position sizes and simple strategies

Your trading bot is now ready to start! 🚀