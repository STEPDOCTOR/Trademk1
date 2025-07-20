# Guide to Revert Aggressive Trading Mode

This guide explains how to revert the temporary aggressive trading mode changes and restore the system to its normal, production-ready state.

## Overview of Temporary Changes

The aggressive mode made the following modifications:
1. Auto-start autonomous trader in `app/main.py`
2. Added internal endpoint without auth in `app/api/autonomous.py`
3. Modified Docker entrypoint to skip migrations
4. Created multiple activation scripts

## Step-by-Step Reversion Process

### Step 1: Stop All Services
```bash
# Stop Docker containers
docker compose down

# Make sure no processes are running
docker ps
```

### Step 2: Revert Code Changes

#### Option A: Using Git (Recommended)
```bash
# Check which files were modified
git status

# Revert the three main files
git checkout app/main.py
git checkout app/api/autonomous.py
git checkout compose.yaml

# Verify changes are reverted
git diff
```

#### Option B: Manual Reversion

If you can't use git checkout, manually edit the files:

**1. app/main.py** - Remove the aggressive configuration block:
```python
# DELETE THIS ENTIRE BLOCK:
        # Configure aggressive settings for immediate trading
        logger.info("Configuring aggressive autonomous trading settings...")
        
        # Ultra-aggressive momentum settings
        autonomous_trader.update_strategy('momentum',
            enabled=True,
            momentum_threshold=0.001,      # 0.1% - extremely sensitive
            momentum_lookback_hours=1,     # Just look at last hour
            position_size_pct=0.03,        # 3% of portfolio (~$2,200)
            max_positions=25
        )
        
        # Tighter risk management
        autonomous_trader.update_strategy('stop_loss',
            enabled=True,
            stop_loss_pct=0.02  # 2% stop loss
        )
        
        autonomous_trader.update_strategy('take_profit',
            enabled=True,
            take_profit_pct=0.05  # 5% take profit
        )
        
        # Disable rebalancing to focus on momentum
        autonomous_trader.update_strategy('portfolio_rebalance', enabled=False)
        
        # Set very frequent checking
        autonomous_trader.check_interval = 15  # Check every 15 seconds
        
        logger.info("Autonomous trader settings:")
        logger.info("  • Momentum: 0.1% threshold (ultra-sensitive)")
        logger.info("  • Check interval: 15 seconds")
        logger.info("  • Position size: 3% (~$2,200)")
        logger.info("  • Stop loss: 2%")
        logger.info("  • Take profit: 5%")
        
        # Start autonomous trader automatically
        autonomous_trader_task = asyncio.create_task(autonomous_trader.run())
        background_tasks.append(autonomous_trader_task)
        logger.info("🚀 Autonomous trader started with aggressive settings!")

# REPLACE WITH:
        # Don't start automatically - let user control via API
        logger.info("Autonomous trader initialized (not started)")
```

**2. app/api/autonomous.py** - Remove the internal endpoint:
```python
# DELETE THIS ENTIRE FUNCTION:
# TEMPORARY: Internal endpoint for starting without auth (remove in production)
@router.post("/internal/start")
async def start_autonomous_internal() -> Dict[str, str]:
    """Internal endpoint to start autonomous trading (NO AUTH - REMOVE IN PRODUCTION)."""
    if not dependencies.autonomous_trader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading system not initialized"
        )
    
    if dependencies.autonomous_trader.running:
        return {"status": "already_running", "message": "Autonomous trading is already running"}
    
    # Start in background
    import asyncio
    asyncio.create_task(dependencies.autonomous_trader.run())
    
    return {"status": "started", "message": "Autonomous trading system started (NO AUTH MODE)"}
```

**3. compose.yaml** - Remove temporary entrypoint:
```yaml
# REMOVE THIS LINE:
    entrypoint: ["/app/docker/entrypoint-temp.sh"]

# The service should use the default entrypoint from the Dockerfile
```

### Step 3: Delete Temporary Files
```bash
# Remove all temporary activation scripts
rm -f ACTIVATE_AGGRESSIVE_BOT.sh
rm -f ACTIVATE_BOT.py
rm -f ACTIVATE_TRADING.py
rm -f BOT_STATUS.sh
rm -f ENABLE_CRYPTO_TRADING.py
rm -f FINAL_START_BOT.py
rm -f MAKE_BOT_TRADE.sh
rm -f MONITOR_BOT.sh
rm -f START_AUTONOMOUS_BOT.sh
rm -f START_BOT.sh
rm -f START_THE_BOT.sh
rm -f START_TRADING_NOW.sh
rm -f adjust_momentum.py
rm -f app/activate_bot.py
rm -f app/start_bot_internal.py
rm -f docker/entrypoint-temp.sh
rm -f manage.py
rm -f start_autonomous.py
rm -f start_bot_simple.py
rm -f start_trading.sh

# Verify they're gone
ls *.py *.sh 2>/dev/null | grep -E "(ACTIVATE|START|BOT|TRADING)"
```

### Step 4: Clean and Rebuild
```bash
# Remove old containers and images
docker compose down -v
docker system prune -f

# Rebuild with clean code
docker compose build --no-cache

# Start services normally
docker compose up -d
```

### Step 5: Verify Normal Operation
```bash
# Check that services are healthy
docker compose ps
curl http://localhost:8000/api/health

# Verify autonomous trader is NOT running
curl http://localhost:8000/api/v1/autonomous/status

# Should show: {"running":false,"strategies":{...}}
```

### Step 6: (Optional) Configure Normal Trading Mode
If you want to use autonomous trading with normal settings:

```bash
# First, create a user and get JWT token
./autostart.sh  # Follow prompts

# Start autonomous trader with auth (normal mode)
curl -X POST http://localhost:8000/api/v1/autonomous/start \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Configure normal settings (optional)
curl -X PATCH http://localhost:8000/api/v1/autonomous/strategy/momentum \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "momentum_threshold": 0.03,
    "momentum_lookback_hours": 6,
    "position_size_pct": 0.02,
    "max_positions": 20
  }'
```

## Verification Checklist

- [ ] All temporary scripts deleted
- [ ] `git status` shows no modified files (or manual edits completed)
- [ ] Docker containers rebuilt
- [ ] Services are healthy
- [ ] Autonomous trader is NOT auto-starting
- [ ] Internal endpoint `/api/v1/autonomous/internal/start` returns 404
- [ ] Normal authentication is required for all endpoints

## Troubleshooting

### If bot is still running after revert:
```bash
# Force stop everything
docker compose down -v
docker rm -f $(docker ps -aq)
docker compose up --build
```

### If migrations fail:
```bash
# The temporary entrypoint skipped migrations
# After reverting, ensure migrations run:
docker compose exec app alembic upgrade head
```

### If you need to preserve data:
```bash
# Backup database before reverting
docker compose exec db pg_dump -U postgres trademk1 > backup.sql

# After revert and rebuild, restore:
docker compose exec db psql -U postgres trademk1 < backup.sql
```

## Important Notes

1. **Always use paper trading** during testing
2. **Monitor closely** after reverting to ensure normal operation
3. **Check logs** for any errors: `docker compose logs -f app`
4. **Document any custom changes** you want to keep

## Post-Reversion Best Practices

1. Set up proper authentication for all users
2. Configure reasonable trading parameters
3. Enable monitoring and alerts
4. Review and test strategies before enabling
5. Set up proper logging and audit trails

Remember: The aggressive mode was designed for testing and should not be used in production!