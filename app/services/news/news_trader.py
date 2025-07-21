"""News-based trading service using sentiment analysis."""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import re
from textblob import TextBlob
import yfinance as yf

from app.monitoring.logger import get_logger
from app.services.trading.execution_engine import ExecutionEngine

logger = get_logger(__name__)


class NewsSentiment(str, Enum):
    """News sentiment categories."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


@dataclass
class NewsArticle:
    """News article data."""
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime
    symbols: List[str]
    sentiment_score: float  # -1 to 1
    sentiment: NewsSentiment
    relevance_score: float  # 0 to 1
    
    
@dataclass
class NewsSignal:
    """Trading signal based on news."""
    symbol: str
    action: str  # "buy", "sell", "hold"
    confidence: float
    sentiment: NewsSentiment
    news_count: int
    avg_sentiment_score: float
    key_articles: List[NewsArticle]
    reason: str


class NewsTrader:
    """News-based trading using sentiment analysis."""
    
    def __init__(self, execution_engine: ExecutionEngine):
        self.execution_engine = execution_engine
        self.news_cache: Dict[str, List[NewsArticle]] = {}
        self.sentiment_history: Dict[str, List[float]] = {}
        
        # Configuration
        self.min_articles_for_signal = 3
        self.sentiment_threshold = 0.3
        self.recency_hours = 24
        self.position_size_multiplier = 0.5  # Conservative sizing
        
        # News sources (in practice, would use real APIs)
        self.news_sources = [
            "bloomberg",
            "reuters",
            "cnbc",
            "marketwatch",
            "seekingalpha"
        ]
        
    async def fetch_news(self, symbols: List[str]) -> Dict[str, List[NewsArticle]]:
        """Fetch news for given symbols."""
        news_by_symbol = {}
        
        for symbol in symbols:
            try:
                # In practice, this would call news APIs
                # For now, use Yahoo Finance news as example
                ticker = yf.Ticker(symbol)
                news = ticker.news
                
                articles = []
                for item in news[:10]:  # Last 10 news items
                    # Analyze sentiment
                    text = f"{item.get('title', '')} {item.get('summary', '')}"
                    sentiment_score = self._analyze_sentiment(text)
                    sentiment = self._categorize_sentiment(sentiment_score)
                    
                    # Extract relevance
                    relevance = self._calculate_relevance(text, symbol)
                    
                    article = NewsArticle(
                        title=item.get('title', ''),
                        summary=item.get('summary', '')[:200],
                        source=item.get('publisher', 'Unknown'),
                        url=item.get('link', ''),
                        published_at=datetime.fromtimestamp(item.get('providerPublishTime', 0)),
                        symbols=[symbol],
                        sentiment_score=sentiment_score,
                        sentiment=sentiment,
                        relevance_score=relevance
                    )
                    
                    articles.append(article)
                    
                news_by_symbol[symbol] = articles
                self.news_cache[symbol] = articles
                
            except Exception as e:
                logger.error(f"Error fetching news for {symbol}: {e}")
                news_by_symbol[symbol] = []
                
        return news_by_symbol
        
    def _analyze_sentiment(self, text: str) -> float:
        """Analyze sentiment of text using TextBlob and custom rules."""
        try:
            # Basic sentiment with TextBlob
            blob = TextBlob(text)
            base_sentiment = blob.sentiment.polarity  # -1 to 1
            
            # Custom keyword adjustments
            bullish_keywords = [
                'surge', 'soar', 'rally', 'breakthrough', 'record high',
                'beat expectations', 'strong earnings', 'upgrade', 'buy',
                'growth', 'expansion', 'innovation', 'positive', 'exceed'
            ]
            
            bearish_keywords = [
                'crash', 'plunge', 'fall', 'decline', 'concern', 'worry',
                'miss expectations', 'downgrade', 'sell', 'warning',
                'recession', 'layoff', 'loss', 'negative', 'below'
            ]
            
            text_lower = text.lower()
            
            # Count keyword occurrences
            bullish_count = sum(1 for keyword in bullish_keywords if keyword in text_lower)
            bearish_count = sum(1 for keyword in bearish_keywords if keyword in text_lower)
            
            # Adjust sentiment based on keywords
            keyword_adjustment = (bullish_count - bearish_count) * 0.1
            
            # Combine base sentiment with keyword adjustment
            final_sentiment = max(-1, min(1, base_sentiment + keyword_adjustment))
            
            return final_sentiment
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return 0.0
            
    def _categorize_sentiment(self, score: float) -> NewsSentiment:
        """Categorize sentiment score into discrete categories."""
        if score >= 0.5:
            return NewsSentiment.VERY_BULLISH
        elif score >= 0.2:
            return NewsSentiment.BULLISH
        elif score >= -0.2:
            return NewsSentiment.NEUTRAL
        elif score >= -0.5:
            return NewsSentiment.BEARISH
        else:
            return NewsSentiment.VERY_BEARISH
            
    def _calculate_relevance(self, text: str, symbol: str) -> float:
        """Calculate relevance of news to the symbol."""
        try:
            text_lower = text.lower()
            symbol_lower = symbol.lower()
            
            # Direct mentions
            direct_mentions = text_lower.count(symbol_lower)
            
            # Company name mentions (would need mapping)
            company_names = {
                "AAPL": ["apple", "iphone", "tim cook"],
                "TSLA": ["tesla", "elon musk", "electric vehicle"],
                "AMZN": ["amazon", "aws", "jeff bezos"],
                # Add more mappings
            }
            
            company_mentions = 0
            if symbol in company_names:
                for name in company_names[symbol]:
                    company_mentions += text_lower.count(name)
                    
            # Calculate relevance score
            total_mentions = direct_mentions + company_mentions
            relevance = min(1.0, total_mentions / 5)  # Cap at 1.0
            
            return relevance
            
        except Exception as e:
            logger.error(f"Error calculating relevance: {e}")
            return 0.5
            
    async def analyze_news_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> Optional[NewsSignal]:
        """Analyze news sentiment for a symbol and generate signal."""
        try:
            # Get recent news
            if symbol not in self.news_cache:
                await self.fetch_news([symbol])
                
            articles = self.news_cache.get(symbol, [])
            
            # Filter by recency
            cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
            recent_articles = [
                a for a in articles
                if a.published_at > cutoff_time
            ]
            
            if len(recent_articles) < self.min_articles_for_signal:
                return None
                
            # Calculate aggregate sentiment
            sentiment_scores = [a.sentiment_score * a.relevance_score for a in recent_articles]
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            
            # Count sentiment categories
            sentiment_counts = {}
            for article in recent_articles:
                sentiment_counts[article.sentiment] = sentiment_counts.get(article.sentiment, 0) + 1
                
            # Determine dominant sentiment
            dominant_sentiment = max(sentiment_counts, key=sentiment_counts.get)
            
            # Generate signal
            if abs(avg_sentiment) < self.sentiment_threshold:
                return None
                
            if avg_sentiment > self.sentiment_threshold:
                action = "buy"
                confidence = min(0.9, avg_sentiment)
                reason = f"Positive news sentiment ({avg_sentiment:.2f}) from {len(recent_articles)} articles"
            else:
                action = "sell"
                confidence = min(0.9, abs(avg_sentiment))
                reason = f"Negative news sentiment ({avg_sentiment:.2f}) from {len(recent_articles)} articles"
                
            # Get key articles
            key_articles = sorted(
                recent_articles,
                key=lambda a: abs(a.sentiment_score) * a.relevance_score,
                reverse=True
            )[:3]
            
            return NewsSignal(
                symbol=symbol,
                action=action,
                confidence=confidence,
                sentiment=dominant_sentiment,
                news_count=len(recent_articles),
                avg_sentiment_score=avg_sentiment,
                key_articles=key_articles,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Error analyzing news sentiment for {symbol}: {e}")
            return None
            
    async def monitor_breaking_news(
        self,
        symbols: List[str],
        callback: Any
    ):
        """Monitor for breaking news and trigger callbacks."""
        while True:
            try:
                # Fetch latest news
                news_by_symbol = await self.fetch_news(symbols)
                
                for symbol, articles in news_by_symbol.items():
                    # Check for significant news
                    for article in articles[:5]:  # Check last 5 articles
                        if article.published_at > datetime.utcnow() - timedelta(minutes=30):
                            # Recent breaking news
                            if abs(article.sentiment_score) > 0.5 and article.relevance_score > 0.7:
                                await callback(symbol, article)
                                
                # Wait before next check
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error monitoring breaking news: {e}")
                await asyncio.sleep(60)
                
    async def execute_news_signal(self, signal: NewsSignal) -> Dict[str, Any]:
        """Execute a news-based trading signal."""
        try:
            # Adjust position size based on confidence
            base_size = 100  # Base shares
            adjusted_size = int(base_size * signal.confidence * self.position_size_multiplier)
            
            # Create trade signal
            trade_signal = {
                "symbol": signal.symbol,
                "side": signal.action,
                "qty": adjusted_size,
                "reason": f"[NEWS] {signal.reason}"
            }
            
            # Execute through execution engine
            result = await self.execution_engine._process_signal(trade_signal)
            
            return {
                "status": "executed",
                "symbol": signal.symbol,
                "action": signal.action,
                "quantity": adjusted_size,
                "sentiment": signal.sentiment.value,
                "confidence": signal.confidence,
                "order_id": result.get("id")
            }
            
        except Exception as e:
            logger.error(f"Error executing news signal: {e}")
            return {"status": "error", "message": str(e)}
            
    def get_sentiment_summary(self, symbols: List[str]) -> Dict[str, Any]:
        """Get sentiment summary for multiple symbols."""
        summary = {}
        
        for symbol in symbols:
            articles = self.news_cache.get(symbol, [])
            
            if articles:
                recent_articles = [
                    a for a in articles
                    if a.published_at > datetime.utcnow() - timedelta(hours=24)
                ]
                
                if recent_articles:
                    avg_sentiment = sum(a.sentiment_score for a in recent_articles) / len(recent_articles)
                    
                    summary[symbol] = {
                        "article_count": len(recent_articles),
                        "avg_sentiment": avg_sentiment,
                        "sentiment": self._categorize_sentiment(avg_sentiment).value,
                        "latest_article": recent_articles[0].title if recent_articles else None
                    }
                    
        return summary
        
    async def backtest_news_strategy(
        self,
        symbol: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """Backtest news-based strategy."""
        try:
            # Would implement historical news analysis
            # For now, return mock results
            
            return {
                "symbol": symbol,
                "period_days": lookback_days,
                "total_signals": 15,
                "profitable_signals": 9,
                "win_rate": 0.60,
                "avg_return_per_signal": 0.008,
                "sharpe_ratio": 1.2,
                "max_drawdown": -0.05
            }
            
        except Exception as e:
            logger.error(f"Error backtesting news strategy: {e}")
            return {}


# Note: This requires additional dependencies
# pip install textblob yfinance