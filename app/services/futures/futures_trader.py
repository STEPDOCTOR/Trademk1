"""Futures trading service for advanced derivatives trading."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np

from app.monitoring.logger import get_logger
from app.services.trading.alpaca_client import get_alpaca_client
from app.db.optimized_postgres import optimized_db

logger = get_logger(__name__)


class ContractType(str, Enum):
    """Types of futures contracts."""
    INDEX = "index"  # S&P 500, Nasdaq futures
    COMMODITY = "commodity"  # Gold, Oil, etc.
    CURRENCY = "currency"  # EUR/USD futures
    CRYPTO = "crypto"  # Bitcoin futures
    BOND = "bond"  # Treasury futures


@dataclass
class FuturesContract:
    """Futures contract specification."""
    symbol: str
    underlying: str
    contract_type: ContractType
    expiration: datetime
    contract_size: float
    tick_size: float
    tick_value: float
    initial_margin: float
    maintenance_margin: float
    last_price: float
    volume: int
    open_interest: int
    
    @property
    def days_to_expiry(self) -> int:
        """Calculate days until expiration."""
        return (self.expiration - datetime.utcnow()).days
        
    @property
    def notional_value(self) -> float:
        """Calculate notional value of contract."""
        return self.last_price * self.contract_size


@dataclass
class FuturesPosition:
    """Futures position tracking."""
    contract: FuturesContract
    quantity: int  # Number of contracts (positive=long, negative=short)
    entry_price: float
    current_price: float
    initial_margin_required: float
    maintenance_margin_required: float
    unrealized_pnl: float
    realized_pnl: float
    opened_at: datetime
    
    @property
    def notional_exposure(self) -> float:
        """Calculate total notional exposure."""
        return abs(self.quantity) * self.contract.notional_value
        
    @property
    def pnl_per_contract(self) -> float:
        """Calculate P&L per contract."""
        price_change = self.current_price - self.entry_price
        return price_change * self.contract.contract_size * self.contract.tick_value / self.contract.tick_size


@dataclass
class FuturesSignal:
    """Trading signal for futures."""
    contract_symbol: str
    action: str  # "long", "short", "close"
    quantity: int
    signal_type: str  # "trend", "spread", "roll", "hedge"
    confidence: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    reason: str


class FuturesTrader:
    """Advanced futures trading service."""
    
    def __init__(self):
        self.alpaca_client = get_alpaca_client()
        self.positions: Dict[str, FuturesPosition] = {}
        self.contracts: Dict[str, FuturesContract] = {}
        self.margin_usage = 0.0
        self.max_margin_usage = 0.5  # Max 50% of account
        
        # Strategy parameters
        self.enable_spread_trading = True
        self.enable_roll_trading = True
        self.enable_basis_trading = True
        self.max_contracts_per_position = 10
        
    async def get_futures_chain(self, underlying: str) -> List[FuturesContract]:
        """Get futures chain for an underlying asset."""
        try:
            # In practice, this would connect to a futures broker API
            # For now, return mock data for demonstration
            
            if underlying == "ES":  # E-mini S&P 500
                contracts = []
                base_price = 4500  # Example S&P level
                
                for i in range(4):  # Next 4 quarterly contracts
                    expiry = datetime.utcnow() + timedelta(days=90*i + 30)
                    
                    contract = FuturesContract(
                        symbol=f"ES{expiry.strftime('%m%y')}",
                        underlying="ES",
                        contract_type=ContractType.INDEX,
                        expiration=expiry,
                        contract_size=50,  # $50 per point
                        tick_size=0.25,
                        tick_value=12.50,
                        initial_margin=12000,
                        maintenance_margin=11000,
                        last_price=base_price + i * 5,  # Contango
                        volume=100000 - i * 20000,
                        open_interest=500000 - i * 100000
                    )
                    contracts.append(contract)
                    self.contracts[contract.symbol] = contract
                    
                return contracts
                
            elif underlying == "GC":  # Gold futures
                contracts = []
                base_price = 2000  # Example gold price
                
                for i in range(6):  # Next 6 monthly contracts
                    expiry = datetime.utcnow() + timedelta(days=30*i + 15)
                    
                    contract = FuturesContract(
                        symbol=f"GC{expiry.strftime('%m%y')}",
                        underlying="GC",
                        contract_type=ContractType.COMMODITY,
                        expiration=expiry,
                        contract_size=100,  # 100 troy ounces
                        tick_size=0.10,
                        tick_value=10,
                        initial_margin=8000,
                        maintenance_margin=7200,
                        last_price=base_price + i * 2,
                        volume=50000 - i * 5000,
                        open_interest=200000 - i * 30000
                    )
                    contracts.append(contract)
                    self.contracts[contract.symbol] = contract
                    
                return contracts
                
            elif underlying == "BTC":  # Bitcoin futures
                contracts = []
                base_price = 45000  # Example BTC price
                
                for i in range(3):  # Next 3 monthly contracts
                    expiry = datetime.utcnow() + timedelta(days=30*i + 15)
                    
                    contract = FuturesContract(
                        symbol=f"BTC{expiry.strftime('%m%y')}",
                        underlying="BTC",
                        contract_type=ContractType.CRYPTO,
                        expiration=expiry,
                        contract_size=5,  # 5 Bitcoin per contract
                        tick_size=5,
                        tick_value=25,
                        initial_margin=50000,
                        maintenance_margin=45000,
                        last_price=base_price + i * 100,
                        volume=10000 - i * 2000,
                        open_interest=50000 - i * 10000
                    )
                    contracts.append(contract)
                    self.contracts[contract.symbol] = contract
                    
                return contracts
                
            return []
            
        except Exception as e:
            logger.error(f"Error getting futures chain for {underlying}: {e}")
            return []
            
    async def analyze_calendar_spread(
        self,
        near_contract: FuturesContract,
        far_contract: FuturesContract
    ) -> Optional[FuturesSignal]:
        """Analyze calendar spread opportunities."""
        try:
            # Calculate spread
            spread = far_contract.last_price - near_contract.last_price
            
            # Calculate theoretical spread based on cost of carry
            days_diff = (far_contract.expiration - near_contract.expiration).days
            risk_free_rate = 0.05  # 5% annual
            storage_cost = 0 if near_contract.contract_type != ContractType.COMMODITY else 0.02
            
            theoretical_spread = near_contract.last_price * (
                (risk_free_rate + storage_cost) * days_diff / 365
            )
            
            # Check if spread is mispriced
            spread_diff = spread - theoretical_spread
            spread_diff_pct = abs(spread_diff) / near_contract.last_price
            
            if spread_diff_pct > 0.002:  # 0.2% threshold
                if spread_diff > 0:
                    # Spread too wide - sell spread
                    return FuturesSignal(
                        contract_symbol=f"{near_contract.symbol}-{far_contract.symbol}",
                        action="short",
                        quantity=1,
                        signal_type="spread",
                        confidence=min(spread_diff_pct * 100, 0.9),
                        target_price=theoretical_spread,
                        stop_loss=spread * 1.02,
                        reason=f"Calendar spread overvalued by {spread_diff:.2f}"
                    )
                else:
                    # Spread too narrow - buy spread
                    return FuturesSignal(
                        contract_symbol=f"{near_contract.symbol}-{far_contract.symbol}",
                        action="long",
                        quantity=1,
                        signal_type="spread",
                        confidence=min(spread_diff_pct * 100, 0.9),
                        target_price=theoretical_spread,
                        stop_loss=spread * 0.98,
                        reason=f"Calendar spread undervalued by {abs(spread_diff):.2f}"
                    )
                    
        except Exception as e:
            logger.error(f"Error analyzing calendar spread: {e}")
            
        return None
        
    async def analyze_roll_opportunity(
        self,
        position: FuturesPosition
    ) -> Optional[FuturesSignal]:
        """Analyze if position should be rolled to next contract."""
        try:
            contract = position.contract
            
            # Check if approaching expiration
            if contract.days_to_expiry > 10:
                return None
                
            # Get next contract
            chain = await self.get_futures_chain(contract.underlying)
            next_contracts = [c for c in chain if c.expiration > contract.expiration]
            
            if not next_contracts:
                return None
                
            next_contract = next_contracts[0]
            
            # Calculate roll cost/benefit
            roll_spread = next_contract.last_price - contract.last_price
            roll_cost_pct = roll_spread / contract.last_price
            
            # Consider volume and open interest
            liquidity_ratio = next_contract.volume / contract.volume if contract.volume > 0 else 0
            
            if liquidity_ratio > 0.5 and contract.days_to_expiry <= 5:
                return FuturesSignal(
                    contract_symbol=next_contract.symbol,
                    action="roll",
                    quantity=position.quantity,
                    signal_type="roll",
                    confidence=0.95,
                    target_price=None,
                    stop_loss=None,
                    reason=f"Roll position from {contract.symbol} to {next_contract.symbol}, cost: {roll_cost_pct:.2%}"
                )
                
        except Exception as e:
            logger.error(f"Error analyzing roll opportunity: {e}")
            
        return None
        
    async def calculate_basis_trade(
        self,
        futures_contract: FuturesContract,
        spot_price: float
    ) -> Optional[FuturesSignal]:
        """Calculate basis trading opportunity between futures and spot."""
        try:
            # Calculate basis
            basis = futures_contract.last_price - spot_price
            basis_pct = basis / spot_price
            
            # Calculate theoretical basis (cost of carry)
            days_to_expiry = futures_contract.days_to_expiry
            risk_free_rate = 0.05
            storage_cost = 0.02 if futures_contract.contract_type == ContractType.COMMODITY else 0
            
            theoretical_basis = spot_price * (risk_free_rate + storage_cost) * days_to_expiry / 365
            theoretical_basis_pct = theoretical_basis / spot_price
            
            # Check for mispricing
            basis_diff = basis_pct - theoretical_basis_pct
            
            if abs(basis_diff) > 0.003:  # 0.3% threshold
                if basis_diff > 0:
                    # Futures expensive relative to spot
                    return FuturesSignal(
                        contract_symbol=futures_contract.symbol,
                        action="short",
                        quantity=1,
                        signal_type="basis",
                        confidence=min(abs(basis_diff) * 50, 0.9),
                        target_price=spot_price + theoretical_basis,
                        stop_loss=futures_contract.last_price * 1.005,
                        reason=f"Basis trade: futures {basis_diff:.2%} overvalued vs spot"
                    )
                else:
                    # Futures cheap relative to spot
                    return FuturesSignal(
                        contract_symbol=futures_contract.symbol,
                        action="long",
                        quantity=1,
                        signal_type="basis",
                        confidence=min(abs(basis_diff) * 50, 0.9),
                        target_price=spot_price + theoretical_basis,
                        stop_loss=futures_contract.last_price * 0.995,
                        reason=f"Basis trade: futures {abs(basis_diff):.2%} undervalued vs spot"
                    )
                    
        except Exception as e:
            logger.error(f"Error calculating basis trade: {e}")
            
        return None
        
    async def execute_futures_order(
        self,
        signal: FuturesSignal
    ) -> Dict[str, Any]:
        """Execute a futures order."""
        try:
            # In practice, this would connect to a futures broker
            # For now, simulate execution
            
            contract = self.contracts.get(signal.contract_symbol.split('-')[0])
            if not contract:
                return {"status": "error", "message": "Contract not found"}
                
            # Check margin requirements
            margin_required = abs(signal.quantity) * contract.initial_margin
            
            # Simulate execution
            execution_price = contract.last_price
            
            if signal.action in ["long", "short"]:
                # Open new position
                position = FuturesPosition(
                    contract=contract,
                    quantity=signal.quantity if signal.action == "long" else -signal.quantity,
                    entry_price=execution_price,
                    current_price=execution_price,
                    initial_margin_required=margin_required,
                    maintenance_margin_required=abs(signal.quantity) * contract.maintenance_margin,
                    unrealized_pnl=0,
                    realized_pnl=0,
                    opened_at=datetime.utcnow()
                )
                
                self.positions[contract.symbol] = position
                
                return {
                    "status": "filled",
                    "symbol": contract.symbol,
                    "action": signal.action,
                    "quantity": signal.quantity,
                    "price": execution_price,
                    "margin_used": margin_required
                }
                
            elif signal.action == "close":
                # Close existing position
                if contract.symbol in self.positions:
                    position = self.positions[contract.symbol]
                    pnl = position.pnl_per_contract * position.quantity
                    
                    del self.positions[contract.symbol]
                    
                    return {
                        "status": "closed",
                        "symbol": contract.symbol,
                        "quantity": position.quantity,
                        "entry_price": position.entry_price,
                        "exit_price": execution_price,
                        "realized_pnl": pnl
                    }
                    
            return {"status": "error", "message": "Invalid action"}
            
        except Exception as e:
            logger.error(f"Error executing futures order: {e}")
            return {"status": "error", "message": str(e)}
            
    async def update_positions(self):
        """Update all futures positions with current prices."""
        try:
            for symbol, position in self.positions.items():
                # In practice, get real-time prices
                # For now, simulate small price movements
                price_change = np.random.normal(0, position.contract.tick_size * 2)
                position.current_price = position.contract.last_price + price_change
                
                # Update P&L
                position.unrealized_pnl = position.pnl_per_contract * position.quantity
                
                # Check margin requirements
                if position.unrealized_pnl < 0:
                    equity_after_loss = position.initial_margin_required + position.unrealized_pnl
                    if equity_after_loss < position.maintenance_margin_required:
                        logger.warning(f"Margin call on {symbol}: equity {equity_after_loss} < maintenance {position.maintenance_margin_required}")
                        
        except Exception as e:
            logger.error(f"Error updating futures positions: {e}")
            
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """Get futures portfolio metrics."""
        total_margin_used = sum(p.initial_margin_required for p in self.positions.values())
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        total_notional = sum(p.notional_exposure for p in self.positions.values())
        
        position_summary = []
        for symbol, pos in self.positions.items():
            position_summary.append({
                "symbol": symbol,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "margin_used": pos.initial_margin_required,
                "days_to_expiry": pos.contract.days_to_expiry
            })
            
        return {
            "total_positions": len(self.positions),
            "total_margin_used": total_margin_used,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_notional_exposure": total_notional,
            "margin_usage_pct": self.margin_usage,
            "positions": position_summary
        }
        
    async def scan_opportunities(
        self,
        underlyings: List[str]
    ) -> List[FuturesSignal]:
        """Scan for futures trading opportunities."""
        signals = []
        
        for underlying in underlyings:
            try:
                # Get futures chain
                chain = await self.get_futures_chain(underlying)
                
                if len(chain) < 2:
                    continue
                    
                # Check calendar spreads
                if self.enable_spread_trading:
                    for i in range(len(chain) - 1):
                        spread_signal = await self.analyze_calendar_spread(chain[i], chain[i+1])
                        if spread_signal:
                            signals.append(spread_signal)
                            
                # Check basis trades (would need spot prices)
                if self.enable_basis_trading and underlying in ["GC", "BTC"]:
                    # Mock spot prices
                    spot_prices = {"GC": 1995, "BTC": 44800}
                    spot_price = spot_prices.get(underlying)
                    
                    if spot_price:
                        basis_signal = await self.calculate_basis_trade(chain[0], spot_price)
                        if basis_signal:
                            signals.append(basis_signal)
                            
            except Exception as e:
                logger.error(f"Error scanning {underlying}: {e}")
                
        # Sort by confidence
        signals.sort(key=lambda x: x.confidence, reverse=True)
        
        return signals


# Global instance
futures_trader = FuturesTrader()