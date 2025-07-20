"""Market sentiment API endpoints."""
from typing import Dict, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, AuthUser
from app.services.market_sentiment import market_sentiment_service, MarketSentiment, SectorSentiment
from app.monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/market-sentiment", tags=["market-sentiment"])


class MarketSentimentResponse(BaseModel):
    """Response model for market sentiment."""
    overall_sentiment: str
    fear_greed_index: float
    recommendation: str
    risk_level: str
    
    # Key indicators
    advance_decline_ratio: float
    volume_ratio: float
    market_volatility: float
    breadth_percentage: float
    
    # Scores
    momentum_score: float
    volume_score: float
    volatility_score: float
    breadth_score: float
    
    # Trading conditions
    should_trade_aggressively: bool
    trading_note: str


class SectorAnalysisResponse(BaseModel):
    """Response model for sector analysis."""
    sector: str
    sentiment: str
    performance: float
    relative_strength: float
    top_symbol: str
    worst_symbol: str


@router.get("/current")
async def get_current_sentiment(
    current_user: AuthUser = Depends(get_current_user)
) -> MarketSentimentResponse:
    """Get current market sentiment analysis."""
    analysis = await market_sentiment_service.get_market_analysis()
    should_trade, note = await market_sentiment_service.should_trade_aggressively()
    
    return MarketSentimentResponse(
        overall_sentiment=analysis.overall_sentiment.value,
        fear_greed_index=analysis.fear_greed_index,
        recommendation=analysis.trading_recommendation,
        risk_level=analysis.risk_level,
        advance_decline_ratio=analysis.indicators.advance_decline_ratio,
        volume_ratio=analysis.indicators.volume_ratio,
        market_volatility=analysis.indicators.market_volatility,
        breadth_percentage=analysis.indicators.ma_breadth * 100,
        momentum_score=analysis.indicators.momentum_score,
        volume_score=analysis.indicators.volume_score,
        volatility_score=analysis.indicators.volatility_score,
        breadth_score=analysis.indicators.breadth_score,
        should_trade_aggressively=should_trade,
        trading_note=note
    )


@router.get("/fear-greed")
async def get_fear_greed_index(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get Fear & Greed Index details."""
    analysis = await market_sentiment_service.get_market_analysis()
    
    return {
        "index": analysis.fear_greed_index,
        "sentiment": analysis.overall_sentiment.value,
        "components": {
            "momentum": {
                "score": analysis.indicators.momentum_score,
                "weight": 0.25
            },
            "volume": {
                "score": analysis.indicators.volume_score,
                "weight": 0.15
            },
            "volatility": {
                "score": analysis.indicators.volatility_score,
                "weight": 0.20
            },
            "breadth": {
                "score": analysis.indicators.breadth_score,
                "weight": 0.25
            },
            "high_low": {
                "score": analysis.indicators.high_low_score,
                "weight": 0.15
            }
        },
        "interpretation": {
            "0-20": "Extreme Fear",
            "20-40": "Fear",
            "40-60": "Neutral",
            "60-80": "Greed",
            "80-100": "Extreme Greed"
        }
    }


@router.get("/sectors")
async def get_sector_analysis(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get sector rotation analysis."""
    analysis = await market_sentiment_service.get_market_analysis()
    
    sectors = []
    for sector_analysis in analysis.sector_analysis:
        sectors.append(SectorAnalysisResponse(
            sector=sector_analysis.sector.value,
            sentiment=sector_analysis.sector_sentiment.value,
            performance=sector_analysis.avg_performance * 100,  # Convert to percentage
            relative_strength=sector_analysis.relative_strength * 100,
            top_symbol=sector_analysis.top_performers[0][0] if sector_analysis.top_performers else "",
            worst_symbol=sector_analysis.worst_performers[0][0] if sector_analysis.worst_performers else ""
        ))
    
    # Sort by performance
    sectors.sort(key=lambda x: x.performance, reverse=True)
    
    return {
        "market_sentiment": analysis.overall_sentiment.value,
        "sectors": sectors,
        "strongest_sector": sectors[0].sector if sectors else None,
        "weakest_sector": sectors[-1].sector if sectors else None,
        "rotation_signal": "Risk-on" if analysis.fear_greed_index > 60 else "Risk-off"
    }


@router.get("/market-breadth")
async def get_market_breadth(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get detailed market breadth analysis."""
    analysis = await market_sentiment_service.get_market_analysis()
    indicators = analysis.indicators
    
    return {
        "advances": indicators.advances,
        "declines": indicators.declines,
        "unchanged": indicators.unchanged,
        "advance_decline_ratio": indicators.advance_decline_ratio,
        "advance_decline_line": indicators.advances - indicators.declines,
        "breadth_thrust": indicators.advances / (indicators.advances + indicators.declines) if (indicators.advances + indicators.declines) > 0 else 0.5,
        "new_highs": indicators.new_highs,
        "new_lows": indicators.new_lows,
        "high_low_ratio": indicators.high_low_ratio,
        "above_50_ma": indicators.above_50_ma,
        "below_50_ma": indicators.below_50_ma,
        "ma_breadth_percentage": indicators.ma_breadth * 100,
        "market_health": "Healthy" if indicators.advance_decline_ratio > 1.5 and indicators.ma_breadth > 0.6 else "Weak"
    }


@router.get("/key-levels")
async def get_key_market_levels(
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get key support and resistance levels for major indices."""
    analysis = await market_sentiment_service.get_market_analysis()
    
    return {
        "levels": analysis.key_levels,
        "market_position": {
            "SPY": "Above pivot" if analysis.key_levels.get("SPY_current", 0) > analysis.key_levels.get("SPY_pivot", 0) else "Below pivot",
            "QQQ": "Near resistance" if abs(analysis.key_levels.get("QQQ_current", 0) - analysis.key_levels.get("QQQ_resistance", 0)) < 1 else "Normal"
        },
        "trend": "Bullish" if analysis.overall_sentiment in [MarketSentiment.BULLISH, MarketSentiment.VERY_BULLISH] else "Bearish"
    }


@router.get("/trading-conditions")
async def get_trading_conditions(
    risk_tolerance: str = Query("medium", description="Risk tolerance: low, medium, high"),
    current_user: AuthUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get personalized trading conditions based on market sentiment."""
    analysis = await market_sentiment_service.get_market_analysis()
    should_trade, reason = await market_sentiment_service.should_trade_aggressively()
    
    # Adjust recommendations based on risk tolerance
    if risk_tolerance == "low":
        position_size_multiplier = 0.5 if analysis.risk_level in ["high", "extreme"] else 0.8
        max_positions = 10
    elif risk_tolerance == "high":
        position_size_multiplier = 1.2 if analysis.overall_sentiment == MarketSentiment.VERY_BULLISH else 1.0
        max_positions = 30
    else:  # medium
        position_size_multiplier = 1.0
        max_positions = 20
    
    # Adjust for market conditions
    if analysis.risk_level == "extreme":
        position_size_multiplier *= 0.5
        max_positions = int(max_positions * 0.5)
    
    return {
        "market_conditions": {
            "sentiment": analysis.overall_sentiment.value,
            "risk_level": analysis.risk_level,
            "volatility": analysis.indicators.market_volatility,
            "fear_greed_index": analysis.fear_greed_index
        },
        "recommendations": {
            "should_trade": should_trade,
            "reason": reason,
            "position_size_adjustment": position_size_multiplier,
            "max_positions": max_positions,
            "preferred_sectors": [s.sector.value for s in analysis.sector_analysis[:3] if s.avg_performance > 0],
            "avoid_sectors": [s.sector.value for s in analysis.sector_analysis if s.avg_performance < -0.01]
        },
        "risk_management": {
            "suggested_stop_loss": 0.03 if analysis.indicators.market_volatility > 0.02 else 0.02,
            "suggested_take_profit": 0.08 if analysis.overall_sentiment == MarketSentiment.VERY_BULLISH else 0.05,
            "use_trailing_stops": True,
            "trail_percentage": 0.03 if analysis.indicators.market_volatility > 0.02 else 0.02
        }
    }