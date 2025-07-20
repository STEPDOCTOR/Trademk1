# Aggressive Trading Mode Documentation

## Overview

The aggressive trading mode is a high-frequency, ultra-sensitive configuration of the autonomous trading system designed to capture small price movements with frequent trades.

## Current Configuration

### Trading Parameters
- **Momentum Threshold**: 0.1% (down from default 3%)
- **Check Interval**: 15 seconds (down from 60 seconds)
- **Stop Loss**: 2% (tighter than default 5%)
- **Take Profit**: 5% (down from default 15%)
- **Position Size**: 3% of portfolio (~$2,200 per position)
- **Max Positions**: 25
- **Lookback Period**: 1 hour (for momentum calculation)

### Auto-Start Behavior
The system currently auto-starts the aggressive trading mode when Docker containers launch. This is implemented through:
1. Modified `app/main.py` that configures and starts the autonomous trader
2. Internal API endpoint at `/api/v1/autonomous/internal/start` (no auth required)
3. Multiple activation scripts for manual control

## Activation Methods

### Method 1: Automatic (Current Default)
```bash
docker compose up
# Bot starts automatically with aggressive settings
```

### Method 2: Python Script
```bash
python3 ACTIVATE_BOT.py
```

### Method 3: Shell Scripts
```bash
./START_AUTONOMOUS_BOT.sh
# or
./ACTIVATE_AGGRESSIVE_BOT.sh
# or
./START_THE_BOT.sh
```

### Method 4: Direct API Call
```bash
curl -X POST http://localhost:8000/api/v1/autonomous/internal/start
```

## Monitoring

### Check Status
```bash
# API status endpoint
curl http://localhost:8000/api/v1/autonomous/status | jq

# View logs
docker compose logs -f app | grep -i "autonomous"

# Watch position syncs
docker compose logs -f app | grep "Synced.*positions"

# Monitor trades
docker compose logs -f app | grep -E "(BUY|SELL|signal)"
```

### Key Log Messages
- `"Autonomous trader started with aggressive settings!"` - Bot activated
- `"Checking for trading opportunities..."` - Regular cycle running
- `"Synced X positions from Alpaca"` - Position sync completed
- `"Generated BUY/SELL signal"` - Trade signal created
- `"Momentum detected"` - Price movement threshold exceeded

## Trading Behavior

### Entry Conditions
1. **Momentum Buy**: Price increases by 0.1% or more in the last hour
2. **Position Sizing**: 3% of total portfolio value
3. **Max Positions**: Won't exceed 25 concurrent positions

### Exit Conditions
1. **Stop Loss**: Automatic sell if position drops 2%
2. **Take Profit**: Automatic sell if position gains 5%
3. **Momentum Reversal**: May sell on negative momentum

### Risk Management
- Position size limited to 3% of portfolio
- Maximum 25 concurrent positions
- Total portfolio exposure capped at 75%
- Market hours validation for stocks (crypto trades 24/7)

## Performance Expectations

### Advantages
- Captures small price movements quickly
- High trade frequency can compound gains
- Tight stop loss limits downside risk
- Diversification across many positions

### Risks
- High sensitivity may trigger on noise
- Frequent trading increases transaction costs
- Tight stops may exit positions prematurely
- Requires constant monitoring

## Reverting to Normal Mode

### Step 1: Stop the Bot
```bash
docker compose down
```

### Step 2: Revert Code Changes
```bash
# Restore original main.py (remove auto-start code)
git checkout app/main.py

# Remove internal endpoint from autonomous.py
git checkout app/api/autonomous.py

# Restore original compose.yaml
git checkout compose.yaml
```

### Step 3: Delete Temporary Files
```bash
rm ACTIVATE_*.py ACTIVATE_*.sh
rm START_*.sh MAKE_*.sh MONITOR_*.sh
rm ENABLE_*.py FINAL_*.py BOT_*.sh
rm manage.py start_*.py adjust_*.py
rm docker/entrypoint-temp.sh
```

### Step 4: Restart with Normal Settings
```bash
docker compose up --build
```

## Configuration Adjustments

To modify the aggressive settings, edit the configuration in `app/main.py`:

```python
# Momentum settings
autonomous_trader.update_strategy('momentum',
    enabled=True,
    momentum_threshold=0.001,      # Adjust sensitivity (0.001 = 0.1%)
    momentum_lookback_hours=1,     # Lookback period
    position_size_pct=0.03,        # Position size (0.03 = 3%)
    max_positions=25               # Maximum positions
)

# Risk management
autonomous_trader.update_strategy('stop_loss',
    enabled=True,
    stop_loss_pct=0.02  # Stop loss (0.02 = 2%)
)

autonomous_trader.update_strategy('take_profit',
    enabled=True,
    take_profit_pct=0.05  # Take profit (0.05 = 5%)
)

# Check frequency
autonomous_trader.check_interval = 15  # Seconds between checks
```

## Safety Considerations

1. **Paper Trading Only**: Ensure Alpaca account is in paper mode
2. **Monitor Closely**: Watch for excessive trading or losses
3. **Set Limits**: Consider daily loss limits
4. **Test First**: Run for short periods before extended use
5. **Have Kill Switch**: Know how to stop the bot quickly

## Troubleshooting

### Bot Not Starting
```bash
# Check health
curl http://localhost:8000/api/health

# Check logs
docker compose logs app | tail -50

# Restart services
docker compose restart app
```

### Too Many Trades
- Increase momentum threshold (e.g., to 0.002 for 0.2%)
- Increase check interval (e.g., to 30 seconds)
- Reduce max positions

### Not Enough Trades
- Decrease momentum threshold (but be careful of noise)
- Add more symbols to watch list
- Check market hours for stocks

## Important Notes

⚠️ **WARNING**: This mode is experimental and bypasses normal safety checks:
- No authentication required for internal endpoint
- Very sensitive to price movements
- High trading frequency
- Should not be used in production
- Always use with paper trading account