#!/usr/bin/env python3
"""Test autonomous trading system directly."""
import asyncio
from app.services.strategies.autonomous_trader import AutonomousTrader
from app.services.trading.execution_engine import ExecutionEngine
from app.services.trading.position_sync import PositionSyncService
from app.db.postgres import init_postgres, close_postgres
from app.config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_autonomous():
    """Test autonomous trading."""
    # Initialize database
    await init_postgres()
    
    # Initialize services
    execution_engine = ExecutionEngine()
    await execution_engine.initialize()
    
    position_sync = PositionSyncService(execution_engine.alpaca_client)
    autonomous_trader = AutonomousTrader(execution_engine)
    
    # Sync positions first
    logger.info("Syncing positions from Alpaca...")
    await position_sync.sync_positions()
    
    # Get position summary
    summary = await position_sync.get_position_summary()
    logger.info(f"Portfolio Summary:")
    logger.info(f"  Total Positions: {summary['total_positions']}")
    logger.info(f"  Total Value: ${summary['total_value']:,.2f}")
    logger.info(f"  Total P&L: ${summary['total_unrealized_pnl']:,.2f} ({summary['total_pnl_pct']:.2f}%)")
    logger.info(f"  Stocks: {summary['stock_positions']}, Crypto: {summary['crypto_positions']}")
    
    # Configure autonomous trader for conservative trading
    logger.info("\nConfiguring autonomous trader...")
    autonomous_trader.update_strategy("stop_loss", enabled=True, stop_loss_pct=0.10)  # 10% stop loss
    autonomous_trader.update_strategy("take_profit", enabled=True, take_profit_pct=0.20)  # 20% take profit
    autonomous_trader.update_strategy("momentum", enabled=True, momentum_threshold=0.05)  # 5% momentum
    autonomous_trader.update_strategy("portfolio_rebalance", enabled=False)  # Disable rebalancing for now
    
    # Run one trading cycle
    logger.info("\nRunning autonomous trading cycle...")
    await autonomous_trader.run_cycle()
    
    # Cleanup
    await execution_engine.stop()
    await close_postgres()
    logger.info("\nTest complete!")

if __name__ == "__main__":
    asyncio.run(test_autonomous())