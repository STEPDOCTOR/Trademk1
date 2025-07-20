"""Backtesting service specifically for aggressive trading strategies."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from app.db.questdb import get_questdb_pool
from app.services.technical_indicators import technical_indicators
from app.services.position_sizing import position_sizing
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestTrade:
    """Represents a trade in backtesting."""
    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    price: float
    value: float
    reason: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    position_value: Optional[float] = None


@dataclass
class BacktestPosition:
    """Represents a position during backtesting."""
    symbol: str
    quantity: int
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    entry_time: datetime
    highest_price: float = 0
    lowest_price: float = float('inf')
    trailing_stop_price: Optional[float] = None


@dataclass
class BacktestResults:
    """Results from a backtest run."""
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    trades: List[BacktestTrade]
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    trades_per_day: float
    best_trade: BacktestTrade
    worst_trade: BacktestTrade
    equity_curve: List[Dict[str, float]]
    daily_returns: List[float]
    strategy_params: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary for API response."""
        return {
            "summary": {
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "initial_capital": self.initial_capital,
                "final_capital": self.final_capital,
                "total_return": self.total_return,
                "total_return_pct": self.total_return_pct,
                "num_trades": len(self.trades),
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": self.win_rate,
                "avg_win": self.avg_win,
                "avg_loss": self.avg_loss,
                "profit_factor": self.profit_factor,
                "max_drawdown": self.max_drawdown,
                "max_drawdown_pct": self.max_drawdown_pct,
                "sharpe_ratio": self.sharpe_ratio,
                "sortino_ratio": self.sortino_ratio,
                "trades_per_day": self.trades_per_day
            },
            "best_trade": {
                "symbol": self.best_trade.symbol,
                "pnl": self.best_trade.pnl,
                "pnl_pct": self.best_trade.pnl_pct,
                "timestamp": self.best_trade.timestamp.isoformat()
            } if self.best_trade else None,
            "worst_trade": {
                "symbol": self.worst_trade.symbol,
                "pnl": self.worst_trade.pnl,
                "pnl_pct": self.worst_trade.pnl_pct,
                "timestamp": self.worst_trade.timestamp.isoformat()
            } if self.worst_trade else None,
            "strategy_params": self.strategy_params,
            "trades_count": len(self.trades),
            "equity_curve_points": len(self.equity_curve)
        }


class AggressiveBacktester:
    """Backtesting engine for aggressive trading strategies."""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.positions: Dict[str, BacktestPosition] = {}
        self.trades: List[BacktestTrade] = []
        self.cash = initial_capital
        self.equity_curve: List[Dict[str, float]] = []
        self.daily_returns: List[float] = []
        
    async def run_backtest(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        strategy_params: Dict[str, Any]
    ) -> BacktestResults:
        """Run backtest for aggressive trading strategies."""
        logger.info(f"Starting backtest from {start_date} to {end_date} for {len(symbols)} symbols")
        
        # Reset state
        self.positions.clear()
        self.trades.clear()
        self.cash = self.initial_capital
        self.equity_curve.clear()
        self.daily_returns.clear()
        
        # Get price data for all symbols
        price_data = await self._load_price_data(symbols, start_date, end_date)
        if not price_data:
            logger.error("No price data available for backtesting")
            return self._generate_empty_results(start_date, end_date, strategy_params)
        
        # Simulate trading day by day
        current_date = start_date
        last_portfolio_value = self.initial_capital
        
        while current_date <= end_date:
            # Get prices for current timestamp
            current_prices = self._get_prices_at_time(price_data, current_date)
            
            if current_prices:
                # Update positions with current prices
                self._update_positions(current_prices)
                
                # Check exit signals for existing positions
                await self._check_exit_signals(current_prices, current_date, strategy_params)
                
                # Check entry signals for new positions
                await self._check_entry_signals(current_prices, current_date, symbols, strategy_params)
                
                # Record equity curve
                portfolio_value = self._calculate_portfolio_value(current_prices)
                self.equity_curve.append({
                    "timestamp": current_date,
                    "value": portfolio_value,
                    "cash": self.cash,
                    "positions_value": portfolio_value - self.cash
                })
                
                # Calculate daily return
                if last_portfolio_value > 0:
                    daily_return = (portfolio_value - last_portfolio_value) / last_portfolio_value
                    self.daily_returns.append(daily_return)
                last_portfolio_value = portfolio_value
            
            # Move to next time period (15 minutes for aggressive trading)
            current_date += timedelta(minutes=15)
        
        # Close all remaining positions at end
        final_prices = self._get_prices_at_time(price_data, end_date)
        if final_prices:
            await self._close_all_positions(final_prices, end_date)
        
        # Generate results
        return self._generate_results(start_date, end_date, strategy_params)
    
    async def _load_price_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """Load historical price data from QuestDB."""
        price_data = {}
        
        for symbol in symbols:
            try:
                query = f"""
                SELECT timestamp, price, volume
                FROM market_ticks
                WHERE symbol = '{symbol}'
                AND timestamp >= '{start_date.isoformat()}'
                AND timestamp <= '{end_date.isoformat()}'
                ORDER BY timestamp ASC
                """
                
                async with get_questdb_pool() as conn:
                    result = await conn.fetch(query)
                    
                if result:
                    df = pd.DataFrame(result)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    price_data[symbol] = df
                    logger.info(f"Loaded {len(df)} price points for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error loading price data for {symbol}: {e}")
        
        return price_data
    
    def _get_prices_at_time(
        self,
        price_data: Dict[str, pd.DataFrame],
        timestamp: datetime
    ) -> Dict[str, float]:
        """Get prices for all symbols at a specific timestamp."""
        prices = {}
        
        for symbol, df in price_data.items():
            # Find the closest price to the timestamp
            if len(df) > 0:
                # Use the last known price up to this timestamp
                mask = df.index <= timestamp
                if mask.any():
                    prices[symbol] = df.loc[mask, 'price'].iloc[-1]
        
        return prices
    
    def _update_positions(self, current_prices: Dict[str, float]):
        """Update positions with current prices."""
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                position.current_price = current_prices[symbol]
                position.market_value = position.quantity * position.current_price
                position.unrealized_pnl = (position.current_price - position.avg_price) * position.quantity
                position.unrealized_pnl_pct = ((position.current_price - position.avg_price) / position.avg_price) * 100
                
                # Track highest/lowest prices
                position.highest_price = max(position.highest_price, position.current_price)
                position.lowest_price = min(position.lowest_price, position.current_price)
    
    async def _check_exit_signals(
        self,
        current_prices: Dict[str, float],
        timestamp: datetime,
        params: Dict[str, Any]
    ):
        """Check for exit signals on existing positions."""
        positions_to_close = []
        
        for symbol, position in self.positions.items():
            if symbol not in current_prices:
                continue
            
            close_position = False
            reason = ""
            
            # Stop loss check
            if params.get('stop_loss_enabled', True):
                stop_loss_pct = params.get('stop_loss_pct', 0.02)
                if position.unrealized_pnl_pct <= -stop_loss_pct * 100:
                    close_position = True
                    reason = f"Stop loss: {position.unrealized_pnl_pct:.2f}%"
            
            # Take profit check
            if not close_position and params.get('take_profit_enabled', True):
                take_profit_pct = params.get('take_profit_pct', 0.05)
                if position.unrealized_pnl_pct >= take_profit_pct * 100:
                    close_position = True
                    reason = f"Take profit: {position.unrealized_pnl_pct:.2f}%"
            
            # Trailing stop check
            if not close_position and params.get('trailing_stop_enabled', True):
                trail_pct = params.get('trail_pct', 0.02)
                if position.trailing_stop_price is None and position.unrealized_pnl_pct > 1:
                    # Activate trailing stop
                    position.trailing_stop_price = position.current_price * (1 - trail_pct)
                elif position.trailing_stop_price is not None:
                    # Update trailing stop
                    new_stop = position.current_price * (1 - trail_pct)
                    if new_stop > position.trailing_stop_price:
                        position.trailing_stop_price = new_stop
                    
                    # Check if triggered
                    if position.current_price <= position.trailing_stop_price:
                        close_position = True
                        reason = f"Trailing stop: ${position.current_price:.2f} <= ${position.trailing_stop_price:.2f}"
            
            # Technical analysis exit
            if not close_position and params.get('technical_exits', True):
                tech_signals = await technical_indicators.get_technical_signals(symbol)
                if tech_signals and tech_signals.overall_signal in ['sell', 'strong_sell']:
                    if tech_signals.confidence >= params.get('min_confidence', 0.6):
                        close_position = True
                        reason = f"Technical sell: {tech_signals.overall_signal}"
            
            if close_position:
                positions_to_close.append((symbol, reason))
        
        # Execute closes
        for symbol, reason in positions_to_close:
            await self._close_position(symbol, current_prices[symbol], timestamp, reason)
    
    async def _check_entry_signals(
        self,
        current_prices: Dict[str, float],
        timestamp: datetime,
        symbols: List[str],
        params: Dict[str, Any]
    ):
        """Check for entry signals for new positions."""
        # Skip if we're at max positions
        max_positions = params.get('max_positions', 20)
        if len(self.positions) >= max_positions:
            return
        
        entry_signals = []
        
        for symbol in symbols:
            if symbol in self.positions or symbol not in current_prices:
                continue
            
            # Momentum check
            if params.get('momentum_enabled', True):
                momentum = await self._calculate_momentum(symbol, timestamp)
                if momentum > params.get('momentum_threshold', 0.001):
                    entry_signals.append((symbol, f"Momentum: {momentum:.2%}", momentum))
            
            # Technical analysis entry
            if params.get('technical_entries', True):
                tech_signals = await technical_indicators.get_technical_signals(symbol)
                if tech_signals and tech_signals.overall_signal in ['buy', 'strong_buy']:
                    if tech_signals.confidence >= params.get('min_confidence', 0.5):
                        entry_signals.append((
                            symbol,
                            f"Technical buy: {tech_signals.overall_signal}",
                            tech_signals.confidence
                        ))
        
        # Sort by confidence/strength and take top opportunities
        entry_signals.sort(key=lambda x: x[2], reverse=True)
        
        for symbol, reason, confidence in entry_signals[:3]:  # Top 3
            if len(self.positions) >= max_positions:
                break
            
            # Calculate position size
            portfolio_value = self._calculate_portfolio_value(current_prices)
            position_size_pct = params.get('position_size_pct', 0.02)
            
            # Use position sizing service if enabled
            if params.get('dynamic_sizing', True):
                size_rec = await position_sizing.calculate_position_size(
                    symbol=symbol,
                    account_value=portfolio_value,
                    current_price=current_prices[symbol],
                    signal_confidence=confidence,
                    existing_positions=len(self.positions),
                    max_positions=max_positions
                )
                position_value = size_rec.risk_adjusted_size
            else:
                position_value = portfolio_value * position_size_pct
            
            # Calculate shares
            shares = int(position_value / current_prices[symbol])
            
            if shares > 0 and self.cash >= shares * current_prices[symbol]:
                await self._open_position(symbol, shares, current_prices[symbol], timestamp, reason)
    
    async def _calculate_momentum(self, symbol: str, timestamp: datetime) -> float:
        """Calculate momentum for a symbol."""
        try:
            query = f"""
            SELECT price
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > '{(timestamp - timedelta(hours=1)).isoformat()}'
            AND timestamp <= '{timestamp.isoformat()}'
            ORDER BY timestamp ASC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                
            if len(result) < 2:
                return 0
            
            prices = [r['price'] for r in result]
            return (prices[-1] - prices[0]) / prices[0]
            
        except Exception as e:
            logger.error(f"Error calculating momentum for {symbol}: {e}")
            return 0
    
    async def _open_position(
        self,
        symbol: str,
        quantity: int,
        price: float,
        timestamp: datetime,
        reason: str
    ):
        """Open a new position."""
        cost = quantity * price
        
        if self.cash >= cost:
            self.cash -= cost
            
            position = BacktestPosition(
                symbol=symbol,
                quantity=quantity,
                avg_price=price,
                current_price=price,
                market_value=cost,
                unrealized_pnl=0,
                unrealized_pnl_pct=0,
                entry_time=timestamp
            )
            
            self.positions[symbol] = position
            
            trade = BacktestTrade(
                timestamp=timestamp,
                symbol=symbol,
                side='buy',
                quantity=quantity,
                price=price,
                value=cost,
                reason=reason
            )
            
            self.trades.append(trade)
            logger.debug(f"Opened position: {symbol} {quantity} shares @ ${price:.2f}")
    
    async def _close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        reason: str
    ):
        """Close an existing position."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        proceeds = position.quantity * price
        pnl = (price - position.avg_price) * position.quantity
        pnl_pct = ((price - position.avg_price) / position.avg_price) * 100
        
        self.cash += proceeds
        
        trade = BacktestTrade(
            timestamp=timestamp,
            symbol=symbol,
            side='sell',
            quantity=position.quantity,
            price=price,
            value=proceeds,
            reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct
        )
        
        self.trades.append(trade)
        del self.positions[symbol]
        
        logger.debug(f"Closed position: {symbol} {position.quantity} shares @ ${price:.2f}, PnL: ${pnl:.2f} ({pnl_pct:.2f}%)")
    
    async def _close_all_positions(self, final_prices: Dict[str, float], timestamp: datetime):
        """Close all remaining positions at end of backtest."""
        symbols_to_close = list(self.positions.keys())
        
        for symbol in symbols_to_close:
            if symbol in final_prices:
                await self._close_position(
                    symbol,
                    final_prices[symbol],
                    timestamp,
                    "End of backtest"
                )
    
    def _calculate_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        positions_value = sum(
            pos.quantity * current_prices.get(sym, pos.current_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + positions_value
    
    def _generate_results(
        self,
        start_date: datetime,
        end_date: datetime,
        strategy_params: Dict[str, Any]
    ) -> BacktestResults:
        """Generate backtest results."""
        # Final values
        final_capital = self.equity_curve[-1]['value'] if self.equity_curve else self.initial_capital
        total_return = final_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        # Trade statistics
        sell_trades = [t for t in self.trades if t.side == 'sell' and t.pnl is not None]
        winning_trades = [t for t in sell_trades if t.pnl > 0]
        losing_trades = [t for t in sell_trades if t.pnl < 0]
        
        win_rate = (len(winning_trades) / len(sell_trades)) * 100 if sell_trades else 0
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        
        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Drawdown calculation
        equity_values = [e['value'] for e in self.equity_curve]
        if equity_values:
            peak = equity_values[0]
            max_dd = 0
            max_dd_pct = 0
            
            for value in equity_values:
                if value > peak:
                    peak = value
                drawdown = peak - value
                drawdown_pct = (drawdown / peak) * 100 if peak > 0 else 0
                
                if drawdown > max_dd:
                    max_dd = drawdown
                    max_dd_pct = drawdown_pct
        else:
            max_dd = 0
            max_dd_pct = 0
        
        # Risk ratios
        if self.daily_returns:
            daily_returns_array = np.array(self.daily_returns)
            
            # Sharpe ratio (assuming 0% risk-free rate)
            if daily_returns_array.std() > 0:
                sharpe_ratio = (daily_returns_array.mean() / daily_returns_array.std()) * np.sqrt(252)
            else:
                sharpe_ratio = 0
            
            # Sortino ratio
            negative_returns = daily_returns_array[daily_returns_array < 0]
            if len(negative_returns) > 0 and negative_returns.std() > 0:
                sortino_ratio = (daily_returns_array.mean() / negative_returns.std()) * np.sqrt(252)
            else:
                sortino_ratio = 0
        else:
            sharpe_ratio = 0
            sortino_ratio = 0
        
        # Best and worst trades
        if sell_trades:
            best_trade = max(sell_trades, key=lambda t: t.pnl)
            worst_trade = min(sell_trades, key=lambda t: t.pnl)
        else:
            best_trade = None
            worst_trade = None
        
        # Trades per day
        num_days = (end_date - start_date).days
        trades_per_day = len(self.trades) / num_days if num_days > 0 else 0
        
        return BacktestResults(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            trades=self.trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            trades_per_day=trades_per_day,
            best_trade=best_trade,
            worst_trade=worst_trade,
            equity_curve=self.equity_curve,
            daily_returns=self.daily_returns,
            strategy_params=strategy_params
        )
    
    def _generate_empty_results(
        self,
        start_date: datetime,
        end_date: datetime,
        strategy_params: Dict[str, Any]
    ) -> BacktestResults:
        """Generate empty results when no data is available."""
        return BacktestResults(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            total_return=0,
            total_return_pct=0,
            trades=[],
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            max_drawdown=0,
            max_drawdown_pct=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            trades_per_day=0,
            best_trade=None,
            worst_trade=None,
            equity_curve=[],
            daily_returns=[],
            strategy_params=strategy_params
        )