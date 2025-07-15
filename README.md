# Trademk1

An autonomous real-time trading platform for U.S. stocks and top-15 cryptocurrencies.

## 🚀 Quick Start (30 seconds)

```bash
# Option 1: Zero-config demo mode
./quickstart.sh

# Option 2: Interactive setup with Alpaca integration
./autostart.sh

# Option 3: Use Make commands
make setup  # First time only
make start  # Start services
```

## Features

### Core Trading
- ✅ Real-time market data ingestion from multiple sources
- ✅ Support for U.S. stocks (via Alpaca) and cryptocurrencies (via Binance)
- ✅ Paper trading with Alpaca integration
- ✅ Order Management System (OMS)
- ✅ Position tracking with real-time P&L
- ✅ Multi-strategy portfolio management
- ✅ Backtesting engine
- ✅ Advanced risk management

### Infrastructure
- ✅ PostgreSQL for application data
- ✅ QuestDB for high-performance time-series storage
- ✅ Redis for caching and pub/sub
- ✅ WebSocket API for real-time updates
- ✅ JWT authentication with refresh tokens
- ✅ API key management
- ✅ Rate limiting and DDoS protection
- ✅ Comprehensive monitoring and logging

### User Experience
- ✅ Interactive API documentation
- ✅ Portfolio analytics and performance metrics
- ✅ User preferences and notifications
- ✅ Audit logging for compliance
- ✅ API versioning
- ✅ One-click startup scripts

## 📋 Prerequisites

- Docker and Docker Compose
- (Optional) Free Alpaca paper trading account from [alpaca.markets](https://alpaca.markets/)

## 🛠️ Installation Options

### Option 1: Quick Demo (No API Keys Required)
```bash
git clone https://github.com/STEPDOCTOR/Trademk1.git
cd Trademk1
./quickstart.sh
```

### Option 2: Full Setup with Trading
```bash
git clone https://github.com/STEPDOCTOR/Trademk1.git
cd Trademk1
./autostart.sh  # Interactive setup
```

### Option 3: Using Make
```bash
git clone https://github.com/STEPDOCTOR/Trademk1.git
cd Trademk1
make setup      # First-time setup
make start      # Start services
make status     # Check health
```

## 🎯 Quick Usage

```bash
# After setup, use the API helper:
./api.sh positions   # View positions
./api.sh buy AAPL 10 # Buy 10 shares of AAPL
./api.sh portfolio   # View portfolio

# Or use Make commands:
make positions
make portfolio
make logs
```

## 📚 Documentation

- **API Docs**: http://localhost:8000/api/docs/
- **Detailed Guide**: See [STARTUP_GUIDE.md](STARTUP_GUIDE.md)
- **Strategy Development**: See [STRATEGY_README.md](STRATEGY_README.md)
- **Order Management**: See [OMS_README.md](OMS_README.md)

## 🔧 Common Operations

### Service Management
```bash
make start      # Start all services
make stop       # Stop all services
make restart    # Restart services
make logs       # View logs
make status     # Check health
```

### Development
```bash
make dev        # Start with auto-reload
make test       # Run tests
make shell      # App container shell
make db-shell   # PostgreSQL shell
make redis-cli  # Redis CLI
```

### Trading
```bash
# Using api.sh helper
./api.sh buy AAPL 10      # Buy stock
./api.sh sell BTCUSDT 0.1 # Sell crypto
./api.sh positions        # View positions
./api.sh strategies       # List strategies

# Using Make
make positions
make portfolio
make orders
```

## 🏗️ Architecture

### Services
- **FastAPI**: Async web framework with WebSocket support
- **PostgreSQL**: Primary database for application data
- **QuestDB**: Time-series database for market data (ILP protocol)
- **Redis**: Caching, pub/sub, and rate limiting
- **Docker Compose**: Container orchestration with health checks

### Key Components
- **Market Data Ingestion**: Real-time WebSocket clients for Binance and Alpaca
- **Order Management System**: Paper trading execution via Alpaca
- **Strategy Framework**: Pluggable strategies with backtesting
- **Risk Management**: Position limits, drawdown protection, correlation analysis
- **Authentication**: JWT tokens with refresh, API keys, RBAC
- **Monitoring**: Comprehensive logging, metrics, and health checks

## 🛡️ Security & Compliance

- Paper trading only (no real money)
- JWT authentication with secure refresh tokens
- API rate limiting and DDoS protection
- Comprehensive audit logging
- Encrypted password storage (bcrypt)
- IP-based security filtering

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

[MIT License](LICENSE)

## ⚠️ Disclaimer

This software is for educational and paper trading purposes only. Always test thoroughly before considering any real trading applications.