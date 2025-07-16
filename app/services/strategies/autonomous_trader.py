"""Autonomous trading system that manages positions intelligently."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
import numpy as np

from app.db.optimized_postgres import optimized_db
from app.models.position import Position
from app.models.symbol import Symbol
from app.services.trading.execution_engine import ExecutionEngine
from app.db.questdb import get_questdb_pool

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Trading signal to execute."""
    symbol: str
    side: str
    qty: float
    reason: str


class StrategyType(str, Enum):
    """Types of autonomous strategies."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    PORTFOLIO_REBALANCE = "portfolio_rebalance"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


@dataclass
class AutonomousStrategy:
    """Configuration for an autonomous strategy."""
    strategy_type: StrategyType
    enabled: bool = True
    # Risk parameters
    position_size_pct: float = 0.02  # 2% of portfolio per position
    max_positions: int = 20
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.15  # 15% take profit
    # Strategy-specific parameters
    momentum_lookback_hours: int = 24
    momentum_threshold: float = 0.03  # 3% move
    rebalance_threshold: float = 0.10  # 10% deviation from target


class AutonomousTrader:
    """Main autonomous trading system."""
    
    def __init__(self, execution_engine: ExecutionEngine):
        """Initialize autonomous trader.
        
        Args:
            execution_engine: Engine for executing trades
        """
        self.execution_engine = execution_engine
        self.running = False
        self.strategies = {
            StrategyType.MOMENTUM: AutonomousStrategy(StrategyType.MOMENTUM),
            StrategyType.MEAN_REVERSION: AutonomousStrategy(StrategyType.MEAN_REVERSION),
            StrategyType.PORTFOLIO_REBALANCE: AutonomousStrategy(StrategyType.PORTFOLIO_REBALANCE),
            StrategyType.STOP_LOSS: AutonomousStrategy(StrategyType.STOP_LOSS),
            StrategyType.TAKE_PROFIT: AutonomousStrategy(StrategyType.TAKE_PROFIT),
        }
        self.check_interval = 60  # Check every minute
        self.last_rebalance = datetime.utcnow()
        
    async def analyze_position(self, position: Position) -> List[TradingSignal]:
        """Analyze a position and generate trading signals."""
        signals = []
        
        # Get recent price data
        price_data = await self._get_price_history(position.symbol, hours=24)
        if not price_data:
            return signals
            
        current_price = position.last_price
        avg_price = position.avg_price
        pnl_pct = (current_price - avg_price) / avg_price
        
        # Stop Loss Check
        if self.strategies[StrategyType.STOP_LOSS].enabled:
            if pnl_pct < -self.strategies[StrategyType.STOP_LOSS].stop_loss_pct:
                logger.warning(f"Stop loss triggered for {position.symbol}: {pnl_pct:.2%} loss")
                signals.append(TradingSignal(
                    symbol=position.symbol,
                    side="sell",
                    qty=position.qty,
                    reason=f"Stop loss: {pnl_pct:.2%} loss"
                ))
                
        # Take Profit Check
        if self.strategies[StrategyType.TAKE_PROFIT].enabled:
            if pnl_pct > self.strategies[StrategyType.TAKE_PROFIT].take_profit_pct:
                logger.info(f"Take profit triggered for {position.symbol}: {pnl_pct:.2%} gain")
                signals.append(TradingSignal(
                    symbol=position.symbol,
                    side="sell",
                    qty=position.qty * 0.5,  # Sell half
                    reason=f"Take profit: {pnl_pct:.2%} gain"
                ))
                
        # Momentum Analysis
        if self.strategies[StrategyType.MOMENTUM].enabled and len(price_data) > 10:
            momentum = self._calculate_momentum(price_data)
            if momentum < -self.strategies[StrategyType.MOMENTUM].momentum_threshold:
                logger.info(f"Negative momentum detected for {position.symbol}: {momentum:.2%}")
                signals.append(TradingSignal(
                    symbol=position.symbol,
                    side="sell",
                    qty=position.qty * 0.25,  # Trim 25%
                    reason=f"Negative momentum: {momentum:.2%}"
                ))
                
        return signals
        
    async def find_new_opportunities(self) -> List[TradingSignal]:
        """Find new trading opportunities."""
        signals = []
        
        if not self.strategies[StrategyType.MOMENTUM].enabled:
            return signals
            
        # Get account info
        account_info = await self.execution_engine.alpaca_client.get_account()
        buying_power = account_info["buying_power"]
        
        # Get current positions
        async with optimized_db.get_session() as db:
            result = await db.execute(
                select(Position).where(Position.qty > 0)
            )
            current_positions = {pos.symbol for pos in result.scalars().all()}
            
            # Don't exceed max positions
            if len(current_positions) >= self.strategies[StrategyType.MOMENTUM].max_positions:
                return signals
                
        # Check top movers
        top_movers = await self._get_top_movers()
        
        for symbol, momentum in top_movers[:5]:  # Top 5 movers
            if symbol in current_positions:
                continue
                
            # Calculate position size
            position_value = buying_power * self.strategies[StrategyType.MOMENTUM].position_size_pct
            price = await self._get_latest_price(symbol)
            if not price:
                continue
                
            qty = int(position_value / price)
            if qty > 0:
                signals.append(TradingSignal(
                    symbol=symbol,
                    side="buy",
                    qty=qty,
                    reason=f"Momentum buy: {momentum:.2%} gain in 24h"
                ))
                
        return signals
        
    async def rebalance_portfolio(self) -> List[TradingSignal]:
        """Rebalance portfolio to target allocations."""
        signals = []
        
        if not self.strategies[StrategyType.PORTFOLIO_REBALANCE].enabled:
            return signals
            
        # Only rebalance once per day
        if datetime.utcnow() - self.last_rebalance < timedelta(days=1):
            return signals
            
        async with optimized_db.get_session() as db:
            result = await db.execute(
                select(Position).where(Position.qty > 0)
            )
            positions = result.scalars().all()
            
            if not positions:
                return signals
                
            # Calculate total portfolio value
            total_value = sum(pos.market_value for pos in positions)
            target_allocation = 1.0 / len(positions)  # Equal weight for simplicity
            
            for position in positions:
                current_allocation = position.market_value / total_value
                deviation = abs(current_allocation - target_allocation)
                
                if deviation > self.strategies[StrategyType.PORTFOLIO_REBALANCE].rebalance_threshold:
                    # Calculate rebalance quantity
                    target_value = total_value * target_allocation
                    value_diff = target_value - position.market_value
                    qty_diff = int(value_diff / position.last_price)
                    
                    if qty_diff != 0:
                        signals.append(TradingSignal(
                            symbol=position.symbol,
                            side="buy" if qty_diff > 0 else "sell",
                            qty=abs(qty_diff),
                            reason=f"Rebalance: {current_allocation:.1%} -> {target_allocation:.1%}"
                        ))
                        
        if signals:
            self.last_rebalance = datetime.utcnow()
            
        return signals
        
    async def _get_price_history(self, symbol: str, hours: int = 24) -> List[float]:
        """Get price history from QuestDB."""
        try:
            query = f"""
            SELECT price 
            FROM market_ticks 
            WHERE symbol = '{symbol}' 
            AND timestamp > dateadd('h', -{hours}, now())
            ORDER BY timestamp DESC
            LIMIT 100
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                return [row['price'] for row in result]
        except Exception as e:
            logger.error(f"Error getting price history for {symbol}: {e}")
            return []
            
    async def _get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price for a symbol."""
        prices = await self._get_price_history(symbol, hours=1)
        return prices[0] if prices else None
        
    def _calculate_momentum(self, prices: List[float]) -> float:
        """Calculate momentum as percentage change."""
        if len(prices) < 2:
            return 0.0
        return (prices[0] - prices[-1]) / prices[-1]
        
    async def _get_top_movers(self) -> List[tuple[str, float]]:
        """Get top moving symbols in last 24 hours."""
        try:
            # Get symbols we track
            async with optimized_db.get_session() as db:
                result = await db.execute(
                    select(Symbol).where(Symbol.is_active == True)
                )
                symbols = result.scalars().all()
                
            movers = []
            for symbol in symbols:
                prices = await self._get_price_history(symbol.ticker, hours=24)
                if len(prices) >= 10:
                    momentum = self._calculate_momentum(prices)
                    if momentum > self.strategies[StrategyType.MOMENTUM].momentum_threshold:
                        movers.append((symbol.ticker, momentum))
                        
            # Sort by momentum
            movers.sort(key=lambda x: x[1], reverse=True)
            return movers
            
        except Exception as e:
            logger.error(f"Error getting top movers: {e}")
            return []
            
    async def execute_signals(self, signals: List[TradingSignal]):
        """Execute trading signals."""
        for signal in signals:
            try:
                logger.info(f"Executing signal: {signal}")
                await self.execution_engine._process_signal({
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "qty": signal.qty,
                    "reason": f"[AUTO] {signal.reason}"
                })
            except Exception as e:
                logger.error(f"Error executing signal {signal}: {e}")
                
    async def run_cycle(self):
        """Run one cycle of autonomous trading."""
        try:
            all_signals = []
            
            # Analyze existing positions
            async with optimized_db.get_session() as db:
                result = await db.execute(
                    select(Position).where(Position.qty > 0)
                )
                positions = result.scalars().all()
                
                for position in positions:
                    signals = await self.analyze_position(position)
                    all_signals.extend(signals)
                    
            # Find new opportunities
            new_signals = await self.find_new_opportunities()
            all_signals.extend(new_signals)
            
            # Check for rebalancing
            rebalance_signals = await self.rebalance_portfolio()
            all_signals.extend(rebalance_signals)
            
            # Execute signals
            if all_signals:
                logger.info(f"Generated {len(all_signals)} trading signals")
                await self.execute_signals(all_signals)
            
        except Exception as e:
            logger.error(f"Error in autonomous trading cycle: {e}")
            
    async def run(self):
        """Run the autonomous trading system."""
        self.running = True
        logger.info("Starting autonomous trading system")
        logger.info(f"Enabled strategies: {[s for s, cfg in self.strategies.items() if cfg.enabled]}")
        
        while self.running:
            try:
                await self.run_cycle()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in autonomous trading loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
                
    async def stop(self):
        """Stop the autonomous trading system."""
        logger.info("Stopping autonomous trading system")
        self.running = False
        
    def update_strategy(self, strategy_type: StrategyType, **kwargs):
        """Update strategy configuration."""
        if strategy_type in self.strategies:
            strategy = self.strategies[strategy_type]
            for key, value in kwargs.items():
                if hasattr(strategy, key):
                    setattr(strategy, key, value)
                    logger.info(f"Updated {strategy_type} {key} to {value}")