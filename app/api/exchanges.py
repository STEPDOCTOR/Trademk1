"""Exchange management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.exchanges.exchange_manager import exchange_manager, Exchange, BestQuote, UnifiedQuote
from app.services.arbitrage.arbitrage_scanner import ArbitrageScanner
from app.services.trading.execution_engine import ExecutionEngine
from app.monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/exchanges", tags=["exchanges"])


@router.get("/status")
async def get_exchange_status(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Get status of all exchanges."""
    return {
        "exchanges": {
            exchange.value: {
                "enabled": exchange_manager.active_exchanges.get(exchange, False),
                "connected": exchange in exchange_manager.active_exchanges and exchange_manager.active_exchanges[exchange],
                "supported_symbols": exchange_manager.get_supported_symbols(exchange)
            }
            for exchange in Exchange
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/enable/{exchange}")
async def enable_exchange(
    exchange: Exchange,
    enabled: bool = True,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Enable or disable an exchange."""
    try:
        exchange_manager.enable_exchange(exchange, enabled)
        
        # Initialize if enabling
        if enabled and exchange in [Exchange.COINBASE, Exchange.KRAKEN]:
            await exchange_manager.initialize()
            
        return {
            "status": "success",
            "exchange": exchange.value,
            "enabled": enabled,
            "message": f"Exchange {exchange.value} {'enabled' if enabled else 'disabled'}"
        }
        
    except Exception as e:
        logger.error(f"Error enabling exchange {exchange}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes/{symbol}")
async def get_quotes(
    symbol: str,
    exchanges: Optional[List[Exchange]] = Query(None),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get quotes from multiple exchanges."""
    try:
        if exchanges:
            # Get quotes from specific exchanges
            quotes = []
            for exchange in exchanges:
                quote = await exchange_manager.get_quote(symbol, exchange)
                if quote:
                    quotes.append(quote)
        else:
            # Get quotes from all active exchanges
            quotes = await exchange_manager.get_all_quotes(symbol)
            
        # Get best quote
        best_quote = await exchange_manager.get_best_quote(symbol)
        
        return {
            "symbol": symbol,
            "quotes": [
                {
                    "exchange": q.exchange.value,
                    "bid": q.bid,
                    "ask": q.ask,
                    "bid_size": q.bid_size,
                    "ask_size": q.ask_size,
                    "spread": q.spread,
                    "spread_pct": q.spread_pct,
                    "last_price": q.last_price,
                    "volume_24h": q.volume_24h,
                    "timestamp": q.timestamp.isoformat()
                }
                for q in quotes
            ],
            "best_quote": {
                "best_bid": best_quote.best_bid,
                "best_bid_exchange": best_quote.best_bid_exchange.value,
                "best_ask": best_quote.best_ask,
                "best_ask_exchange": best_quote.best_ask_exchange.value,
                "spread": best_quote.spread,
                "spread_pct": best_quote.spread_pct,
                "arbitrage_opportunity": best_quote.arbitrage_opportunity
            } if best_quote else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting quotes for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balances")
async def get_balances(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Get balances from all exchanges."""
    try:
        balances = await exchange_manager.get_balances()
        
        # Calculate total USD value
        total_usd = 0
        for exchange, balance in balances.items():
            total_usd += balance.get("USD", 0) + balance.get("ZUSD", 0)  # Kraken uses ZUSD
            
        return {
            "balances": {
                exchange.value: balance
                for exchange, balance in balances.items()
            },
            "total_usd_value": total_usd,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/arbitrage/scan")
async def scan_arbitrage(
    symbols: List[str],
    min_profit_pct: float = 0.001,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Scan for arbitrage opportunities."""
    try:
        # Get execution engine (needed for ArbitrageScanner)
        from app.services.trading.execution_engine import ExecutionEngine
        execution_engine = ExecutionEngine()
        
        # Create scanner
        scanner = ArbitrageScanner(execution_engine)
        scanner.min_profit_pct = min_profit_pct
        
        # Scan for opportunities
        await scanner._scan_cross_exchange(symbols)
        
        # Get opportunities
        opportunities = scanner.get_opportunities()
        
        return {
            "opportunities": [
                {
                    "type": opp.type,
                    "symbols": opp.symbols,
                    "exchanges": opp.exchanges,
                    "buy_price": opp.buy_price,
                    "sell_price": opp.sell_price,
                    "spread_pct": opp.spread_pct,
                    "estimated_profit": opp.estimated_profit,
                    "estimated_profit_pct": opp.estimated_profit_pct,
                    "trade_size": opp.trade_size,
                    "confidence": opp.confidence,
                    "time_window": opp.time_window,
                    "detected_at": opp.detected_at.isoformat()
                }
                for opp in opportunities
            ],
            "count": len(opportunities),
            "min_profit_pct": min_profit_pct,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error scanning arbitrage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order")
async def place_multi_exchange_order(
    exchange: Exchange,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: Optional[float] = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Place order on specific exchange."""
    try:
        result = await exchange_manager.place_order(
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        return {
            "status": "success",
            "exchange": exchange.value,
            "order": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order on {exchange}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-symbols/{exchange}")
async def get_supported_symbols(
    exchange: Exchange,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get supported symbols for an exchange."""
    return {
        "exchange": exchange.value,
        "symbols": exchange_manager.get_supported_symbols(exchange),
        "count": len(exchange_manager.get_supported_symbols(exchange))
    }