"""Options trading service for advanced strategies."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm

from app.models.option import Option, OptionType, OptionPosition, OptionTrade, OptionStrategy
from app.db.optimized_postgres import optimized_db
from app.services.trading.alpaca_client import get_alpaca_client
from app.monitoring.logger import get_logger
from sqlalchemy import select, and_

logger = get_logger(__name__)


@dataclass
class OptionQuote:
    """Real-time option quote."""
    symbol: str
    strike: float
    expiry: datetime
    type: OptionType
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float
    underlying_price: float


@dataclass
class OptionGreeks:
    """Option Greeks calculations."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass
class StrategySignal:
    """Signal for option strategy execution."""
    strategy_name: str
    underlying_symbol: str
    legs: List[Dict[str, Any]]
    max_risk: float
    max_reward: float
    probability_of_profit: float
    expected_value: float
    reason: str


class OptionsTrader:
    """Advanced options trading service."""
    
    def __init__(self):
        self.alpaca_client = get_alpaca_client()
        self.risk_free_rate = 0.045  # Current treasury rate
        self.min_volume = 10  # Minimum option volume
        self.min_open_interest = 50
        self.max_spread_pct = 0.05  # 5% max bid-ask spread
        
    async def get_option_chain(self, symbol: str, expiry_days: int = 30) -> List[OptionQuote]:
        """Get option chain for a symbol."""
        try:
            # Get current stock price
            stock_quote = await self.alpaca_client.get_latest_trade(symbol)
            underlying_price = stock_quote["price"]
            
            # Calculate expiry date range
            min_expiry = datetime.now() + timedelta(days=expiry_days - 7)
            max_expiry = datetime.now() + timedelta(days=expiry_days + 7)
            
            # Get options data from Alpaca
            # Note: This is a placeholder - Alpaca's options API might differ
            options = await self.alpaca_client.get_option_contracts(
                underlying_symbols=symbol,
                expiration_date_gte=min_expiry.date(),
                expiration_date_lte=max_expiry.date()
            )
            
            option_quotes = []
            for opt in options:
                # Get option quote
                quote = await self.alpaca_client.get_option_quote(opt['symbol'])
                
                option_quotes.append(OptionQuote(
                    symbol=opt['symbol'],
                    strike=opt['strike_price'],
                    expiry=opt['expiration_date'],
                    type=OptionType.CALL if opt['type'] == 'call' else OptionType.PUT,
                    bid=quote['bid_price'],
                    ask=quote['ask_price'],
                    last=quote['last_price'],
                    volume=quote['volume'],
                    open_interest=opt['open_interest'],
                    implied_volatility=quote.get('implied_volatility', 0.3),
                    underlying_price=underlying_price
                ))
            
            return option_quotes
            
        except Exception as e:
            logger.error(f"Error getting option chain for {symbol}: {e}")
            return []
    
    def calculate_greeks(
        self,
        option_type: OptionType,
        S: float,  # Current price
        K: float,  # Strike price
        T: float,  # Time to expiry (years)
        r: float,  # Risk-free rate
        sigma: float  # Implied volatility
    ) -> OptionGreeks:
        """Calculate option Greeks using Black-Scholes."""
        # Avoid division by zero
        if T <= 0:
            T = 0.001
        if sigma <= 0:
            sigma = 0.2
            
        # Calculate d1 and d2
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == OptionType.CALL:
            delta = norm.cdf(d1)
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                    - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        else:  # PUT
            delta = norm.cdf(d1) - 1
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                    + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
        
        # Greeks that are same for calls and puts
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1% change in IV
        rho = K * T * np.exp(-r * T) * (norm.cdf(d2) if option_type == OptionType.CALL else -norm.cdf(-d2)) / 100
        
        return OptionGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho
        )
    
    def calculate_probability_of_profit(
        self,
        strategy_type: str,
        current_price: float,
        strikes: List[float],
        option_types: List[OptionType],
        positions: List[str],  # "long" or "short"
        iv: float
    ) -> float:
        """Calculate probability of profit for a strategy."""
        # Simplified probability calculation
        # In reality, this would use Monte Carlo or analytical methods
        
        if strategy_type == "long_call":
            # Probability that price > strike + premium at expiry
            breakeven = strikes[0] * 1.02  # Approximate with 2% premium
            z_score = (np.log(breakeven / current_price)) / (iv * np.sqrt(30/365))
            return 1 - norm.cdf(z_score)
            
        elif strategy_type == "short_put":
            # Probability that price > strike - premium at expiry
            breakeven = strikes[0] * 0.98  # Approximate with 2% premium
            z_score = (np.log(breakeven / current_price)) / (iv * np.sqrt(30/365))
            return norm.cdf(z_score)
            
        elif strategy_type == "call_spread":
            # Probability of max profit (price > higher strike)
            z_score = (np.log(strikes[1] / current_price)) / (iv * np.sqrt(30/365))
            prob_max_profit = 1 - norm.cdf(z_score)
            
            # Probability of any profit (price > lower strike + net debit)
            breakeven = strikes[0] * 1.01  # Approximate
            z_score_be = (np.log(breakeven / current_price)) / (iv * np.sqrt(30/365))
            prob_any_profit = 1 - norm.cdf(z_score_be)
            
            return prob_any_profit
            
        elif strategy_type == "iron_condor":
            # Probability that price stays between short strikes
            lower_short = strikes[1]
            upper_short = strikes[2]
            
            z_lower = (np.log(lower_short / current_price)) / (iv * np.sqrt(30/365))
            z_upper = (np.log(upper_short / current_price)) / (iv * np.sqrt(30/365))
            
            return norm.cdf(z_upper) - norm.cdf(z_lower)
            
        else:
            return 0.5  # Default 50%
    
    async def find_covered_call_opportunities(
        self,
        owned_symbols: List[str],
        min_premium_yield: float = 0.02  # 2% minimum
    ) -> List[StrategySignal]:
        """Find covered call opportunities on owned stocks."""
        signals = []
        
        for symbol in owned_symbols:
            try:
                # Get option chain
                options = await self.get_option_chain(symbol, expiry_days=30)
                
                if not options:
                    continue
                
                # Get current price
                current_price = options[0].underlying_price if options else 0
                if current_price <= 0:
                    continue
                
                # Filter for OTM calls with good premium
                otm_calls = [
                    opt for opt in options
                    if opt.type == OptionType.CALL
                    and opt.strike > current_price * 1.02  # At least 2% OTM
                    and opt.strike < current_price * 1.10  # Not more than 10% OTM
                    and opt.volume >= self.min_volume
                    and opt.bid > 0
                ]
                
                for call in otm_calls:
                    # Calculate premium yield
                    premium_yield = (call.bid * 100) / (current_price * 100)  # Per contract
                    
                    if premium_yield >= min_premium_yield:
                        # Calculate annualized return
                        days_to_expiry = (call.expiry - datetime.now()).days
                        annualized_return = premium_yield * (365 / days_to_expiry)
                        
                        # Calculate probability of keeping premium
                        prob_profit = self.calculate_probability_of_profit(
                            "covered_call",
                            current_price,
                            [call.strike],
                            [OptionType.CALL],
                            ["short"],
                            call.implied_volatility
                        )
                        
                        signals.append(StrategySignal(
                            strategy_name="covered_call",
                            underlying_symbol=symbol,
                            legs=[{
                                "action": "sell_to_open",
                                "option_type": "call",
                                "strike": call.strike,
                                "expiry": call.expiry,
                                "quantity": 1,
                                "premium": call.bid
                            }],
                            max_risk=0,  # Already own shares
                            max_reward=call.bid * 100,
                            probability_of_profit=prob_profit,
                            expected_value=call.bid * 100 * prob_profit,
                            reason=f"Covered call: {premium_yield:.1%} yield, {annualized_return:.1%} annualized"
                        ))
                
            except Exception as e:
                logger.error(f"Error finding covered calls for {symbol}: {e}")
                
        return sorted(signals, key=lambda x: x.expected_value, reverse=True)
    
    async def find_cash_secured_puts(
        self,
        watchlist: List[str],
        max_buying_power: float,
        min_premium_yield: float = 0.02
    ) -> List[StrategySignal]:
        """Find cash-secured put opportunities."""
        signals = []
        
        for symbol in watchlist:
            try:
                # Get option chain
                options = await self.get_option_chain(symbol, expiry_days=30)
                
                if not options:
                    continue
                
                current_price = options[0].underlying_price if options else 0
                if current_price <= 0:
                    continue
                
                # Filter for OTM puts with good premium
                otm_puts = [
                    opt for opt in options
                    if opt.type == OptionType.PUT
                    and opt.strike < current_price * 0.98  # At least 2% OTM
                    and opt.strike > current_price * 0.90  # Not more than 10% OTM
                    and opt.volume >= self.min_volume
                    and opt.bid > 0
                ]
                
                for put in otm_puts:
                    # Calculate required cash
                    cash_required = put.strike * 100
                    
                    if cash_required > max_buying_power:
                        continue
                    
                    # Calculate premium yield
                    premium_yield = (put.bid * 100) / cash_required
                    
                    if premium_yield >= min_premium_yield:
                        # Calculate probability of profit
                        prob_profit = self.calculate_probability_of_profit(
                            "short_put",
                            current_price,
                            [put.strike],
                            [OptionType.PUT],
                            ["short"],
                            put.implied_volatility
                        )
                        
                        signals.append(StrategySignal(
                            strategy_name="cash_secured_put",
                            underlying_symbol=symbol,
                            legs=[{
                                "action": "sell_to_open",
                                "option_type": "put",
                                "strike": put.strike,
                                "expiry": put.expiry,
                                "quantity": 1,
                                "premium": put.bid
                            }],
                            max_risk=cash_required - (put.bid * 100),
                            max_reward=put.bid * 100,
                            probability_of_profit=prob_profit,
                            expected_value=put.bid * 100 * prob_profit,
                            reason=f"Cash-secured put: {premium_yield:.1%} yield on {cash_required:.0f} cash"
                        ))
                
            except Exception as e:
                logger.error(f"Error finding cash-secured puts for {symbol}: {e}")
                
        return sorted(signals, key=lambda x: x.expected_value, reverse=True)
    
    async def find_vertical_spreads(
        self,
        symbol: str,
        spread_type: str = "bull_call"  # or "bear_put", "bull_put", "bear_call"
    ) -> List[StrategySignal]:
        """Find vertical spread opportunities."""
        signals = []
        
        try:
            # Get option chain
            options = await self.get_option_chain(symbol, expiry_days=30)
            
            if not options:
                return signals
            
            current_price = options[0].underlying_price
            
            # Determine option type and direction
            if spread_type in ["bull_call", "bear_call"]:
                option_type = OptionType.CALL
            else:
                option_type = OptionType.PUT
                
            # Filter relevant options
            relevant_options = [
                opt for opt in options
                if opt.type == option_type
                and opt.volume >= self.min_volume
                and opt.bid > 0
                and opt.ask > 0
            ]
            
            # Sort by strike
            relevant_options.sort(key=lambda x: x.strike)
            
            # Find spread combinations
            for i, long_option in enumerate(relevant_options[:-1]):
                for short_option in relevant_options[i+1:i+4]:  # Check next 3 strikes
                    # Calculate spread metrics
                    if spread_type == "bull_call":
                        net_debit = long_option.ask - short_option.bid
                        max_profit = (short_option.strike - long_option.strike) - net_debit
                        max_loss = net_debit
                        breakeven = long_option.strike + net_debit
                        
                    elif spread_type == "bear_put":
                        net_debit = short_option.ask - long_option.bid
                        max_profit = (short_option.strike - long_option.strike) - net_debit
                        max_loss = net_debit
                        breakeven = short_option.strike - net_debit
                        
                    else:
                        continue  # Credit spreads need different logic
                    
                    if max_profit <= 0 or max_loss <= 0:
                        continue
                    
                    # Calculate risk/reward ratio
                    risk_reward_ratio = max_profit / max_loss
                    
                    if risk_reward_ratio < 1.5:  # Minimum 1.5:1 reward/risk
                        continue
                    
                    # Calculate probability of profit
                    prob_profit = self.calculate_probability_of_profit(
                        "call_spread" if option_type == OptionType.CALL else "put_spread",
                        current_price,
                        [long_option.strike, short_option.strike],
                        [option_type, option_type],
                        ["long", "short"],
                        long_option.implied_volatility
                    )
                    
                    signals.append(StrategySignal(
                        strategy_name=spread_type,
                        underlying_symbol=symbol,
                        legs=[
                            {
                                "action": "buy_to_open",
                                "option_type": option_type.value,
                                "strike": long_option.strike,
                                "expiry": long_option.expiry,
                                "quantity": 1,
                                "price": long_option.ask
                            },
                            {
                                "action": "sell_to_open",
                                "option_type": option_type.value,
                                "strike": short_option.strike,
                                "expiry": short_option.expiry,
                                "quantity": 1,
                                "price": short_option.bid
                            }
                        ],
                        max_risk=max_loss * 100,
                        max_reward=max_profit * 100,
                        probability_of_profit=prob_profit,
                        expected_value=(max_profit * prob_profit - max_loss * (1 - prob_profit)) * 100,
                        reason=f"{spread_type}: {risk_reward_ratio:.1f}:1 R/R, {prob_profit:.0%} PoP"
                    ))
            
        except Exception as e:
            logger.error(f"Error finding vertical spreads for {symbol}: {e}")
            
        return sorted(signals, key=lambda x: x.expected_value, reverse=True)
    
    async def find_iron_condors(
        self,
        symbol: str,
        min_credit: float = 0.30,  # Minimum $0.30 credit per contract
        win_rate_target: float = 0.70  # Target 70% win rate
    ) -> List[StrategySignal]:
        """Find iron condor opportunities for neutral strategies."""
        signals = []
        
        try:
            # Get option chain
            options = await self.get_option_chain(symbol, expiry_days=45)  # Prefer 45 DTE
            
            if not options:
                return signals
            
            current_price = options[0].underlying_price
            
            # Separate calls and puts
            calls = sorted([opt for opt in options if opt.type == OptionType.CALL], key=lambda x: x.strike)
            puts = sorted([opt for opt in options if opt.type == OptionType.PUT], key=lambda x: x.strike)
            
            # Find suitable strikes (roughly 15-20 delta)
            # Simplified - in practice would calculate actual delta
            short_put_strike = current_price * 0.90  # ~10% below
            long_put_strike = current_price * 0.85   # ~15% below
            short_call_strike = current_price * 1.10  # ~10% above
            long_call_strike = current_price * 1.15   # ~15% above
            
            # Find closest actual strikes
            short_put = min(puts, key=lambda x: abs(x.strike - short_put_strike))
            long_put = min(puts, key=lambda x: abs(x.strike - long_put_strike))
            short_call = min(calls, key=lambda x: abs(x.strike - short_call_strike))
            long_call = min(calls, key=lambda x: abs(x.strike - long_call_strike))
            
            # Calculate net credit
            net_credit = (
                short_put.bid + short_call.bid -
                long_put.ask - long_call.ask
            )
            
            if net_credit >= min_credit:
                # Calculate max loss (width of wider spread - credit)
                put_spread_width = short_put.strike - long_put.strike
                call_spread_width = long_call.strike - short_call.strike
                max_loss = max(put_spread_width, call_spread_width) - net_credit
                
                # Calculate probability of profit
                prob_profit = self.calculate_probability_of_profit(
                    "iron_condor",
                    current_price,
                    [long_put.strike, short_put.strike, short_call.strike, long_call.strike],
                    [OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL],
                    ["long", "short", "short", "long"],
                    short_put.implied_volatility
                )
                
                if prob_profit >= win_rate_target:
                    signals.append(StrategySignal(
                        strategy_name="iron_condor",
                        underlying_symbol=symbol,
                        legs=[
                            {
                                "action": "sell_to_open",
                                "option_type": "put",
                                "strike": short_put.strike,
                                "expiry": short_put.expiry,
                                "quantity": 1
                            },
                            {
                                "action": "buy_to_open",
                                "option_type": "put",
                                "strike": long_put.strike,
                                "expiry": long_put.expiry,
                                "quantity": 1
                            },
                            {
                                "action": "sell_to_open",
                                "option_type": "call",
                                "strike": short_call.strike,
                                "expiry": short_call.expiry,
                                "quantity": 1
                            },
                            {
                                "action": "buy_to_open",
                                "option_type": "call",
                                "strike": long_call.strike,
                                "expiry": long_call.expiry,
                                "quantity": 1
                            }
                        ],
                        max_risk=max_loss * 100,
                        max_reward=net_credit * 100,
                        probability_of_profit=prob_profit,
                        expected_value=(net_credit * prob_profit - max_loss * (1 - prob_profit)) * 100,
                        reason=f"Iron Condor: ${net_credit:.2f} credit, {prob_profit:.0%} PoP"
                    ))
            
        except Exception as e:
            logger.error(f"Error finding iron condors for {symbol}: {e}")
            
        return signals
    
    async def execute_option_strategy(self, signal: StrategySignal) -> Dict[str, Any]:
        """Execute an option strategy."""
        try:
            order_ids = []
            
            for leg in signal.legs:
                # Create order based on leg configuration
                if leg['action'] in ['buy_to_open', 'buy_to_close']:
                    side = 'buy'
                else:
                    side = 'sell'
                
                # Submit option order
                order = await self.alpaca_client.submit_option_order(
                    symbol=leg.get('option_symbol'),  # Full OCC symbol
                    qty=leg['quantity'],
                    side=side,
                    order_type='limit',
                    limit_price=leg.get('price', 0),
                    time_in_force='day'
                )
                
                order_ids.append(order['id'])
                
                # Store in database
                async with optimized_db.get_session() as db:
                    # Create option record if not exists
                    # Create position record
                    # Create trade record
                    pass
            
            return {
                "status": "submitted",
                "strategy": signal.strategy_name,
                "symbol": signal.underlying_symbol,
                "order_ids": order_ids,
                "max_risk": signal.max_risk,
                "max_reward": signal.max_reward
            }
            
        except Exception as e:
            logger.error(f"Error executing option strategy: {e}")
            return {"status": "error", "message": str(e)}


# Global instance
options_trader = OptionsTrader()