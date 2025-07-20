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
from app.models.trailing_stop import TrailingStop
from app.services.trading.execution_engine import ExecutionEngine
from app.db.questdb import get_questdb_pool
from app.services.performance_tracker import performance_tracker
from app.services.notification_service import notification_service, NotificationType
from app.services.technical_indicators import technical_indicators
from app.services.position_sizing import position_sizing
from app.services.market_sentiment import market_sentiment_service, MarketSentiment

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
    DAILY_LIMITS = "daily_limits"
    TRAILING_STOP = "trailing_stop"
    TECHNICAL_ANALYSIS = "technical_analysis"


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
            StrategyType.DAILY_LIMITS: AutonomousStrategy(StrategyType.DAILY_LIMITS),
            StrategyType.TRAILING_STOP: AutonomousStrategy(StrategyType.TRAILING_STOP),
            StrategyType.TECHNICAL_ANALYSIS: AutonomousStrategy(StrategyType.TECHNICAL_ANALYSIS),
        }
        # Configure daily limits
        self.strategies[StrategyType.DAILY_LIMITS].enabled = True
        self.strategies[StrategyType.DAILY_LIMITS].daily_loss_limit = -1000  # $1,000 loss limit
        self.strategies[StrategyType.DAILY_LIMITS].daily_profit_target = 2000  # $2,000 profit target
        self.strategies[StrategyType.DAILY_LIMITS].stop_on_loss_limit = True
        self.strategies[StrategyType.DAILY_LIMITS].stop_on_profit_target = False
        
        # Configure trailing stops
        self.strategies[StrategyType.TRAILING_STOP].enabled = True
        self.strategies[StrategyType.TRAILING_STOP].trail_percent = 0.02  # 2% trailing stop
        self.strategies[StrategyType.TRAILING_STOP].activate_after_profit_pct = 0.01  # Activate after 1% profit
        
        # Configure technical analysis
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].enabled = True
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].min_confidence = 0.6  # 60% confidence threshold
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].use_rsi = True
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].use_macd = True
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].use_volume = True
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].position_size_pct = 0.02  # 2% per position
        self.strategies[StrategyType.TECHNICAL_ANALYSIS].max_positions = 20
        
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
        
        # Trailing Stop Check
        if self.strategies[StrategyType.TRAILING_STOP].enabled:
            trailing_signal = await self._check_trailing_stop(position, current_price, pnl_pct)
            if trailing_signal:
                signals.append(trailing_signal)
                return signals  # Exit immediately if trailing stop hit
        
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
                
        # Take Profit Check with scaling
        if self.strategies[StrategyType.TAKE_PROFIT].enabled:
            if pnl_pct > self.strategies[StrategyType.TAKE_PROFIT].take_profit_pct:
                # Use position sizing service for scale-out strategy
                sell_qty = position_sizing.scale_out_strategy(position.qty, pnl_pct / 100)
                
                if sell_qty > 0:
                    logger.info(f"Take profit triggered for {position.symbol}: {pnl_pct:.2%} gain, selling {sell_qty} shares")
                    signals.append(TradingSignal(
                        symbol=position.symbol,
                        side="sell",
                        qty=int(sell_qty),
                        reason=f"Take profit: {pnl_pct:.2%} gain (scaled exit)"
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
        
        # Technical Analysis
        if self.strategies[StrategyType.TECHNICAL_ANALYSIS].enabled:
            tech_signals = await technical_indicators.get_technical_signals(position.symbol)
            if tech_signals:
                # Check for strong sell signals
                if (tech_signals.overall_signal in ["sell", "strong_sell"] and 
                    tech_signals.confidence >= self.strategies[StrategyType.TECHNICAL_ANALYSIS].min_confidence):
                    logger.info(
                        f"Technical sell signal for {position.symbol}: "
                        f"{tech_signals.overall_signal} (confidence: {tech_signals.confidence:.2f})"
                    )
                    signals.append(TradingSignal(
                        symbol=position.symbol,
                        side="sell",
                        qty=position.qty * 0.5,  # Sell half on technical signal
                        reason=f"Technical: {tech_signals.overall_signal} (RSI:{tech_signals.rsi:.0f}, MACD:{tech_signals.macd_cross})"
                    ))
                
        return signals
        
    async def find_new_opportunities(self) -> List[TradingSignal]:
        """Find new trading opportunities."""
        signals = []
        
        # Get account info
        account_info = await self.execution_engine.alpaca_client.get_account()
        buying_power = float(account_info["buying_power"])
        portfolio_value = float(account_info["portfolio_value"])
        
        # Get current positions
        async with optimized_db.get_session() as db:
            result = await db.execute(
                select(Position).where(Position.qty > 0)
            )
            positions_list = list(result.scalars().all())
            current_positions = {pos.symbol for pos in positions_list}
            num_positions = len(positions_list)
            
            # Don't exceed max positions
            max_positions = max(
                self.strategies[StrategyType.MOMENTUM].max_positions,
                self.strategies[StrategyType.TECHNICAL_ANALYSIS].max_positions if hasattr(self.strategies[StrategyType.TECHNICAL_ANALYSIS], 'max_positions') else 20
            )
            if num_positions >= max_positions:
                return signals
        
        # Technical Analysis opportunities
        if self.strategies[StrategyType.TECHNICAL_ANALYSIS].enabled:
            # Get symbols to analyze
            async with optimized_db.get_session() as db:
                result = await db.execute(
                    select(Symbol).where(Symbol.is_active == True)
                )
                symbols = [sym.ticker for sym in result.scalars().all() if sym.ticker not in current_positions]
            
            # Scan for technical opportunities
            tech_opportunities = await technical_indicators.scan_for_opportunities(symbols[:30])  # Limit to 30 for performance
            
            for tech_signal in tech_opportunities[:3]:  # Top 3 opportunities
                if tech_signal.confidence >= self.strategies[StrategyType.TECHNICAL_ANALYSIS].min_confidence:
                    # Use position sizing service
                    size_recommendation = await position_sizing.calculate_position_size(
                        symbol=tech_signal.symbol,
                        account_value=portfolio_value,
                        current_price=tech_signal.current_price,
                        signal_confidence=tech_signal.confidence,
                        existing_positions=num_positions,
                        max_positions=max_positions,
                        risk_per_trade=0.01  # 1% risk per trade
                    )
                    
                    if size_recommendation.shares > 0:
                        signals.append(TradingSignal(
                            symbol=tech_signal.symbol,
                            side="buy",
                            qty=size_recommendation.shares,
                            reason=f"Technical buy: {tech_signal.overall_signal} (RSI:{tech_signal.rsi:.0f}, MACD:{tech_signal.macd_cross}, conf:{tech_signal.confidence:.2f}, risk:{size_recommendation.risk_score:.2f})"
                        ))
                        logger.info(f"Position sizing for {tech_signal.symbol}: {size_recommendation.shares} shares, reasoning: {', '.join(size_recommendation.reasoning)}")
                
        # Momentum opportunities
        if self.strategies[StrategyType.MOMENTUM].enabled:
            # Check top movers
            top_movers = await self._get_top_movers()
            
            for symbol, momentum in top_movers[:5]:  # Top 5 movers
                if symbol in current_positions:
                    continue
                    
                # Skip if we already have a technical signal for this symbol
                if any(s.symbol == symbol for s in signals):
                    continue
                    
                price = await self._get_latest_price(symbol)
                if not price:
                    continue
                
                # Use position sizing for momentum trades too
                # Adjust confidence based on market sentiment
                base_confidence = min(momentum / 0.05, 1.0)
                if hasattr(self, '_market_analysis') and self._market_analysis:
                    if self._market_analysis.overall_sentiment == MarketSentiment.VERY_BULLISH:
                        base_confidence *= 1.2
                    elif self._market_analysis.overall_sentiment == MarketSentiment.BEARISH:
                        base_confidence *= 0.8
                    elif self._market_analysis.overall_sentiment == MarketSentiment.VERY_BEARISH:
                        base_confidence *= 0.6
                
                size_recommendation = await position_sizing.calculate_position_size(
                    symbol=symbol,
                    account_value=portfolio_value,
                    current_price=price,
                    signal_confidence=min(base_confidence, 1.0),
                    existing_positions=num_positions,
                    max_positions=max_positions,
                    risk_per_trade=0.01
                )
                
                if size_recommendation.shares > 0:
                    signals.append(TradingSignal(
                        symbol=symbol,
                        side="buy",
                        qty=size_recommendation.shares,
                        reason=f"Momentum buy: {momentum:.2%} gain in 24h (risk:{size_recommendation.risk_score:.2f})"
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
    
    async def _check_trailing_stop(self, position: Position, current_price: float, pnl_pct: float) -> Optional[TradingSignal]:
        """Check and update trailing stop for a position."""
        async with optimized_db.get_session() as db:
            # Get or create trailing stop
            trailing_stop = await db.scalar(
                select(TrailingStop).where(TrailingStop.symbol == position.symbol)
            )
            
            if not trailing_stop:
                # Only create trailing stop if position is profitable enough
                min_profit = self.strategies[StrategyType.TRAILING_STOP].activate_after_profit_pct
                if pnl_pct < min_profit:
                    return None
                
                # Create new trailing stop
                trail_pct = self.strategies[StrategyType.TRAILING_STOP].trail_percent
                trailing_stop = TrailingStop(
                    symbol=position.symbol,
                    trail_percent=trail_pct,
                    initial_price=position.avg_price,
                    highest_price=current_price,
                    stop_price=current_price * (1 - trail_pct),
                    enabled=True,
                    is_active=True
                )
                db.add(trailing_stop)
                await db.commit()
                logger.info(f"Created trailing stop for {position.symbol} at ${trailing_stop.stop_price:.2f}")
                return None
            
            # Update trailing stop
            if trailing_stop.is_active:
                # Update the stop price if we have a new high
                updated = trailing_stop.update_stop(current_price)
                if updated:
                    await db.commit()
                    logger.info(f"Updated trailing stop for {position.symbol} to ${trailing_stop.stop_price:.2f}")
                
                # Check if stop is triggered
                if trailing_stop.check_triggered(current_price):
                    await db.commit()
                    logger.warning(f"Trailing stop triggered for {position.symbol} at ${current_price:.2f}")
                    
                    # Send notification
                    await notification_service.send_notification(
                        NotificationType.TRAILING_STOP_HIT,
                        f"Trailing Stop Hit: {position.symbol}",
                        f"Price dropped to ${current_price:.2f}\nStop was at ${trailing_stop.stop_price:.2f}\nHighest price: ${trailing_stop.highest_price:.2f}",
                        {
                            "symbol": position.symbol,
                            "current_price": current_price,
                            "stop_price": trailing_stop.stop_price,
                            "highest_price": trailing_stop.highest_price
                        }
                    )
                    
                    return TradingSignal(
                        symbol=position.symbol,
                        side="sell",
                        qty=position.qty,
                        reason=f"Trailing stop: price ${current_price:.2f} <= stop ${trailing_stop.stop_price:.2f}"
                    )
            
            return None
        
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
            # Check market sentiment first
            should_trade, reason = await market_sentiment_service.should_trade_aggressively()
            if not should_trade:
                logger.warning(f"Skipping cycle - unfavorable market conditions: {reason}")
                return
            
            # Get market analysis for position sizing adjustments
            market_analysis = await market_sentiment_service.get_market_analysis()
            self._market_analysis = market_analysis  # Store for use in position sizing
            
            # First check daily limits if enabled
            if self.strategies[StrategyType.DAILY_LIMITS].enabled:
                metrics = await performance_tracker.get_realtime_metrics()
                current_pnl = metrics.get('realized_pnl', 0)
                
                if current_pnl is not None:
                    daily_limits = self.strategies[StrategyType.DAILY_LIMITS]
                    
                    # Check loss limit
                    if current_pnl <= daily_limits.daily_loss_limit:
                        logger.warning(f"Daily loss limit hit! Current P&L: ${current_pnl:.2f} (limit: ${daily_limits.daily_loss_limit})")
                        if daily_limits.stop_on_loss_limit:
                            logger.warning("Stopping trading due to loss limit")
                            await self.stop()
                            return
                    
                    # Check profit target
                    if current_pnl >= daily_limits.daily_profit_target:
                        logger.info(f"Daily profit target reached! Current P&L: ${current_pnl:.2f} (target: ${daily_limits.daily_profit_target})")
                        if daily_limits.stop_on_profit_target:
                            logger.info("Stopping trading due to profit target")
                            await self.stop()
                            return
            
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