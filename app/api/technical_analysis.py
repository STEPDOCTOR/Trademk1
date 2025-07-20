"""Technical analysis API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, AuthUser
from app.services.technical_indicators import technical_indicators, TechnicalSignals
from app.monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/technical", tags=["technical-analysis"])


class TechnicalSignalsResponse(BaseModel):
    """Response model for technical signals."""
    symbol: str
    current_price: float
    price_change_pct: float
    rsi: float
    rsi_signal: str
    macd: float
    macd_signal: float
    macd_cross: str
    volume_ratio: float
    volume_trend: str
    bb_position: str
    overall_signal: str
    confidence: float
    
    @classmethod
    def from_signals(cls, signals: TechnicalSignals) -> "TechnicalSignalsResponse":
        """Create response from technical signals."""
        return cls(
            symbol=signals.symbol,
            current_price=signals.current_price,
            price_change_pct=signals.price_change_pct,
            rsi=signals.rsi,
            rsi_signal=signals.rsi_signal,
            macd=signals.macd,
            macd_signal=signals.macd_signal,
            macd_cross=signals.macd_cross,
            volume_ratio=signals.volume_ratio,
            volume_trend=signals.volume_trend,
            bb_position=signals.bb_position,
            overall_signal=signals.overall_signal,
            confidence=signals.confidence
        )


@router.get("/signals/{symbol}")
async def get_technical_signals(
    symbol: str,
    current_user: AuthUser = Depends(get_current_user)
) -> TechnicalSignalsResponse:
    """Get technical analysis signals for a symbol."""
    signals = await technical_indicators.get_technical_signals(symbol.upper())
    
    if not signals:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to calculate technical signals for {symbol}"
        )
    
    return TechnicalSignalsResponse.from_signals(signals)


@router.get("/scan")
async def scan_for_opportunities(
    limit: int = Query(10, ge=1, le=50),
    min_confidence: float = Query(0.6, ge=0, le=1),
    current_user: AuthUser = Depends(get_current_user)
) -> List[TechnicalSignalsResponse]:
    """Scan all active symbols for trading opportunities."""
    # Get all active symbols
    from app.db.optimized_postgres import optimized_db
    from app.models.symbol import Symbol
    from sqlalchemy import select
    
    async with optimized_db.get_session() as db:
        result = await db.execute(
            select(Symbol).where(Symbol.is_active == True)
        )
        symbols = [sym.ticker for sym in result.scalars().all()]
    
    # Scan for opportunities
    opportunities = await technical_indicators.scan_for_opportunities(symbols)
    
    # Filter by confidence and limit
    filtered = [
        TechnicalSignalsResponse.from_signals(opp)
        for opp in opportunities
        if opp.confidence >= min_confidence
    ][:limit]
    
    return filtered


@router.get("/indicators/{symbol}/rsi")
async def get_rsi(
    symbol: str,
    period: int = Query(14, ge=2, le=50),
    current_user: AuthUser = Depends(get_current_user)
) -> dict:
    """Get RSI indicator for a symbol."""
    signals = await technical_indicators.get_technical_signals(symbol.upper())
    
    if not signals:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to calculate RSI for {symbol}"
        )
    
    return {
        "symbol": symbol,
        "rsi": signals.rsi,
        "signal": signals.rsi_signal,
        "overbought": signals.rsi > 70,
        "oversold": signals.rsi < 30
    }


@router.get("/indicators/{symbol}/macd")
async def get_macd(
    symbol: str,
    current_user: AuthUser = Depends(get_current_user)
) -> dict:
    """Get MACD indicator for a symbol."""
    signals = await technical_indicators.get_technical_signals(symbol.upper())
    
    if not signals:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to calculate MACD for {symbol}"
        )
    
    return {
        "symbol": symbol,
        "macd": signals.macd,
        "signal": signals.macd_signal,
        "histogram": signals.macd_histogram,
        "crossover": signals.macd_cross
    }


@router.get("/indicators/{symbol}/bollinger")
async def get_bollinger_bands(
    symbol: str,
    current_user: AuthUser = Depends(get_current_user)
) -> dict:
    """Get Bollinger Bands for a symbol."""
    signals = await technical_indicators.get_technical_signals(symbol.upper())
    
    if not signals:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to calculate Bollinger Bands for {symbol}"
        )
    
    return {
        "symbol": symbol,
        "current_price": signals.current_price,
        "upper_band": signals.bb_upper,
        "middle_band": signals.bb_middle,
        "lower_band": signals.bb_lower,
        "position": signals.bb_position,
        "band_width": signals.bb_upper - signals.bb_lower,
        "percent_b": (signals.current_price - signals.bb_lower) / (signals.bb_upper - signals.bb_lower) if signals.bb_upper != signals.bb_lower else 0.5
    }