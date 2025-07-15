"""Strategy configuration management."""
import json
import logging
from typing import Dict, List, Optional, Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db_session
from app.models.strategy_config import StrategyConfiguration
from app.services.strategies.base import StrategyConfig
from app.services.strategies.sma_crossover import SMACrossoverStrategy
from app.services.strategies.momentum import MomentumStrategy
from app.services.strategies.portfolio_manager import MultiStrategyPortfolioManager


logger = logging.getLogger(__name__)


class StrategyConfigManager:
    """Manages strategy configurations in database."""
    
    def __init__(self, portfolio_manager: MultiStrategyPortfolioManager):
        self.portfolio_manager = portfolio_manager
        
    async def load_strategies_from_db(self):
        """Load all enabled strategies from database."""
        async with get_db_session() as db:
            result = await db.execute(
                select(StrategyConfiguration).where(StrategyConfiguration.enabled == True)
            )
            configs = result.scalars().all()
            
            for config in configs:
                try:
                    strategy = self._create_strategy_from_config(config)
                    if strategy:
                        self.portfolio_manager.add_strategy(
                            strategy,
                            initial_allocation=config.allocation
                        )
                        logger.info(f"Loaded strategy {config.strategy_id} from database")
                except Exception as e:
                    logger.error(f"Error loading strategy {config.strategy_id}: {e}")
                    
    async def save_strategy_to_db(
        self,
        strategy_config: StrategyConfig,
        strategy_type: str,
        allocation: float = 0.25
    ) -> str:
        """Save a strategy configuration to database."""
        async with get_db_session() as db:
            db_config = StrategyConfiguration(
                id=uuid4(),
                strategy_id=strategy_config.strategy_id,
                name=strategy_config.name,
                strategy_type=strategy_type,
                enabled=strategy_config.enabled,
                symbols=strategy_config.symbols,
                parameters=strategy_config.parameters,
                risk_parameters=strategy_config.risk_parameters,
                allocation=allocation,
                performance_score=0.5,
                total_signals="0",
                metadata_json={}
            )
            
            db.add(db_config)
            await db.commit()
            
            logger.info(f"Saved strategy {strategy_config.strategy_id} to database")
            return strategy_config.strategy_id
            
    async def update_strategy_config(
        self,
        strategy_id: str,
        updates: Dict[str, Any]
    ):
        """Update strategy configuration in database."""
        async with get_db_session() as db:
            # Get existing config
            result = await db.execute(
                select(StrategyConfiguration).where(
                    StrategyConfiguration.strategy_id == strategy_id
                )
            )
            config = result.scalar_one_or_none()
            
            if not config:
                raise ValueError(f"Strategy {strategy_id} not found")
                
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    
            await db.commit()
            
            # If strategy is loaded, update in memory
            if strategy_id in self.portfolio_manager.strategies:
                allocation = self.portfolio_manager.strategies[strategy_id]
                
                if 'enabled' in updates:
                    allocation.enabled = updates['enabled']
                if 'allocation' in updates:
                    allocation.allocation = updates['allocation']
                    self.portfolio_manager._normalize_allocations()
                    
            logger.info(f"Updated strategy {strategy_id} configuration")
            
    async def delete_strategy_config(self, strategy_id: str):
        """Delete strategy configuration from database."""
        async with get_db_session() as db:
            result = await db.execute(
                select(StrategyConfiguration).where(
                    StrategyConfiguration.strategy_id == strategy_id
                )
            )
            config = result.scalar_one_or_none()
            
            if config:
                await db.delete(config)
                await db.commit()
                
                # Remove from portfolio manager
                if strategy_id in self.portfolio_manager.strategies:
                    self.portfolio_manager.remove_strategy(strategy_id)
                    
                logger.info(f"Deleted strategy {strategy_id}")
                
    async def get_strategy_configs(
        self,
        enabled_only: bool = False
    ) -> List[StrategyConfiguration]:
        """Get all strategy configurations from database."""
        async with get_db_session() as db:
            query = select(StrategyConfiguration)
            if enabled_only:
                query = query.where(StrategyConfiguration.enabled == True)
                
            result = await db.execute(query)
            return result.scalars().all()
            
    async def update_performance_metrics(
        self,
        strategy_id: str,
        performance_score: float,
        total_signals: int,
        last_signal_time: Optional[str] = None
    ):
        """Update strategy performance metrics in database."""
        async with get_db_session() as db:
            stmt = (
                update(StrategyConfiguration)
                .where(StrategyConfiguration.strategy_id == strategy_id)
                .values(
                    performance_score=performance_score,
                    total_signals=str(total_signals),
                    last_signal_time=last_signal_time
                )
            )
            await db.execute(stmt)
            await db.commit()
            
    def _create_strategy_from_config(
        self,
        db_config: StrategyConfiguration
    ) -> Optional[Any]:
        """Create strategy instance from database configuration."""
        try:
            # Create StrategyConfig
            config = StrategyConfig(
                strategy_id=db_config.strategy_id,
                name=db_config.name,
                symbols=db_config.symbols,
                enabled=db_config.enabled,
                parameters=db_config.parameters,
                risk_parameters=db_config.risk_parameters
            )
            
            # Create strategy based on type
            if db_config.strategy_type == 'sma_crossover':
                return SMACrossoverStrategy(config)
            elif db_config.strategy_type == 'momentum':
                return MomentumStrategy(config)
            else:
                logger.warning(f"Unknown strategy type: {db_config.strategy_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating strategy from config: {e}")
            return None
            
    async def sync_active_strategies(self):
        """Sync active strategies between database and portfolio manager."""
        # Get strategies from portfolio manager
        active_strategies = set(self.portfolio_manager.strategies.keys())
        
        # Get strategies from database
        async with get_db_session() as db:
            result = await db.execute(
                select(StrategyConfiguration.strategy_id).where(
                    StrategyConfiguration.enabled == True
                )
            )
            db_strategies = set(result.scalars().all())
            
        # Load strategies that are in DB but not in memory
        strategies_to_load = db_strategies - active_strategies
        for strategy_id in strategies_to_load:
            async with get_db_session() as db:
                result = await db.execute(
                    select(StrategyConfiguration).where(
                        StrategyConfiguration.strategy_id == strategy_id
                    )
                )
                config = result.scalar_one_or_none()
                
                if config:
                    strategy = self._create_strategy_from_config(config)
                    if strategy:
                        self.portfolio_manager.add_strategy(
                            strategy,
                            initial_allocation=config.allocation
                        )
                        
        # Disable strategies that are in memory but not enabled in DB
        strategies_to_disable = active_strategies - db_strategies
        for strategy_id in strategies_to_disable:
            if strategy_id in self.portfolio_manager.strategies:
                self.portfolio_manager.strategies[strategy_id].enabled = False
                
        logger.info("Synced active strategies with database")