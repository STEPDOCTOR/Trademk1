"""Multi-strategy portfolio manager."""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import pandas as pd
import redis.asyncio as redis

from app.config.settings import get_settings
from app.services.strategies.base import BaseStrategy, Signal, SignalType, StrategyConfig
from app.services.strategies.risk_manager import AdvancedRiskManager, RiskLevel
from app.services.strategies.sma_crossover import SMACrossoverStrategy
from app.services.strategies.momentum import MomentumStrategy


logger = logging.getLogger(__name__)


class StrategyAllocation:
    """Manages allocation between multiple strategies."""
    
    def __init__(
        self,
        strategy_id: str,
        strategy: BaseStrategy,
        allocation: float,
        enabled: bool = True
    ):
        self.strategy_id = strategy_id
        self.strategy = strategy
        self.allocation = allocation
        self.enabled = enabled
        self.performance_score = 0.5  # Initial neutral score
        self.recent_signals: List[Signal] = []
        

class MultiStrategyPortfolioManager:
    """Manages multiple trading strategies with dynamic allocation."""
    
    def __init__(self):
        settings = get_settings()
        self.redis_url = settings.REDIS_URL
        self.redis_client: Optional[redis.Redis] = None
        
        # Strategy management
        self.strategies: Dict[str, StrategyAllocation] = {}
        self.risk_manager = AdvancedRiskManager()
        
        # Portfolio state
        self.current_positions: Dict[str, float] = {}
        self.account_value = 100000  # Default, updated from execution engine
        self.market_prices: Dict[str, float] = {}
        
        # Configuration
        self.rebalance_frequency = timedelta(days=7)
        self.last_rebalance = datetime.utcnow()
        self.min_allocation = 0.05  # 5% minimum
        self.max_allocation = 0.40  # 40% maximum
        
        self._running = False
        self._tasks = []
        
    async def initialize(self):
        """Initialize portfolio manager."""
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info("Portfolio manager initialized")
        
    def add_strategy(
        self,
        strategy: BaseStrategy,
        initial_allocation: float = 0.25
    ):
        """Add a strategy to the portfolio."""
        allocation = StrategyAllocation(
            strategy_id=strategy.strategy_id,
            strategy=strategy,
            allocation=initial_allocation
        )
        self.strategies[strategy.strategy_id] = allocation
        logger.info(f"Added strategy {strategy.name} with {initial_allocation*100}% allocation")
        
    def remove_strategy(self, strategy_id: str):
        """Remove a strategy from the portfolio."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            self._normalize_allocations()
            logger.info(f"Removed strategy {strategy_id}")
            
    async def run(self):
        """Main portfolio management loop."""
        if not self.redis_client:
            raise RuntimeError("Portfolio manager not initialized")
            
        self._running = True
        
        # Start signal processing
        signal_task = asyncio.create_task(self._process_signals())
        self._tasks.append(signal_task)
        
        # Start rebalancing task
        rebalance_task = asyncio.create_task(self._rebalance_loop())
        self._tasks.append(rebalance_task)
        
        # Start performance monitoring
        monitor_task = asyncio.create_task(self._monitor_performance())
        self._tasks.append(monitor_task)
        
        logger.info("Portfolio manager started")
        
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Portfolio manager tasks cancelled")
            
    async def _process_signals(self):
        """Process signals from all strategies."""
        while self._running:
            try:
                # Get market data
                market_data = await self._fetch_market_data()
                if market_data.empty:
                    await asyncio.sleep(60)
                    continue
                    
                # Update market prices
                self._update_market_prices(market_data)
                
                # Update risk manager history
                self.risk_manager.update_history(
                    self.account_value,
                    self.current_positions,
                    self.market_prices,
                    datetime.utcnow()
                )
                
                # Collect signals from all strategies
                all_signals = []
                
                for strategy_id, allocation in self.strategies.items():
                    if not allocation.enabled:
                        continue
                        
                    try:
                        # Get signals from strategy
                        signals = await allocation.strategy.execute(
                            market_data,
                            self.current_positions
                        )
                        
                        # Scale by allocation
                        for signal in signals:
                            signal.metadata['allocation'] = allocation.allocation
                            all_signals.append(signal)
                            
                        # Track recent signals
                        allocation.recent_signals.extend(signals)
                        if len(allocation.recent_signals) > 100:
                            allocation.recent_signals = allocation.recent_signals[-100:]
                            
                    except Exception as e:
                        logger.error(f"Error processing strategy {strategy_id}: {e}")
                        
                # Apply portfolio-level risk filters
                filtered_signals, rejected = self.risk_manager.filter_signals_by_risk(
                    all_signals,
                    self.current_positions,
                    self.market_prices,
                    self.account_value
                )
                
                # Log rejected signals
                for reason in rejected:
                    logger.warning(f"Signal rejected: {reason}")
                    
                # Combine and prioritize signals
                final_signals = self._combine_signals(filtered_signals)
                
                # Submit signals to execution engine
                for signal in final_signals:
                    await self._submit_signal(signal)
                    
                # Update positions (would come from execution engine in practice)
                await self._update_positions()
                
            except Exception as e:
                logger.error(f"Error in signal processing: {e}")
                
            await asyncio.sleep(60)  # Process every minute
            
    async def _fetch_market_data(self) -> pd.DataFrame:
        """Fetch recent market data from QuestDB."""
        # This would query QuestDB for recent price data
        # For now, return empty DataFrame
        return pd.DataFrame()
        
    def _update_market_prices(self, market_data: pd.DataFrame):
        """Update current market prices from data."""
        if market_data.empty:
            return
            
        latest_prices = market_data.groupby('symbol')['close'].last()
        self.market_prices.update(latest_prices.to_dict())
        
    def _combine_signals(self, signals: List[Signal]) -> List[Signal]:
        """Combine signals from multiple strategies."""
        # Group signals by symbol and type
        signal_groups: Dict[Tuple[str, SignalType], List[Signal]] = {}
        
        for signal in signals:
            key = (signal.symbol, signal.signal_type)
            if key not in signal_groups:
                signal_groups[key] = []
            signal_groups[key].append(signal)
            
        # Combine signals for each symbol/type
        combined_signals = []
        
        for (symbol, signal_type), group_signals in signal_groups.items():
            if len(group_signals) == 1:
                combined_signals.append(group_signals[0])
            else:
                # Combine multiple signals
                combined = self._merge_signals(group_signals)
                combined_signals.append(combined)
                
        # Sort by strength
        combined_signals.sort(key=lambda s: s.strength, reverse=True)
        
        return combined_signals
        
    def _merge_signals(self, signals: List[Signal]) -> Signal:
        """Merge multiple signals for the same symbol/type."""
        # Weighted average based on allocation and signal strength
        total_weight = 0
        weighted_strength = 0
        reasons = []
        
        for signal in signals:
            allocation = signal.metadata.get('allocation', 0.25)
            weight = allocation * signal.strength
            total_weight += weight
            weighted_strength += weight * signal.strength
            reasons.append(f"{signal.strategy_id}: {signal.reason}")
            
        avg_strength = weighted_strength / total_weight if total_weight > 0 else 0
        
        # Create merged signal
        merged = Signal(
            strategy_id="portfolio_combined",
            symbol=signals[0].symbol,
            signal_type=signals[0].signal_type,
            strength=avg_strength,
            quantity=signals[0].quantity,  # Will be recalculated
            reason=f"Combined signal: {'; '.join(reasons)}",
            metadata={
                'source_strategies': [s.strategy_id for s in signals],
                'signal_count': len(signals)
            }
        )
        
        return merged
        
    async def _submit_signal(self, signal: Signal):
        """Submit signal to execution engine via Redis."""
        if not self.redis_client:
            return
            
        trade_signal = signal.to_trade_signal()
        if trade_signal:
            # Add portfolio manager metadata
            trade_signal['metadata']['portfolio_manager'] = True
            trade_signal['metadata']['risk_adjusted'] = True
            
            # Calculate position size using risk manager
            if signal.signal_type == SignalType.BUY:
                suggestions = self.risk_manager.suggest_position_sizes(
                    [signal],
                    self.account_value,
                    self.market_prices,
                    self.current_positions
                )
                if signal.symbol in suggestions:
                    trade_signal['qty'] = suggestions[signal.symbol]
                    
            # Publish to Redis
            await self.redis_client.publish(
                "trade_signals",
                json.dumps(trade_signal)
            )
            
            logger.info(f"Submitted signal: {signal.symbol} {signal.signal_type.value}")
            
    async def _update_positions(self):
        """Update current positions from execution engine."""
        # This would fetch actual positions from the database
        # For now, we'll simulate
        pass
        
    async def _rebalance_loop(self):
        """Periodic rebalancing of strategy allocations."""
        while self._running:
            try:
                # Check if rebalancing is needed
                if datetime.utcnow() - self.last_rebalance >= self.rebalance_frequency:
                    await self._rebalance_allocations()
                    self.last_rebalance = datetime.utcnow()
                    
            except Exception as e:
                logger.error(f"Error in rebalancing: {e}")
                
            await asyncio.sleep(3600)  # Check every hour
            
    async def _rebalance_allocations(self):
        """Rebalance strategy allocations based on performance."""
        logger.info("Starting portfolio rebalancing")
        
        # Calculate performance scores
        performance_scores = {}
        
        for strategy_id, allocation in self.strategies.items():
            score = await self._calculate_strategy_performance(allocation)
            performance_scores[strategy_id] = score
            allocation.performance_score = score
            
        # Adjust allocations based on performance
        total_score = sum(performance_scores.values())
        
        if total_score > 0:
            for strategy_id, allocation in self.strategies.items():
                # Calculate new allocation
                new_allocation = performance_scores[strategy_id] / total_score
                
                # Apply min/max constraints
                new_allocation = max(self.min_allocation, min(self.max_allocation, new_allocation))
                
                # Smooth the change
                allocation.allocation = 0.7 * allocation.allocation + 0.3 * new_allocation
                
        # Normalize allocations
        self._normalize_allocations()
        
        # Log new allocations
        for strategy_id, allocation in self.strategies.items():
            logger.info(f"Strategy {strategy_id} allocation: {allocation.allocation*100:.1f}%")
            
    async def _calculate_strategy_performance(
        self,
        allocation: StrategyAllocation
    ) -> float:
        """Calculate performance score for a strategy."""
        # Base score on recent signal accuracy
        if not allocation.recent_signals:
            return 0.5  # Neutral score
            
        # This would analyze actual trade results
        # For now, return a simulated score
        win_rate = 0.55  # Would calculate from actual trades
        avg_return = 0.02  # Would calculate from actual returns
        
        # Combine metrics into score
        score = (win_rate * 0.5 + min(avg_return * 10, 1) * 0.5)
        
        return score
        
    def _normalize_allocations(self):
        """Ensure allocations sum to 1.0."""
        total = sum(a.allocation for a in self.strategies.values())
        
        if total > 0:
            for allocation in self.strategies.values():
                allocation.allocation /= total
                
    async def _monitor_performance(self):
        """Monitor and log portfolio performance."""
        while self._running:
            try:
                # Calculate risk metrics
                risk_metrics = self.risk_manager.calculate_risk_metrics(
                    self.account_value,
                    self.current_positions,
                    self.market_prices,
                    self.account_value
                )
                
                # Log performance
                logger.info(f"Portfolio Risk Level: {risk_metrics.risk_level.value}")
                logger.info(f"Current Drawdown: {risk_metrics.current_drawdown*100:.2f}%")
                logger.info(f"VaR 95%: {risk_metrics.var_95*100:.2f}%")
                
                # Store metrics for API access
                await self._store_metrics(risk_metrics)
                
                # Check for risk warnings
                if risk_metrics.warnings:
                    for warning in risk_metrics.warnings:
                        logger.warning(f"Risk Warning: {warning}")
                        
                # Disable strategies if risk is extreme
                if risk_metrics.risk_level == RiskLevel.EXTREME:
                    logger.error("EXTREME RISK DETECTED - Disabling new positions")
                    for allocation in self.strategies.values():
                        allocation.enabled = False
                elif risk_metrics.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]:
                    # Re-enable strategies when risk normalizes
                    for allocation in self.strategies.values():
                        allocation.enabled = True
                        
            except Exception as e:
                logger.error(f"Error monitoring performance: {e}")
                
            await asyncio.sleep(300)  # Monitor every 5 minutes
            
    async def _store_metrics(self, risk_metrics):
        """Store metrics for API access."""
        if self.redis_client:
            metrics_data = {
                'timestamp': risk_metrics.timestamp.isoformat(),
                'risk_level': risk_metrics.risk_level.value,
                'current_drawdown': risk_metrics.current_drawdown,
                'var_95': risk_metrics.var_95,
                'total_exposure': risk_metrics.total_exposure,
                'leverage_ratio': risk_metrics.leverage_ratio,
                'warnings': risk_metrics.warnings
            }
            
            await self.redis_client.setex(
                'portfolio:risk_metrics',
                300,  # 5 minute expiry
                json.dumps(metrics_data)
            )
            
    async def get_status(self) -> Dict[str, Any]:
        """Get current portfolio status."""
        status = {
            'strategies': {},
            'risk_metrics': None,
            'allocations': {},
            'positions': self.current_positions,
            'account_value': self.account_value
        }
        
        # Get strategy status
        for strategy_id, allocation in self.strategies.items():
            status['strategies'][strategy_id] = {
                'name': allocation.strategy.name,
                'enabled': allocation.enabled,
                'allocation': allocation.allocation,
                'performance_score': allocation.performance_score,
                'recent_signals': len(allocation.recent_signals)
            }
            status['allocations'][strategy_id] = allocation.allocation
            
        # Get risk metrics from Redis
        if self.redis_client:
            metrics_data = await self.redis_client.get('portfolio:risk_metrics')
            if metrics_data:
                status['risk_metrics'] = json.loads(metrics_data)
                
        return status
        
    async def stop(self):
        """Stop the portfolio manager."""
        self._running = False
        
        for task in self._tasks:
            task.cancel()
            
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("Portfolio manager stopped")