"""
News Aggregator Module
======================
Aggregates news and research data from multiple sources including AI tools.
Provides unified interface for news collection and analysis.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import time

from logger import get_logger
from news_db import NewsDatabase, NewsArticle
from ai_researcher import AIResearcher
from sentiment_analyzer import SentimentAnalyzer

logger = get_logger(__name__)


class NewsAggregator:
    """
    Aggregates news from multiple sources with AI analysis.
    
    Usage:
        aggregator = NewsAggregator()
        
        # Search and analyze
        results = aggregator.research_symbol("XAUUSD", hours=24)
        
        # Get trading signal
        signal = aggregator.get_trading_signal("XAUUSD")
    """
    
    def __init__(self, db_path: str = "data/news.db"):
        self.db = NewsDatabase(db_path)
        self.ai_researcher = AIResearcher(self.db)
        self.sentiment_analyzer = SentimentAnalyzer()
    
    def research_symbol(self, symbol: str, query: Optional[str] = None,
                        hours: int = 24, use_ai: bool = True) -> Dict:
        """
        Comprehensive research on a symbol.
        
        Args:
            symbol: Trading symbol (e.g., XAUUSD)
            query: Specific query or None for general research
            hours: How far back to look
            use_ai: Whether to use AI tools
        
        Returns:
            Research results with sentiment and signals
        """
        if query is None:
            query = f"{symbol} gold market analysis outlook today"
        
        logger.info(f"Researching {symbol}: {query}")
        
        results = {
            'symbol': symbol,
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'cached_news': [],
            'ai_analysis': None,
            'sentiment': None,
            'trading_signal': None
        }
        
        # Get cached news
        results['cached_news'] = self.db.get_recent_news(symbol, hours)
        logger.info(f"Found {len(results['cached_news'])} cached news items")
        
        # AI research if requested
        if use_ai:
            ai_results = self.ai_researcher.research_all(query)
            aggregated = self.ai_researcher.aggregate_results(ai_results)
            results['ai_analysis'] = aggregated
            
            # Store AI results as news articles
            for ai_result in ai_results:
                if ai_result.success:
                    article = NewsArticle(
                        id=None,
                        title=f"AI Research ({ai_result.tool}): {query[:50]}...",
                        content=ai_result.response,
                        source=f"ai_{ai_result.tool}",
                        url=None,
                        published_at=datetime.now(),
                        symbol=symbol,
                        category='ai_analysis',
                        sentiment=ai_result.confidence,
                        ai_analysis=ai_result.response
                    )
                    self.db.add_news(article)
        
        # Analyze sentiment
        all_texts = []
        
        # Add cached news
        for news in results['cached_news']:
            all_texts.append(news.get('title', '') + ' ' + news.get('content', ''))
        
        # Add AI responses
        if results['ai_analysis'] and results['ai_analysis'].get('success'):
            for ai_data in results['ai_analysis'].get('individual_results', []):
                if 'tool' in ai_data:
                    tool_response = self.db.get_cached_research(query, ai_data['tool'])
                    if tool_response:
                        all_texts.append(tool_response['response'])
        
        if all_texts:
            sentiment = self.sentiment_analyzer.analyze_multiple(all_texts)
            results['sentiment'] = sentiment
            
            # Store sentiment snapshot
            self.db.add_sentiment_snapshot(
                symbol=symbol,
                sentiment=sentiment['average_score'],
                news_count=len(all_texts),
                bullish=sentiment['sentiment_distribution'].get('bullish', 0),
                bearish=sentiment['sentiment_distribution'].get('bearish', 0),
                neutral=sentiment['sentiment_distribution'].get('neutral', 0),
                weighted_score=sentiment['average_score'] * sentiment['average_confidence']
            )
        
        # Generate trading signal
        results['trading_signal'] = self._generate_signal(results)
        
        return results
    
    def _generate_signal(self, research_results: Dict) -> Dict:
        """Generate trading signal from research results."""
        signal = {
            'direction': 'neutral',
            'confidence': 0,
            'strength': 0,
            'factors': [],
            'timeframe': 'short_term',
            'recommendation': 'hold'
        }
        
        # Check AI consensus
        ai_data = research_results.get('ai_analysis', {})
        if ai_data and ai_data.get('success'):
            consensus = ai_data.get('consensus_sentiment', 'neutral')
            consensus_strength = ai_data.get('consensus_strength', 0)
            avg_confidence = ai_data.get('average_confidence', 0) or 0
            
            signal['factors'].append(f"AI Consensus: {consensus} ({consensus_strength:.0%} agreement)")
            
            if consensus == 'bullish':
                signal['direction'] = 'buy'
                signal['confidence'] = avg_confidence * consensus_strength
            elif consensus == 'bearish':
                signal['direction'] = 'sell'
                signal['confidence'] = avg_confidence * consensus_strength
        
        # Check sentiment
        sentiment = research_results.get('sentiment', {})
        if sentiment:
            dom = sentiment.get('dominant_sentiment', 'neutral')
            score = sentiment.get('average_score', 0)
            conf = sentiment.get('average_confidence', 0)
            
            signal['factors'].append(f"Sentiment: {dom} (score: {score:.2f}, confidence: {conf:.2f})")
            
            # Combine with existing signal
            if dom == 'bullish' and signal['direction'] in ['neutral', 'buy']:
                signal['direction'] = 'buy'
                signal['confidence'] = (signal['confidence'] + conf) / 2
            elif dom == 'bearish' and signal['direction'] in ['neutral', 'sell']:
                signal['direction'] = 'sell'
                signal['confidence'] = (signal['confidence'] + conf) / 2
        
        # Determine strength
        if signal['confidence'] > 0.8:
            signal['strength'] = 3
            signal['recommendation'] = 'strong_' + signal['direction']
        elif signal['confidence'] > 0.6:
            signal['strength'] = 2
            signal['recommendation'] = 'moderate_' + signal['direction']
        elif signal['confidence'] > 0.4:
            signal['strength'] = 1
            signal['recommendation'] = 'weak_' + signal['direction']
        else:
            signal['recommendation'] = 'hold'
        
        return signal
    
    def get_sentiment_trend(self, symbol: str, hours: int = 72) -> Dict:
        """
        Get sentiment trend over time.
        
        Returns:
            Trend analysis with direction and momentum
        """
        history = self.db.get_sentiment_trend(symbol, hours)
        
        if not history:
            return {
                'symbol': symbol,
                'trend': 'unknown',
                'momentum': 0,
                'data_points': 0
            }
        
        # Calculate trend
        scores = [h['overall_sentiment'] for h in history]
        
        if len(scores) < 2:
            trend = 'stable'
            momentum = 0
        else:
            # Compare first half vs second half
            mid = len(scores) // 2
            first_avg = sum(scores[:mid]) / max(mid, 1)
            second_avg = sum(scores[mid:]) / max(len(scores) - mid, 1)
            
            momentum = second_avg - first_avg
            
            if momentum > 0.3:
                trend = 'improving'
            elif momentum > 0.1:
                trend = 'slightly_improving'
            elif momentum < -0.3:
                trend = 'deteriorating'
            elif momentum < -0.1:
                trend = 'slightly_deteriorating'
            else:
                trend = 'stable'
        
        return {
            'symbol': symbol,
            'trend': trend,
            'momentum': momentum,
            'current_sentiment': scores[-1] if scores else 0,
            'average_sentiment': sum(scores) / len(scores) if scores else 0,
            'data_points': len(history),
            'history': [
                {
                    'timestamp': h['timestamp'],
                    'sentiment': h['overall_sentiment'],
                    'news_count': h['news_count']
                }
                for h in history
            ]
        }
    
    def compare_with_price(self, symbol: str, price_data: Dict) -> Dict:
        """
        Compare news sentiment with actual price movement.
        
        Args:
            symbol: Trading symbol
            price_data: Dict with price_before, price_after, time_before, time_after
        
        Returns:
            Correlation analysis
        """
        # Get news between price points
        # This is a simplified version - real implementation would query by time
        recent_news = self.db.get_recent_news(symbol, hours=24)
        
        if not recent_news:
            return {'error': 'No news data available'}
        
        # Analyze sentiment of news
        texts = [n['content'] for n in recent_news if n.get('content')]
        sentiment = self.sentiment_analyzer.analyze_multiple(texts)
        
        # Calculate price change
        price_before = price_data.get('price_before', 0)
        price_after = price_data.get('price_after', 0)
        
        if price_before > 0:
            price_change_pct = ((price_after - price_before) / price_before) * 100
        else:
            price_change_pct = 0
        
        # Compare sentiment with price
        sentiment_direction = sentiment['dominant_sentiment']
        price_direction = 'bullish' if price_change_pct > 0 else 'bearish' if price_change_pct < 0 else 'neutral'
        
        alignment = sentiment_direction == price_direction
        
        return {
            'symbol': symbol,
            'sentiment_direction': sentiment_direction,
            'price_direction': price_direction,
            'price_change_pct': price_change_pct,
            'sentiment_score': sentiment['average_score'],
            'alignment': alignment,
            'conclusion': 'aligned' if alignment else 'divergent',
            'news_count': len(recent_news)
        }
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old data to save space."""
        self.db.clean_old_data(days)
        logger.info(f"Cleaned data older than {days} days")
    
    def get_stats(self) -> Dict:
        """Get aggregator statistics."""
        return self.db.get_statistics()
