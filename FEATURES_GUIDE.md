# Trademk1 Trading Bot - Complete Features Guide

## 🚀 Quick Start

### One-Click Activation
```bash
# Activate features with simple menu
./ACTIVATE_FEATURES.py

# Or use the comprehensive control panel
./control_panel.py
```

## 📊 Available Features

### 1. **Autonomous Trading System**
- **Stop Loss Protection**: Automatically sells losing positions
- **Take Profit**: Captures gains at target levels
- **Momentum Trading**: Trades based on price momentum
- **Portfolio Rebalancing**: Maintains target allocations
- **Mean Reversion**: Trades on statistical extremes
- **Trailing Stops**: Protects profits with dynamic stops

### 2. **Machine Learning Predictions** 🧠
- Random Forest models for price prediction
- Continuous model training and updates
- Feature engineering with technical indicators
- Confidence scoring for signals
- Multi-timeframe predictions (5, 15, 30, 60 minutes)

### 3. **Multi-Exchange Trading** 🌐
- **Supported Exchanges**:
  - Alpaca (US Stocks)
  - Binance (Cryptocurrencies)
  - Coinbase (Cryptocurrencies)
  - Kraken (Cryptocurrencies)
- **Arbitrage Detection**: Finds price differences across exchanges
- **Best Execution**: Routes orders to best price

### 4. **Advanced Trading Strategies**

#### **Options Trading** 📈
- Covered Calls
- Cash-Secured Puts
- Vertical Spreads
- Iron Condors
- Greeks calculations (Delta, Gamma, Theta, Vega, Rho)

#### **Pairs Trading** 📊
- Statistical arbitrage
- Cointegration testing
- Mean reversion timing
- Hedge ratio calculations

#### **Market Making** 💹
- Automated liquidity provision
- Dynamic spread adjustment
- Inventory management
- Microprice calculations

#### **Futures Trading** 🔮
- Calendar spread trading
- Roll optimization
- Basis trading
- Margin management

#### **News-Based Trading** 📰
- Sentiment analysis
- Breaking news detection
- Multi-source aggregation
- Relevance scoring

### 5. **Risk Management**
- Position sizing algorithms
- Portfolio risk metrics
- Correlation analysis
- Maximum drawdown protection
- Daily loss limits

### 6. **Performance Analytics**
- Real-time P&L tracking
- Win rate calculation
- Sharpe ratio
- Maximum drawdown
- Trade journal
- Performance attribution

### 7. **Technical Analysis**
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- Moving Averages (SMA, EMA)
- Volume indicators
- Support/Resistance levels

### 8. **Market Sentiment Analysis**
- News sentiment aggregation
- Social media sentiment (coming soon)
- Fear & Greed indicators
- Market breadth analysis

## 🎮 Control Methods

### 1. **Control Panel** (`./control_panel.py`)
Interactive menu-driven interface with:
- Autonomous trading control
- Strategy configuration
- Exchange management
- ML model management
- Performance viewing
- Real-time monitoring

### 2. **Quick Activation** (`./ACTIVATE_FEATURES.py`)
One-click activation for:
- Aggressive trading mode
- Machine learning
- Multi-exchange setup
- All features at once

### 3. **Discord Bot Control** 🎮
Control your bot from Discord with buttons:
- Start/stop trading with one click
- Switch between aggressive/conservative modes
- Enable/disable features instantly
- View positions and performance
- No terminal needed!

### 4. **Telegram Bot Control** 💬
Full control via Telegram chat:
- Push-button interface
- Real-time status updates
- Position monitoring
- Performance tracking
- Mobile-friendly control

### 5. **API Endpoints**
Full REST API for programmatic control:
- `/api/v1/autonomous/` - Autonomous trading
- `/api/v1/ml/` - Machine learning
- `/api/v1/exchanges/` - Exchange management
- `/api/v1/strategies/` - Strategy control
- `/api/v1/trading/` - Order management

### 6. **Web Dashboard**
Access at `http://localhost:8000/dashboard` for:
- Real-time position monitoring
- Performance charts
- Trade history
- System status

## 🔧 Configuration

### Environment Variables (`.env`)
```bash
# Alpaca (Required)
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret

# Optional Exchanges
COINBASE_API_KEY=your_key
COINBASE_API_SECRET=your_secret
KRAKEN_API_KEY=your_key
KRAKEN_API_SECRET=your_secret

# Autonomous Trading
AUTONOMOUS_AUTO_START=True  # Auto-start on boot
MOMENTUM_THRESHOLD=0.03     # 3% default
STOP_LOSS_PCT=0.05         # 5% default
TAKE_PROFIT_PCT=0.15       # 15% default

# Notifications (Optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 📱 Notification Options
- Email alerts
- Telegram messages
- Discord webhooks
- WebSocket real-time updates
- SMS (via Twilio - coming soon)

## 🔐 Security Features
- JWT authentication
- API key management
- Rate limiting
- IP whitelisting
- Audit logging
- Encrypted credentials

## 📈 Coming Soon
- Voice command interface
- Mobile app
- Social trading features
- Copy trading
- Strategy marketplace
- Advanced backtesting UI
- Tax reporting
- Institutional features

## 🆘 Troubleshooting

### Bot not starting?
```bash
# Check logs
docker compose logs -f app

# Restart services
docker compose restart

# Reset database
docker compose down -v
docker compose up --build
```

### No trades being made?
1. Check account balance
2. Verify API keys
3. Check strategy settings
4. Review position limits
5. Check market hours

### ML not working?
1. Train models first: `./ENABLE_ML_TRADING.py`
2. Check data availability (needs 30+ days)
3. Verify memory allocation

## 📞 Support
- GitHub Issues: https://github.com/STEPDOCTOR/Trademk1
- Documentation: `/api/docs`
- Logs: `docker compose logs`

## ⚡ Performance Tips
1. Start with conservative settings
2. Use paper trading first
3. Monitor performance daily
4. Adjust position sizes gradually
5. Enable features one at a time
6. Keep ML models updated
7. Use stop losses always

## 🎯 Quick Commands

```bash
# Start everything
docker compose up -d
./ACTIVATE_FEATURES.py  # Choose option 6

# Start remote control (Discord/Telegram)
./start_remote_control.py

# Monitor
docker compose logs -f app
./control_panel.py  # Choose option 7

# Stop
./control_panel.py  # Stop autonomous trading
docker compose down
```

## 🤖 Remote Control Setup

### Quick Setup
1. Create Discord/Telegram bot (see REMOTE_CONTROL_SETUP.md)
2. Add tokens to `.env`:
   ```bash
   DISCORD_BOT_TOKEN=your_token
   TELEGRAM_BOT_TOKEN=your_token
   ```
3. Start remote control:
   ```bash
   ./start_remote_control.py
   ```
4. Control your bot from anywhere!

Enjoy automated trading with Trademk1! 🚀