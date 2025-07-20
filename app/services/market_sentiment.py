"""Market sentiment analysis service for gauging overall market conditions."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

from app.db.questdb import get_questdb_pool
from app.db.optimized_postgres import optimized_db
from app.models.symbol import Symbol
from app.services.technical_indicators import technical_indicators
from app.monitoring.logger import get_logger
from sqlalchemy import select

logger = get_logger(__name__)


class MarketSentiment(str, Enum):
    """Overall market sentiment levels."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class SectorSentiment(str, Enum):
    """Sector categories for analysis."""
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    HEALTHCARE = "healthcare"
    CONSUMER = "consumer"
    ENERGY = "energy"
    CRYPTO = "crypto"
    BROAD_MARKET = "broad_market"


@dataclass
class SentimentIndicators:
    """Container for various sentiment indicators."""
    # Market breadth
    advances: int
    declines: int
    unchanged: int
    advance_decline_ratio: float
    
    # Price momentum
    new_highs: int
    new_lows: int
    high_low_ratio: float
    
    # Volume analysis
    up_volume: float
    down_volume: float
    volume_ratio: float
    
    # Volatility
    market_volatility: float
    vix_level: Optional[float] = None
    
    # Technical
    above_50_ma: int
    below_50_ma: int
    ma_breadth: float
    
    # Fear & Greed components
    momentum_score: float  # 0-100
    volume_score: float    # 0-100
    volatility_score: float  # 0-100
    breadth_score: float   # 0-100
    high_low_score: float  # 0-100
    
    # Overall scores
    fear_greed_index: float  # 0-100
    sentiment: MarketSentiment
    confidence: float  # 0-1


@dataclass
class SectorAnalysis:
    """Analysis of a specific sector."""
    sector: SectorSentiment
    symbols: List[str]
    avg_performance: float
    top_performers: List[Tuple[str, float]]
    worst_performers: List[Tuple[str, float]]
    sector_sentiment: MarketSentiment
    relative_strength: float  # vs market


@dataclass
class MarketAnalysis:
    """Complete market analysis."""
    timestamp: datetime
    overall_sentiment: MarketSentiment
    fear_greed_index: float
    indicators: SentimentIndicators
    sector_analysis: List[SectorAnalysis]
    trading_recommendation: str
    risk_level: str  # "low", "medium", "high", "extreme"
    key_levels: Dict[str, float]  # Support/resistance for major indices


class MarketSentimentService:
    """Service for analyzing overall market sentiment and conditions."""
    
    def __init__(self):
        self.sector_mappings = {
            SectorSentiment.TECHNOLOGY: ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC"],
            SectorSentiment.FINANCE: ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA"],
            SectorSentiment.HEALTHCARE: ["JNJ", "UNH", "PFE", "ABBV", "TMO", "CVS", "ABT"],
            SectorSentiment.CONSUMER: ["AMZN", "HD", "WMT", "NKE", "MCD", "SBUX", "TGT"],
            SectorSentiment.ENERGY: ["XOM", "CVX", "COP", "SLB", "EOG", "PXD", "VLO"],
            SectorSentiment.CRYPTO: ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "XRPUSD"],
            SectorSentiment.BROAD_MARKET: ["SPY", "QQQ", "DIA", "IWM", "VTI"]
        }
        self.cache_ttl = 300  # 5 minutes
        self._cache: Optional[MarketAnalysis] = None
        self._cache_time: Optional[datetime] = None
    
    async def get_market_analysis(self, force_refresh: bool = False) -> MarketAnalysis:
        """Get comprehensive market analysis."""
        # Check cache
        if not force_refresh and self._cache and self._cache_time:
            if (datetime.utcnow() - self._cache_time).total_seconds() < self.cache_ttl:
                return self._cache
        
        try:
            # Get all active symbols
            async with optimized_db.get_session() as db:
                result = await db.execute(
                    select(Symbol).where(Symbol.is_active == True)
                )
                all_symbols = [sym.ticker for sym in result.scalars().all()]
            
            # Calculate market indicators
            indicators = await self._calculate_market_indicators(all_symbols)
            
            # Analyze sectors
            sector_analyses = await self._analyze_sectors()
            
            # Determine overall sentiment
            overall_sentiment = self._determine_sentiment(indicators.fear_greed_index)
            
            # Generate trading recommendation
            recommendation = self._generate_recommendation(
                overall_sentiment, indicators, sector_analyses
            )
            
            # Determine risk level
            risk_level = self._assess_risk_level(indicators)
            
            # Get key market levels
            key_levels = await self._get_key_levels()
            
            # Create analysis
            analysis = MarketAnalysis(
                timestamp=datetime.utcnow(),
                overall_sentiment=overall_sentiment,
                fear_greed_index=indicators.fear_greed_index,
                indicators=indicators,
                sector_analysis=sector_analyses,
                trading_recommendation=recommendation,
                risk_level=risk_level,
                key_levels=key_levels
            )
            
            # Cache result
            self._cache = analysis
            self._cache_time = datetime.utcnow()
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error generating market analysis: {e}")
            # Return neutral analysis on error
            return self._generate_default_analysis()
    
    async def _calculate_market_indicators(self, symbols: List[str]) -> SentimentIndicators:
        """Calculate various market breadth and sentiment indicators."""
        # Get price data for all symbols
        price_changes = {}
        volumes = {}
        above_ma = 0
        below_ma = 0
        
        for symbol in symbols[:50]:  # Limit for performance
            try:
                # Get 24h price change
                prices = await self._get_price_history(symbol, hours=24)
                if len(prices) >= 2:
                    change = (prices[-1] - prices[0]) / prices[0]
                    price_changes[symbol] = change
                    
                    # Get volume
                    vol = await self._get_volume(symbol)
                    if vol:
                        volumes[symbol] = vol
                    
                    # Check if above 50-period MA
                    if len(prices) >= 50:
                        ma50 = np.mean(prices[-50:])
                        if prices[-1] > ma50:
                            above_ma += 1
                        else:
                            below_ma += 1
                            
            except Exception as e:
                logger.debug(f"Error processing {symbol}: {e}")
                continue
        
        # Calculate breadth indicators
        advances = sum(1 for c in price_changes.values() if c > 0)
        declines = sum(1 for c in price_changes.values() if c < 0)
        unchanged = len(price_changes) - advances - declines
        advance_decline_ratio = advances / declines if declines > 0 else advances
        
        # Calculate volume metrics
        up_volume = sum(volumes.get(s, 0) for s, c in price_changes.items() if c > 0)
        down_volume = sum(volumes.get(s, 0) for s, c in price_changes.items() if c <= 0)
        volume_ratio = up_volume / down_volume if down_volume > 0 else 1.0
        
        # Calculate new highs/lows (simplified - based on 20-day range)
        new_highs = sum(1 for s, c in price_changes.items() if c > 0.05)  # 5% up
        new_lows = sum(1 for s, c in price_changes.items() if c < -0.05)  # 5% down
        high_low_ratio = new_highs / new_lows if new_lows > 0 else new_highs
        
        # Calculate volatility (average absolute price change)
        volatility = np.mean([abs(c) for c in price_changes.values()]) if price_changes else 0.02
        
        # MA breadth
        total_ma_checked = above_ma + below_ma
        ma_breadth = (above_ma / total_ma_checked) if total_ma_checked > 0 else 0.5
        
        # Calculate Fear & Greed components (0-100 scale)
        # Momentum score
        avg_change = np.mean(list(price_changes.values())) if price_changes else 0
        momentum_score = self._normalize_score(avg_change, -0.02, 0.02) * 100
        
        # Volume score (higher up volume = more greed)
        volume_score = self._normalize_score(volume_ratio, 0.5, 2.0) * 100
        
        # Volatility score (lower volatility = more greed)
        volatility_score = (1 - self._normalize_score(volatility, 0.01, 0.05)) * 100
        
        # Breadth score
        breadth_score = self._normalize_score(advance_decline_ratio, 0.5, 2.0) * 100
        
        # High/Low score
        high_low_score = self._normalize_score(high_low_ratio, 0.5, 2.0) * 100
        
        # Calculate Fear & Greed Index (weighted average)
        fear_greed_index = (
            momentum_score * 0.25 +
            volume_score * 0.15 +
            volatility_score * 0.20 +
            breadth_score * 0.25 +
            high_low_score * 0.15
        )
        
        # Determine sentiment
        sentiment = self._determine_sentiment(fear_greed_index)
        
        # Confidence based on data quality
        confidence = min(len(price_changes) / 50, 1.0)
        
        return SentimentIndicators(
            advances=advances,
            declines=declines,
            unchanged=unchanged,
            advance_decline_ratio=advance_decline_ratio,
            new_highs=new_highs,
            new_lows=new_lows,
            high_low_ratio=high_low_ratio,
            up_volume=up_volume,
            down_volume=down_volume,
            volume_ratio=volume_ratio,
            market_volatility=volatility,
            above_50_ma=above_ma,
            below_50_ma=below_ma,
            ma_breadth=ma_breadth,
            momentum_score=momentum_score,
            volume_score=volume_score,
            volatility_score=volatility_score,
            breadth_score=breadth_score,
            high_low_score=high_low_score,
            fear_greed_index=fear_greed_index,
            sentiment=sentiment,
            confidence=confidence
        )
    
    async def _analyze_sectors(self) -> List[SectorAnalysis]:
        """Analyze each sector's performance and sentiment."""
        sector_analyses = []
        
        # Get broad market performance for comparison
        market_perf = await self._get_symbol_performance("SPY", hours=24)
        
        for sector, symbols in self.sector_mappings.items():
            try:
                performances = []
                
                for symbol in symbols:
                    perf = await self._get_symbol_performance(symbol, hours=24)
                    if perf is not None:
                        performances.append((symbol, perf))
                
                if not performances:
                    continue
                
                # Calculate sector metrics
                avg_performance = np.mean([p[1] for p in performances])
                
                # Sort for top/worst
                performances.sort(key=lambda x: x[1], reverse=True)
                top_performers = performances[:3]
                worst_performers = performances[-3:]
                
                # Relative strength vs market
                relative_strength = avg_performance - market_perf if market_perf else avg_performance
                
                # Determine sector sentiment
                if avg_performance > 0.02:
                    sector_sentiment = MarketSentiment.VERY_BULLISH
                elif avg_performance > 0.005:
                    sector_sentiment = MarketSentiment.BULLISH
                elif avg_performance < -0.02:
                    sector_sentiment = MarketSentiment.VERY_BEARISH
                elif avg_performance < -0.005:
                    sector_sentiment = MarketSentiment.BEARISH
                else:
                    sector_sentiment = MarketSentiment.NEUTRAL
                
                sector_analyses.append(SectorAnalysis(
                    sector=sector,
                    symbols=symbols,
                    avg_performance=avg_performance,
                    top_performers=top_performers,
                    worst_performers=worst_performers,
                    sector_sentiment=sector_sentiment,
                    relative_strength=relative_strength
                ))
                
            except Exception as e:
                logger.error(f"Error analyzing sector {sector}: {e}")
                continue
        
        # Sort by performance
        sector_analyses.sort(key=lambda x: x.avg_performance, reverse=True)
        
        return sector_analyses
    
    async def _get_price_history(self, symbol: str, hours: int = 24) -> List[float]:
        """Get price history for a symbol."""
        try:
            query = f"""
            SELECT price
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > dateadd('h', -{hours}, now())
            ORDER BY timestamp ASC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                return [row['price'] for row in result]
                
        except Exception as e:
            logger.debug(f"Error getting price history for {symbol}: {e}")
            return []
    
    async def _get_volume(self, symbol: str) -> Optional[float]:
        """Get recent volume for a symbol."""
        try:
            query = f"""
            SELECT avg(volume) as avg_volume
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > dateadd('h', -1, now())
            AND volume IS NOT NULL
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetchrow(query)
                return result['avg_volume'] if result and result['avg_volume'] else None
                
        except Exception as e:
            logger.debug(f"Error getting volume for {symbol}: {e}")
            return None
    
    async def _get_symbol_performance(self, symbol: str, hours: int = 24) -> Optional[float]:
        """Get performance percentage for a symbol."""
        prices = await self._get_price_history(symbol, hours)
        if len(prices) >= 2:
            return (prices[-1] - prices[0]) / prices[0]
        return None
    
    async def _get_key_levels(self) -> Dict[str, float]:
        """Get key support/resistance levels for major indices."""
        levels = {}
        
        # Get SPY levels (S&P 500)
        spy_prices = await self._get_price_history("SPY", hours=24*5)  # 5 days
        if spy_prices:
            levels["SPY_current"] = spy_prices[-1]
            levels["SPY_resistance"] = max(spy_prices)
            levels["SPY_support"] = min(spy_prices)
            levels["SPY_pivot"] = (levels["SPY_resistance"] + levels["SPY_support"] + spy_prices[-1]) / 3
        
        # Get QQQ levels (NASDAQ)
        qqq_prices = await self._get_price_history("QQQ", hours=24*5)
        if qqq_prices:
            levels["QQQ_current"] = qqq_prices[-1]
            levels["QQQ_resistance"] = max(qqq_prices)
            levels["QQQ_support"] = min(qqq_prices)
        
        return levels
    
    def _normalize_score(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize a value to 0-1 range."""
        if value <= min_val:
            return 0.0
        elif value >= max_val:
            return 1.0
        else:
            return (value - min_val) / (max_val - min_val)
    
    def _determine_sentiment(self, fear_greed_index: float) -> MarketSentiment:
        """Determine market sentiment from Fear & Greed Index."""
        if fear_greed_index >= 80:
            return MarketSentiment.VERY_BULLISH
        elif fear_greed_index >= 60:
            return MarketSentiment.BULLISH
        elif fear_greed_index >= 40:
            return MarketSentiment.NEUTRAL
        elif fear_greed_index >= 20:
            return MarketSentiment.BEARISH
        else:
            return MarketSentiment.VERY_BEARISH
    
    def _assess_risk_level(self, indicators: SentimentIndicators) -> str:
        """Assess current market risk level."""
        risk_score = 0
        
        # High volatility increases risk
        if indicators.market_volatility > 0.03:
            risk_score += 2
        elif indicators.market_volatility > 0.02:
            risk_score += 1
        
        # Extreme sentiment increases risk
        if indicators.fear_greed_index > 85 or indicators.fear_greed_index < 15:
            risk_score += 2
        elif indicators.fear_greed_index > 75 or indicators.fear_greed_index < 25:
            risk_score += 1
        
        # Poor breadth increases risk
        if indicators.advance_decline_ratio < 0.5 or indicators.advance_decline_ratio > 2:
            risk_score += 1
        
        # Many new lows increase risk
        if indicators.new_lows > indicators.new_highs * 2:
            risk_score += 1
        
        if risk_score >= 4:
            return "extreme"
        elif risk_score >= 3:
            return "high"
        elif risk_score >= 1:
            return "medium"
        else:
            return "low"
    
    def _generate_recommendation(
        self,
        sentiment: MarketSentiment,
        indicators: SentimentIndicators,
        sectors: List[SectorAnalysis]
    ) -> str:
        """Generate trading recommendation based on analysis."""
        # Find strongest sectors
        strong_sectors = [s for s in sectors if s.sector_sentiment in [MarketSentiment.BULLISH, MarketSentiment.VERY_BULLISH]]
        weak_sectors = [s for s in sectors if s.sector_sentiment in [MarketSentiment.BEARISH, MarketSentiment.VERY_BEARISH]]
        
        if sentiment == MarketSentiment.VERY_BULLISH:
            rec = "Strong buying opportunity. Market showing extreme optimism. "
            if indicators.fear_greed_index > 85:
                rec += "However, be cautious of potential overbought conditions. Consider taking some profits. "
            if strong_sectors:
                rec += f"Focus on: {', '.join(s.sector.value for s in strong_sectors[:2])}."
                
        elif sentiment == MarketSentiment.BULLISH:
            rec = "Favorable conditions for buying. Market momentum is positive. "
            if strong_sectors:
                rec += f"Best opportunities in: {', '.join(s.sector.value for s in strong_sectors[:2])}."
                
        elif sentiment == MarketSentiment.NEUTRAL:
            rec = "Mixed market conditions. Be selective with entries. "
            if strong_sectors and weak_sectors:
                rec += f"Consider long positions in {strong_sectors[0].sector.value}, avoid {weak_sectors[0].sector.value}."
            else:
                rec += "Wait for clearer signals or trade with smaller position sizes."
                
        elif sentiment == MarketSentiment.BEARISH:
            rec = "Cautious market environment. Reduce position sizes and tighten stops. "
            if weak_sectors:
                rec += f"Avoid or consider shorting: {', '.join(s.sector.value for s in weak_sectors[:2])}."
                
        else:  # VERY_BEARISH
            rec = "High-risk environment. Consider cash positions or defensive strategies. "
            if indicators.fear_greed_index < 15:
                rec += "Extreme fear may present contrarian buying opportunities for patient investors. "
            rec += "Focus on capital preservation."
        
        # Add volatility warning
        if indicators.market_volatility > 0.03:
            rec += " ⚠️ High volatility detected - use wider stops."
        
        return rec
    
    def _generate_default_analysis(self) -> MarketAnalysis:
        """Generate default neutral analysis when real data unavailable."""
        default_indicators = SentimentIndicators(
            advances=50,
            declines=50,
            unchanged=0,
            advance_decline_ratio=1.0,
            new_highs=10,
            new_lows=10,
            high_low_ratio=1.0,
            up_volume=1000000,
            down_volume=1000000,
            volume_ratio=1.0,
            market_volatility=0.02,
            above_50_ma=50,
            below_50_ma=50,
            ma_breadth=0.5,
            momentum_score=50,
            volume_score=50,
            volatility_score=50,
            breadth_score=50,
            high_low_score=50,
            fear_greed_index=50,
            sentiment=MarketSentiment.NEUTRAL,
            confidence=0.5
        )
        
        return MarketAnalysis(
            timestamp=datetime.utcnow(),
            overall_sentiment=MarketSentiment.NEUTRAL,
            fear_greed_index=50,
            indicators=default_indicators,
            sector_analysis=[],
            trading_recommendation="Market data temporarily unavailable. Trade with caution.",
            risk_level="medium",
            key_levels={}
        )
    
    async def should_trade_aggressively(self) -> Tuple[bool, str]:
        """Determine if market conditions favor aggressive trading."""
        analysis = await self.get_market_analysis()
        
        # Favorable conditions for aggressive trading
        if analysis.overall_sentiment in [MarketSentiment.BULLISH, MarketSentiment.VERY_BULLISH]:
            if analysis.risk_level in ["low", "medium"]:
                if analysis.indicators.advance_decline_ratio > 1.5:
                    return True, "Market conditions favorable: Strong breadth and bullish sentiment"
        
        # Unfavorable conditions
        if analysis.overall_sentiment in [MarketSentiment.VERY_BEARISH]:
            return False, f"Market too bearish: {analysis.overall_sentiment.value}"
        
        if analysis.risk_level == "extreme":
            return False, "Extreme risk detected in market"
        
        if analysis.indicators.market_volatility > 0.04:
            return False, f"Volatility too high: {analysis.indicators.market_volatility:.1%}"
        
        # Neutral - trade with normal parameters
        return True, "Market conditions neutral - trade with standard risk management"


# Global instance
market_sentiment_service = MarketSentimentService()