"""
News Database Module
====================
Manages storage for news, research data, and AI analysis results.
Uses SQLite for simplicity and portability.
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class NewsArticle:
    """News article data structure."""
    id: Optional[int]
    title: str
    content: str
    source: str
    url: Optional[str]
    published_at: datetime
    symbol: str
    category: str
    sentiment: Optional[float] = None
    impact_score: Optional[float] = None
    ai_analysis: Optional[str] = None
    created_at: Optional[datetime] = None


class NewsDatabase:
    """
    Database manager for news and research data.
    
    Tables:
        - news_articles: ข่าวและบทความ
        - ai_research: ผลการค้นหาจาก AI tools
        - market_events: เหตุการณ์สำคัญตลาด
        - price_correlations: ความสัมพันธ์ราคากับข่าว
    """
    
    def __init__(self, db_path: Optional[str] = None):
        resolved_path = db_path or os.getenv("NEWS_DB_PATH", "data/news.db")
        self.db_path = Path(resolved_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # News articles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT,
                    published_at TIMESTAMP NOT NULL,
                    symbol TEXT NOT NULL,
                    category TEXT NOT NULL,
                    sentiment REAL,
                    impact_score REAL,
                    ai_analysis TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(title, source, published_at)
                )
            """)
            
            # AI research results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_research (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    response TEXT NOT NULL,
                    symbol TEXT,
                    category TEXT,
                    confidence REAL,
                    sources TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    UNIQUE(query, tool, created_at)
                )
            """)
            
            # Market events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    symbol TEXT NOT NULL,
                    expected_impact TEXT,
                    actual_impact TEXT,
                    event_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Price correlation table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_correlations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER,
                    symbol TEXT NOT NULL,
                    price_before REAL,
                    price_after REAL,
                    price_change_pct REAL,
                    time_before TIMESTAMP,
                    time_after TIMESTAMP,
                    correlation_score REAL,
                    FOREIGN KEY (news_id) REFERENCES news_articles(id)
                )
            """)
            
            # Sentiment history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    overall_sentiment REAL,
                    news_count INTEGER,
                    bullish_count INTEGER,
                    bearish_count INTEGER,
                    neutral_count INTEGER,
                    weighted_score REAL
                )
            """)
            
            # Indexes for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_articles(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_time ON news_articles(published_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_query ON ai_research(query, tool)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sentiment_symbol ON sentiment_history(symbol)
            """)
            
            conn.commit()
            logger.info("News database initialized")
    
    def add_news(self, article: NewsArticle) -> int:
        """
        Add news article to database.
        
        Returns:
            Article ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO news_articles 
                    (title, content, source, url, published_at, symbol, category,
                     sentiment, impact_score, ai_analysis)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.title, article.content, article.source, article.url,
                    article.published_at, article.symbol, article.category,
                    article.sentiment, article.impact_score, article.ai_analysis
                ))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                logger.warning(f"Duplicate news article: {article.title}")
                return -1
    
    def get_recent_news(self, symbol: str, hours: int = 24,
                        category: Optional[str] = None) -> List[Dict]:
        """Get recent news for a symbol."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(hours=hours)
            
            if category:
                cursor.execute("""
                    SELECT * FROM news_articles 
                    WHERE symbol = ? AND category = ? AND published_at > ?
                    ORDER BY published_at DESC
                """, (symbol, category, since))
            else:
                cursor.execute("""
                    SELECT * FROM news_articles 
                    WHERE symbol = ? AND published_at > ?
                    ORDER BY published_at DESC
                """, (symbol, since))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def add_ai_research(self, query: str, tool: str, response: str,
                        symbol: Optional[str] = None,
                        category: Optional[str] = None,
                        confidence: Optional[float] = None,
                        sources: Optional[List[str]] = None,
                        ttl_hours: int = 24) -> int:
        """
        Store AI research result.
        
        Args:
            query: Search query
            tool: AI tool used (opencode, kilocode, gemini)
            response: AI response text
            symbol: Related symbol
            category: News category
            confidence: Confidence score 0-1
            sources: List of sources
            ttl_hours: Cache time-to-live in hours
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            expires_at = datetime.now() + timedelta(hours=ttl_hours)
            sources_json = json.dumps(sources) if sources else None
            
            cursor.execute("""
                INSERT INTO ai_research 
                (query, tool, response, symbol, category, confidence, sources, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (query, tool, response, symbol, category, confidence, sources_json, expires_at))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_cached_research(self, query: str, tool: str,
                            max_age_hours: int = 24) -> Optional[Dict]:
        """
        Get cached AI research result if not expired.
        
        Returns:
            Cached result or None if expired/not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM ai_research 
                WHERE query = ? AND tool = ? AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
            """, (query, tool, datetime.now()))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get('sources'):
                    result['sources'] = json.loads(result['sources'])
                return result
            return None
    
    def get_all_research_for_query(self, query: str,
                                    symbol: Optional[str] = None) -> List[Dict]:
        """Get all AI research results for a query across all tools."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("""
                    SELECT * FROM ai_research 
                    WHERE query = ? AND symbol = ? AND expires_at > ?
                    ORDER BY tool, created_at DESC
                """, (query, symbol, datetime.now()))
            else:
                cursor.execute("""
                    SELECT * FROM ai_research 
                    WHERE query = ? AND expires_at > ?
                    ORDER BY tool, created_at DESC
                """, (query, datetime.now()))
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result.get('sources'):
                    result['sources'] = json.loads(result['sources'])
                results.append(result)
            return results
    
    def add_sentiment_snapshot(self, symbol: str, sentiment: float,
                                news_count: int, bullish: int, bearish: int,
                                neutral: int, weighted_score: float):
        """Record sentiment snapshot."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sentiment_history 
                (symbol, overall_sentiment, news_count, bullish_count, bearish_count,
                 neutral_count, weighted_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, sentiment, news_count, bullish, bearish, neutral, weighted_score))
            conn.commit()
    
    def get_sentiment_trend(self, symbol: str, hours: int = 24) -> List[Dict]:
        """Get sentiment trend over time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            since = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT * FROM sentiment_history 
                WHERE symbol = ? AND timestamp > ?
                ORDER BY timestamp ASC
            """, (symbol, since))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def clean_old_data(self, days: int = 30):
        """Clean data older than specified days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)
            
            tables = ['news_articles', 'ai_research', 'market_events', 'sentiment_history']
            for table in tables:
                cursor.execute(f"""
                    DELETE FROM {table} WHERE created_at < ?
                """, (cutoff,))
            
            conn.commit()
            logger.info(f"Cleaned data older than {days} days")
    
    def get_statistics(self) -> Dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            tables = ['news_articles', 'ai_research', 'market_events', 'sentiment_history']
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            
            return stats
