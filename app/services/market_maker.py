"""Market maker service for providing liquidity and earning spreads."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np

from app.services.trading.execution_engine import ExecutionEngine
from app.services.trading.alpaca_client import get_alpaca_client
from app.db.optimized_postgres import optimized_db
from app.models.order import Order
from app.monitoring.logger import get_logger
from sqlalchemy import select, and_

logger = get_logger(__name__)


@dataclass
class MarketMakerConfig:
    """Configuration for market making strategy."""
    symbol: str
    spread_bps: int = 10  # Basis points (0.10%)
    order_size: int = 100  # Shares per order
    max_position: int = 1000  # Maximum position size
    order_refresh_seconds: int = 30  # How often to refresh orders
    use_dynamic_spread: bool = True  # Adjust spread based on volatility
    min_spread_bps: int = 5  # Minimum spread
    max_spread_bps: int = 50  # Maximum spread
    inventory_skew: float = 0.5  # How much to skew prices based on inventory
    
    # Risk parameters
    max_loss_per_day: float = 1000
    stop_loss_pct: float = 0.02  # 2% stop loss
    
    # Advanced features
    use_microprice: bool = True  # Use order book imbalance
    layer_orders: bool = True  # Place multiple orders at different levels
    num_layers: int = 3  # Number of order layers
    layer_spacing_bps: int = 5  # Spacing between layers


@dataclass
class MarketMakerState:
    """Current state of market maker for a symbol."""
    symbol: str
    current_position: int
    average_cost: float
    realized_pnl: float
    unrealized_pnl: float
    bid_orders: List[str]  # Order IDs
    ask_orders: List[str]  # Order IDs
    last_update: datetime
    spread_bps: int
    bid_price: float
    ask_price: float
    mid_price: float
    trades_today: int
    volume_today: int


class MarketMaker:
    """Automated market making service."""
    
    def __init__(self, execution_engine: ExecutionEngine):
        self.execution_engine = execution_engine
        self.alpaca_client = get_alpaca_client()
        self.configs: Dict[str, MarketMakerConfig] = {}
        self.states: Dict[str, MarketMakerState] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.daily_pnl: Dict[str, float] = {}
        
    async def start_market_making(self, config: MarketMakerConfig):
        """Start market making for a symbol."""
        symbol = config.symbol
        
        if symbol in self.running_tasks:
            logger.warning(f"Market maker already running for {symbol}")
            return
        
        self.configs[symbol] = config
        
        # Initialize state
        self.states[symbol] = MarketMakerState(
            symbol=symbol,
            current_position=0,
            average_cost=0,
            realized_pnl=0,
            unrealized_pnl=0,
            bid_orders=[],
            ask_orders=[],
            last_update=datetime.utcnow(),
            spread_bps=config.spread_bps,
            bid_price=0,
            ask_price=0,
            mid_price=0,
            trades_today=0,
            volume_today=0
        )
        
        # Load existing position
        await self._load_existing_position(symbol)
        
        # Start market making task
        task = asyncio.create_task(self._market_maker_loop(symbol))
        self.running_tasks[symbol] = task
        
        logger.info(f"Started market making for {symbol}")
    
    async def stop_market_making(self, symbol: str, cancel_orders: bool = True):
        """Stop market making for a symbol."""
        if symbol not in self.running_tasks:
            return
        
        # Cancel task
        task = self.running_tasks.pop(symbol)
        task.cancel()
        
        if cancel_orders:
            # Cancel all open orders
            await self._cancel_all_orders(symbol)
        
        logger.info(f"Stopped market making for {symbol}")
    
    async def _market_maker_loop(self, symbol: str):
        """Main market making loop for a symbol."""
        config = self.configs[symbol]
        
        while True:
            try:
                # Check daily P&L limit
                if await self._check_daily_limit(symbol):
                    logger.warning(f"Daily loss limit reached for {symbol}")
                    break
                
                # Get current market data
                market_data = await self._get_market_data(symbol)
                
                if not market_data:
                    await asyncio.sleep(5)
                    continue
                
                # Calculate optimal quotes
                bid_price, ask_price = await self._calculate_quotes(
                    symbol, market_data, config
                )
                
                # Update state
                state = self.states[symbol]
                state.bid_price = bid_price
                state.ask_price = ask_price
                state.mid_price = market_data['mid_price']
                state.spread_bps = int((ask_price - bid_price) / market_data['mid_price'] * 10000)
                
                # Cancel existing orders
                await self._cancel_all_orders(symbol)
                
                # Place new orders
                await self._place_orders(symbol, bid_price, ask_price, config)
                
                # Update P&L
                await self._update_pnl(symbol)
                
                # Sleep before next update
                await asyncio.sleep(config.order_refresh_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in market maker loop for {symbol}: {e}")
                await asyncio.sleep(10)
    
    async def _get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current market data for a symbol."""
        try:
            # Get quote
            quote = await self.alpaca_client.get_latest_quote(symbol)
            
            # Get recent trades for volatility
            bars = await self.alpaca_client.get_bars(
                symbol,
                timeframe='1Min',
                limit=30
            )
            
            if not bars:
                return None
            
            # Calculate volatility
            returns = []
            for i in range(1, len(bars)):
                ret = (bars[i]['close'] - bars[i-1]['close']) / bars[i-1]['close']
                returns.append(ret)
            
            volatility = np.std(returns) * np.sqrt(390 * 252) if returns else 0.02
            
            # Calculate order book imbalance (simplified)
            bid_size = quote.get('bid_size', 100)
            ask_size = quote.get('ask_size', 100)
            imbalance = (bid_size - ask_size) / (bid_size + ask_size) if (bid_size + ask_size) > 0 else 0
            
            return {
                'bid': quote['bid_price'],
                'ask': quote['ask_price'],
                'mid_price': (quote['bid_price'] + quote['ask_price']) / 2,
                'spread': quote['ask_price'] - quote['bid_price'],
                'volatility': volatility,
                'imbalance': imbalance,
                'last_price': bars[-1]['close']
            }
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None
    
    async def _calculate_quotes(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        config: MarketMakerConfig
    ) -> Tuple[float, float]:
        """Calculate optimal bid and ask prices."""
        mid_price = market_data['mid_price']
        state = self.states[symbol]
        
        # Base spread
        if config.use_dynamic_spread:
            # Adjust spread based on volatility
            vol_adjustment = market_data['volatility'] * 100  # Convert to percentage
            spread_bps = config.spread_bps + int(vol_adjustment * 100)
            spread_bps = max(config.min_spread_bps, min(spread_bps, config.max_spread_bps))
        else:
            spread_bps = config.spread_bps
        
        # Calculate base quotes
        half_spread = mid_price * spread_bps / 20000  # Divide by 2 for half spread
        base_bid = mid_price - half_spread
        base_ask = mid_price + half_spread
        
        # Inventory skew
        if state.current_position != 0:
            position_ratio = state.current_position / config.max_position
            skew = position_ratio * config.inventory_skew * half_spread
            
            # If long, lower prices to reduce position
            # If short, raise prices to reduce position
            base_bid -= skew
            base_ask -= skew
        
        # Microprice adjustment based on order book imbalance
        if config.use_microprice and 'imbalance' in market_data:
            imbalance_adjustment = market_data['imbalance'] * half_spread * 0.2
            base_bid += imbalance_adjustment
            base_ask += imbalance_adjustment
        
        # Round to penny
        bid_price = round(base_bid, 2)
        ask_price = round(base_ask, 2)
        
        # Ensure minimum spread
        if ask_price - bid_price < 0.01:
            ask_price = bid_price + 0.01
        
        return bid_price, ask_price
    
    async def _place_orders(
        self,
        symbol: str,
        bid_price: float,
        ask_price: float,
        config: MarketMakerConfig
    ):
        """Place market making orders."""
        state = self.states[symbol]
        
        # Calculate order sizes based on position
        bid_size = config.order_size
        ask_size = config.order_size
        
        # Reduce size if approaching position limits
        if state.current_position > config.max_position * 0.8:
            bid_size = int(bid_size * 0.5)  # Reduce buying
        elif state.current_position < -config.max_position * 0.8:
            ask_size = int(ask_size * 0.5)  # Reduce selling
        
        # Don't exceed position limits
        if state.current_position + bid_size > config.max_position:
            bid_size = max(0, config.max_position - state.current_position)
        if state.current_position - ask_size < -config.max_position:
            ask_size = max(0, config.max_position + state.current_position)
        
        new_bid_orders = []
        new_ask_orders = []
        
        if config.layer_orders:
            # Place multiple orders at different price levels
            for i in range(config.num_layers):
                layer_offset = i * config.layer_spacing_bps / 10000
                
                # Bid orders
                if bid_size > 0:
                    layer_bid_price = bid_price - (bid_price * layer_offset)
                    layer_bid_size = bid_size // config.num_layers
                    
                    if layer_bid_size > 0:
                        order = await self._place_limit_order(
                            symbol, 'buy', layer_bid_size, layer_bid_price
                        )
                        if order:
                            new_bid_orders.append(order['id'])
                
                # Ask orders
                if ask_size > 0:
                    layer_ask_price = ask_price + (ask_price * layer_offset)
                    layer_ask_size = ask_size // config.num_layers
                    
                    if layer_ask_size > 0:
                        order = await self._place_limit_order(
                            symbol, 'sell', layer_ask_size, layer_ask_price
                        )
                        if order:
                            new_ask_orders.append(order['id'])
        else:
            # Single order at each level
            if bid_size > 0:
                order = await self._place_limit_order(symbol, 'buy', bid_size, bid_price)
                if order:
                    new_bid_orders.append(order['id'])
            
            if ask_size > 0:
                order = await self._place_limit_order(symbol, 'sell', ask_size, ask_price)
                if order:
                    new_ask_orders.append(order['id'])
        
        # Update state
        state.bid_orders = new_bid_orders
        state.ask_orders = new_ask_orders
        state.last_update = datetime.utcnow()
    
    async def _place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float
    ) -> Optional[Dict[str, Any]]:
        """Place a limit order."""
        try:
            order = await self.alpaca_client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type='limit',
                time_in_force='day',
                limit_price=price
            )
            
            logger.debug(f"Placed {side} order for {qty} {symbol} @ ${price}")
            return order
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    async def _cancel_all_orders(self, symbol: str):
        """Cancel all open orders for a symbol."""
        state = self.states.get(symbol)
        if not state:
            return
        
        all_orders = state.bid_orders + state.ask_orders
        
        for order_id in all_orders:
            try:
                await self.alpaca_client.cancel_order(order_id)
            except Exception as e:
                logger.debug(f"Error canceling order {order_id}: {e}")
        
        state.bid_orders = []
        state.ask_orders = []
    
    async def _load_existing_position(self, symbol: str):
        """Load existing position from database."""
        try:
            async with optimized_db.get_session() as db:
                result = await db.execute(
                    select(Order).where(
                        and_(
                            Order.symbol == symbol,
                            Order.status == 'filled'
                        )
                    ).order_by(Order.created_at)
                )
                orders = result.scalars().all()
                
                position = 0
                total_cost = 0
                
                for order in orders:
                    if order.side == 'buy':
                        position += order.qty
                        total_cost += order.qty * order.filled_price
                    else:
                        position -= order.qty
                        total_cost -= order.qty * order.filled_price
                
                state = self.states[symbol]
                state.current_position = position
                state.average_cost = total_cost / position if position != 0 else 0
                
        except Exception as e:
            logger.error(f"Error loading position for {symbol}: {e}")
    
    async def _update_pnl(self, symbol: str):
        """Update P&L for a symbol."""
        state = self.states[symbol]
        
        if state.current_position == 0:
            state.unrealized_pnl = 0
        else:
            current_price = state.mid_price
            state.unrealized_pnl = (current_price - state.average_cost) * state.current_position
        
        # Track daily P&L
        total_pnl = state.realized_pnl + state.unrealized_pnl
        self.daily_pnl[symbol] = total_pnl
    
    async def _check_daily_limit(self, symbol: str) -> bool:
        """Check if daily loss limit is reached."""
        config = self.configs[symbol]
        daily_pnl = self.daily_pnl.get(symbol, 0)
        
        return daily_pnl < -config.max_loss_per_day
    
    async def handle_fill(self, symbol: str, order_id: str, side: str, qty: int, price: float):
        """Handle order fill event."""
        state = self.states.get(symbol)
        if not state:
            return
        
        # Update position
        if side == 'buy':
            new_position = state.current_position + qty
            # Update average cost
            if new_position != 0:
                total_cost = (state.current_position * state.average_cost) + (qty * price)
                state.average_cost = total_cost / new_position
            state.current_position = new_position
        else:  # sell
            # Calculate realized P&L
            if state.current_position > 0:
                realized = (price - state.average_cost) * min(qty, state.current_position)
                state.realized_pnl += realized
            
            state.current_position -= qty
        
        # Update statistics
        state.trades_today += 1
        state.volume_today += qty
        
        logger.info(
            f"Fill: {side} {qty} {symbol} @ ${price:.2f}, "
            f"Position: {state.current_position}, "
            f"Realized P&L: ${state.realized_pnl:.2f}"
        )
    
    def get_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get current status of market maker."""
        if symbol:
            state = self.states.get(symbol)
            if not state:
                return {"error": f"No market maker for {symbol}"}
            
            return {
                "symbol": symbol,
                "running": symbol in self.running_tasks,
                "position": state.current_position,
                "average_cost": state.average_cost,
                "unrealized_pnl": state.unrealized_pnl,
                "realized_pnl": state.realized_pnl,
                "total_pnl": state.unrealized_pnl + state.realized_pnl,
                "bid_price": state.bid_price,
                "ask_price": state.ask_price,
                "spread_bps": state.spread_bps,
                "trades_today": state.trades_today,
                "volume_today": state.volume_today,
                "last_update": state.last_update.isoformat() if state.last_update else None
            }
        else:
            # Return status for all symbols
            return {
                symbol: self.get_status(symbol)
                for symbol in self.configs.keys()
            }