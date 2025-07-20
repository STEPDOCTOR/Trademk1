"""Performance tracking service for monitoring trading performance."""
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade_history import TradeHistory, TradeType, TradeReason
from app.models.performance_metrics import DailyPerformance, RealtimeMetrics
from app.models.position import Position
from app.models.order import Order
from app.db.postgres import get_session
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


class PerformanceTracker:
    """Service for tracking and analyzing trading performance."""
    
    def __init__(self):
        self.realtime_metrics: Optional[RealtimeMetrics] = None
        self._update_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the performance tracker."""
        logger.info("Initializing performance tracker...")
        
        # Load or create today's realtime metrics
        async with get_session() as session:
            self.realtime_metrics = await self._get_or_create_realtime_metrics(session)
            
        # Start background update task
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("Performance tracker initialized")
    
    async def shutdown(self):
        """Shutdown the performance tracker."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
    
    async def record_trade(
        self,
        order: Order,
        position: Optional[Position],
        reason: TradeReason,
        strategy_name: Optional[str] = None,
        market_conditions: Optional[Dict] = None
    ) -> TradeHistory:
        """Record a completed trade in history."""
        async with get_session() as session:
            # Calculate P&L for sells
            profit_loss = None
            profit_loss_pct = None
            entry_price = None
            
            if order.side == "sell" and position:
                # Calculate realized P&L
                profit_loss = (order.filled_price - position.avg_price) * order.qty
                profit_loss_pct = ((order.filled_price - position.avg_price) / position.avg_price) * 100
                entry_price = position.avg_price
            
            # Get current portfolio value
            portfolio_value = await self._get_portfolio_value(session)
            
            # Count today's trades
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_trade_count = await session.scalar(
                select(func.count(TradeHistory.id))
                .where(TradeHistory.executed_at >= today_start)
            )
            
            # Create trade history record
            trade = TradeHistory(
                symbol=order.symbol,
                trade_type=TradeType.BUY if order.side == "buy" else TradeType.SELL,
                quantity=order.qty,
                price=order.filled_price,
                total_value=order.filled_price * order.qty,
                executed_at=datetime.utcnow(),
                alpaca_order_id=order.alpaca_order_id,
                reason=reason,
                strategy_name=strategy_name,
                entry_price=entry_price,
                profit_loss=profit_loss,
                profit_loss_pct=profit_loss_pct,
                market_conditions=market_conditions,
                position_size_before=position.qty if position else 0,
                position_size_after=(position.qty + order.qty) if order.side == "buy" and position else 
                                   (position.qty - order.qty if position else 0),
                portfolio_value_at_trade=portfolio_value,
                trading_day=date.today(),
                daily_trade_number=daily_trade_count + 1
            )
            
            session.add(trade)
            await session.commit()
            await session.refresh(trade)
            
            # Update realtime metrics
            await self._update_realtime_metrics_for_trade(trade)
            
            logger.info(
                f"Recorded trade: {trade.trade_type.value} {trade.quantity} "
                f"{trade.symbol} @ ${trade.price:.2f} "
                f"(P&L: ${trade.profit_loss:.2f} / {trade.profit_loss_pct:.2f}%)" 
                if trade.profit_loss else ""
            )
            
            return trade
    
    async def get_daily_performance(self, trading_date: Optional[date] = None) -> Optional[DailyPerformance]:
        """Get performance metrics for a specific day."""
        if not trading_date:
            trading_date = date.today()
            
        async with get_session() as session:
            return await session.scalar(
                select(DailyPerformance)
                .where(DailyPerformance.trading_date == trading_date)
            )
    
    async def calculate_daily_performance(self, trading_date: Optional[date] = None) -> DailyPerformance:
        """Calculate and store daily performance metrics."""
        if not trading_date:
            trading_date = date.today()
            
        async with get_session() as session:
            # Get all trades for the day
            trades = await session.scalars(
                select(TradeHistory)
                .where(TradeHistory.trading_day == trading_date)
                .order_by(TradeHistory.executed_at)
            )
            trades_list = list(trades)
            
            if not trades_list:
                logger.info(f"No trades found for {trading_date}")
                return None
            
            # Calculate metrics
            total_trades = len(trades_list)
            winning_trades = sum(1 for t in trades_list if t.profit_loss and t.profit_loss > 0)
            losing_trades = sum(1 for t in trades_list if t.profit_loss and t.profit_loss < 0)
            
            total_pnl = sum(t.profit_loss for t in trades_list if t.profit_loss) or 0
            total_volume = sum(t.total_value for t in trades_list) or 0
            
            wins = [t.profit_loss for t in trades_list if t.profit_loss and t.profit_loss > 0]
            losses = [t.profit_loss for t in trades_list if t.profit_loss and t.profit_loss < 0]
            
            # Strategy breakdown
            trades_by_strategy = {}
            pnl_by_strategy = {}
            
            for trade in trades_list:
                strategy = trade.strategy_name or "manual"
                trades_by_strategy[strategy] = trades_by_strategy.get(strategy, 0) + 1
                if trade.profit_loss:
                    pnl_by_strategy[strategy] = pnl_by_strategy.get(strategy, 0) + trade.profit_loss
            
            # Get or create daily performance record
            perf = await session.scalar(
                select(DailyPerformance)
                .where(DailyPerformance.trading_date == trading_date)
            )
            
            if not perf:
                perf = DailyPerformance(trading_date=trading_date)
                session.add(perf)
            
            # Update metrics
            perf.total_trades = total_trades
            perf.winning_trades = winning_trades
            perf.losing_trades = losing_trades
            perf.win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            perf.total_profit_loss = total_pnl
            perf.best_trade = max(wins) if wins else 0
            perf.worst_trade = min(losses) if losses else 0
            perf.average_win = (sum(wins) / len(wins)) if wins else 0
            perf.average_loss = (sum(losses) / len(losses)) if losses else 0
            
            perf.total_volume_traded = total_volume
            perf.profit_factor = (sum(wins) / abs(sum(losses))) if losses else float('inf')
            
            perf.trades_by_strategy = trades_by_strategy
            perf.pnl_by_strategy = pnl_by_strategy
            
            perf.calculated_at = datetime.utcnow()
            
            await session.commit()
            
            logger.info(
                f"Daily performance for {trading_date}: "
                f"{total_trades} trades, "
                f"Win rate: {perf.win_rate:.1f}%, "
                f"P&L: ${total_pnl:.2f}"
            )
            
            return perf
    
    async def check_daily_limits(self, current_pnl: float) -> Dict[str, Any]:
        """Check if daily loss limits or profit targets are hit."""
        # TODO: Get these from user preferences
        daily_loss_limit = -1000  # $1,000 daily loss limit
        daily_profit_target = 2000  # $2,000 daily profit target
        
        status = {
            "loss_limit_hit": current_pnl <= daily_loss_limit,
            "profit_target_hit": current_pnl >= daily_profit_target,
            "current_pnl": current_pnl,
            "loss_limit": daily_loss_limit,
            "profit_target": daily_profit_target,
            "pct_to_loss_limit": (current_pnl / daily_loss_limit * 100) if daily_loss_limit else 0,
            "pct_to_profit_target": (current_pnl / daily_profit_target * 100) if daily_profit_target else 0
        }
        
        if status["loss_limit_hit"]:
            logger.warning(f"Daily loss limit hit! Current P&L: ${current_pnl:.2f}")
            await self._record_limit_hit("loss", current_pnl)
        
        if status["profit_target_hit"]:
            logger.info(f"Daily profit target hit! Current P&L: ${current_pnl:.2f}")
            await self._record_limit_hit("profit", current_pnl)
        
        return status
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """Get current real-time performance metrics."""
        if not self.realtime_metrics:
            return {}
        
        async with get_session() as session:
            # Refresh metrics from database
            await session.refresh(self.realtime_metrics)
            
            return {
                "session_start": self.realtime_metrics.session_start.isoformat(),
                "last_updated": self.realtime_metrics.last_updated.isoformat(),
                "unrealized_pnl": self.realtime_metrics.unrealized_pnl,
                "realized_pnl": self.realtime_metrics.realized_pnl,
                "total_pnl": self.realtime_metrics.total_pnl,
                "total_pnl_pct": self.realtime_metrics.total_pnl_pct,
                "open_positions": self.realtime_metrics.open_positions,
                "total_position_value": self.realtime_metrics.total_position_value,
                "cash_available": self.realtime_metrics.cash_available,
                "buying_power": self.realtime_metrics.buying_power,
                "trades_today": self.realtime_metrics.trades_today,
                "winning_trades_today": self.realtime_metrics.winning_trades_today,
                "losing_trades_today": self.realtime_metrics.losing_trades_today,
                "volume_today": self.realtime_metrics.volume_today,
                "current_risk_exposure": self.realtime_metrics.current_risk_exposure,
                "risk_exposure_pct": self.realtime_metrics.risk_exposure_pct,
                "active_strategies": self.realtime_metrics.active_strategies,
                "market_status": self.realtime_metrics.market_status
            }
    
    async def _update_loop(self):
        """Background task to update realtime metrics."""
        while True:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                await self._update_realtime_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating realtime metrics: {e}")
    
    async def _update_realtime_metrics(self):
        """Update realtime performance metrics."""
        async with get_session() as session:
            # Get current positions
            positions = await session.scalars(
                select(Position)
                .where(Position.qty > 0)
            )
            positions_list = list(positions)
            
            # Calculate unrealized P&L
            unrealized_pnl = sum(p.unrealized_pnl or 0 for p in positions_list)
            total_position_value = sum(p.market_value or 0 for p in positions_list)
            
            # Get today's trades
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_trades = await session.scalars(
                select(TradeHistory)
                .where(TradeHistory.executed_at >= today_start)
            )
            today_trades_list = list(today_trades)
            
            # Calculate realized P&L for today
            realized_pnl = sum(t.profit_loss for t in today_trades_list if t.profit_loss) or 0
            
            # Update metrics
            if self.realtime_metrics:
                self.realtime_metrics.last_updated = datetime.utcnow()
                self.realtime_metrics.unrealized_pnl = unrealized_pnl
                self.realtime_metrics.realized_pnl = realized_pnl
                self.realtime_metrics.total_pnl = unrealized_pnl + realized_pnl
                self.realtime_metrics.open_positions = len(positions_list)
                self.realtime_metrics.total_position_value = total_position_value
                self.realtime_metrics.trades_today = len(today_trades_list)
                self.realtime_metrics.winning_trades_today = sum(
                    1 for t in today_trades_list if t.profit_loss and t.profit_loss > 0
                )
                self.realtime_metrics.losing_trades_today = sum(
                    1 for t in today_trades_list if t.profit_loss and t.profit_loss < 0
                )
                self.realtime_metrics.volume_today = sum(t.total_value for t in today_trades_list)
                
                session.add(self.realtime_metrics)
                await session.commit()
    
    async def _update_realtime_metrics_for_trade(self, trade: TradeHistory):
        """Update realtime metrics after a trade."""
        if not self.realtime_metrics:
            return
        
        async with get_session() as session:
            self.realtime_metrics.trades_today += 1
            self.realtime_metrics.volume_today += trade.total_value
            
            if trade.profit_loss:
                if trade.profit_loss > 0:
                    self.realtime_metrics.winning_trades_today += 1
                else:
                    self.realtime_metrics.losing_trades_today += 1
                
                self.realtime_metrics.realized_pnl += trade.profit_loss
            
            session.add(self.realtime_metrics)
            await session.commit()
    
    async def _get_or_create_realtime_metrics(self, session: AsyncSession) -> RealtimeMetrics:
        """Get or create realtime metrics for today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        metrics = await session.scalar(
            select(RealtimeMetrics)
            .where(RealtimeMetrics.session_start >= today_start)
        )
        
        if not metrics:
            metrics = RealtimeMetrics(
                session_start=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                active_strategies=["momentum", "stop_loss", "take_profit"]
            )
            session.add(metrics)
            await session.commit()
            await session.refresh(metrics)
        
        return metrics
    
    async def _get_portfolio_value(self, session: AsyncSession) -> float:
        """Get current portfolio value."""
        positions = await session.scalars(
            select(Position)
            .where(Position.qty > 0)
        )
        return sum(p.market_value or 0 for p in positions)
    
    async def _record_limit_hit(self, limit_type: str, current_pnl: float):
        """Record when a daily limit is hit."""
        async with get_session() as session:
            today_perf = await self.get_daily_performance()
            if today_perf:
                if limit_type == "loss":
                    today_perf.daily_loss_limit_hit = datetime.utcnow()
                else:
                    today_perf.daily_profit_target_hit = datetime.utcnow()
                
                session.add(today_perf)
                await session.commit()


# Global instance
performance_tracker = PerformanceTracker()