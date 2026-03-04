"""
Disk Cache Layer
==================
Fast, persistent caching using DiskCache for AI responses, market data, and analysis results.

Provides:
- Sub-millisecond cache lookups for repeated queries
- Automatic expiration with TTL (time-to-live)
- Statistics tracking (hits, misses, size)
- Namespace isolation (research, signals, news)

Usage:
    from disk_cache_layer import get_cache, CacheNamespace
    
    cache = get_cache()
    
    # Simple caching
    result = cache.get_or_fetch(
        key="daily_analysis_xauusd",
        fetch_fn=lambda: run_analysis(),
        ttl_hours=24,
        namespace=CacheNamespace.ANALYSIS
    )
    
    # Stats
    stats = cache.get_stats()
    print(f"Cache hit rate: {stats['hit_rate']:.1%}")
"""

import os
import json
import hashlib
from typing import Optional, Callable, Any, Dict, List
from enum import Enum
from datetime import datetime, timedelta

try:
    import diskcache
    DISKCACHE_AVAILABLE = True
except ImportError:
    DISKCACHE_AVAILABLE = False

from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────

class CacheNamespace(str, Enum):
    """Cache namespaces for organization."""
    AI_RESPONSE = "ai_response"
    MARKET_DATA = "market_data"
    ANALYSIS = "analysis"
    SENTIMENT = "sentiment"
    NEWS = "news"
    SIGNALS = "signals"


# ─────────────────────────────────────────────────────
# Cache Statistics
# ─────────────────────────────────────────────────────

class CacheStats:
    """Cache performance statistics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.total_size_bytes = 0
    
    @property
    def hit_rate(self) -> float:
        """Percentage of cache hits vs total requests."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def total_requests(self) -> int:
        """Total cache requests."""
        return self.hits + self.misses
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': self.hit_rate,
            'total_requests': self.total_requests,
            'evictions': self.evictions,
            'total_size_mb': self.total_size_bytes / (1024 * 1024),
        }


# ─────────────────────────────────────────────────────
# Disk Cache Wrapper
# ─────────────────────────────────────────────────────

class DiskCacheLayer:
    """
    Persistent disk-based cache for AI responses and analysis.
    
    Uses DiskCache library for fast, reliable caching with
    automatic expiration and statistics.
    """
    
    def __init__(self, cache_dir: str = "data/.cache"):
        self.cache_dir = cache_dir
        self.cache = None
        self.stats = CacheStats()
        self.enabled = DISKCACHE_AVAILABLE
        
        self._initialize()
    
    def _initialize(self):
        """Initialize cache."""
        if not DISKCACHE_AVAILABLE:
            logger.warning("[DiskCache] Package not installed (pip install diskcache)")
            self.enabled = False
            return
        
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            self.cache = diskcache.Cache(self.cache_dir)
            logger.info(f"[DiskCache] Initialized at {self.cache_dir}")
        except Exception as e:
            logger.error(f"[DiskCache] Initialization failed: {e}")
            self.enabled = False
    
    # ─────────────────────────────────────────────────
    # Core Cache Operations
    # ─────────────────────────────────────────────────
    
    def _make_key(self, key: str, namespace: CacheNamespace) -> str:
        """Create namespaced cache key."""
        return f"{namespace.value}:{key}"
    
    def get(self, key: str, namespace: CacheNamespace = CacheNamespace.ANALYSIS) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            namespace: Cache namespace for organization
        
        Returns:
            Cached value or None if not found/expired
        """
        if not self.enabled:
            return None
        
        try:
            cache_key = self._make_key(key, namespace)
            value = self.cache.get(cache_key)
            
            if value is not None:
                self.stats.hits += 1
                logger.debug(f"Cache HIT: {cache_key}")
            else:
                self.stats.misses += 1
                logger.debug(f"Cache MISS: {cache_key}")
            
            return value
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl_hours: int = 24,
            namespace: CacheNamespace = CacheNamespace.ANALYSIS) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_hours: Time-to-live in hours
            namespace: Cache namespace
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            cache_key = self._make_key(key, namespace)
            
            # Convert to JSON-serializable if needed
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            # Set with expiration
            expire_time = datetime.now() + timedelta(hours=ttl_hours)
            self.cache.set(cache_key, value, expire=int(expire_time.timestamp()))
            
            # Update size stats
            if hasattr(value, '__sizeof__'):
                self.stats.total_size_bytes += value.__sizeof__()
            
            logger.debug(f"Cache SET: {cache_key} (TTL {ttl_hours}h)")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False
    
    def delete(self, key: str, namespace: CacheNamespace = CacheNamespace.ANALYSIS) -> bool:
        """Delete cache entry."""
        if not self.enabled:
            return False
        
        try:
            cache_key = self._make_key(key, namespace)
            del self.cache[cache_key]
            logger.debug(f"Cache DELETE: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed: {e}")
            return False
    
    # ─────────────────────────────────────────────────
    # Convenience Methods
    # ─────────────────────────────────────────────────
    
    def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        ttl_hours: int = 24,
        namespace: CacheNamespace = CacheNamespace.ANALYSIS,
        force_refresh: bool = False,
    ) -> Any:
        """
        Get from cache or fetch using callback if missing.
        
        Args:
            key: Cache key
            fetch_fn: Function to call if cache misses
            ttl_hours: Cache TTL in hours
            namespace: Cache namespace
            force_refresh: Force cache miss and refetch
        
        Returns:
            Cached or freshly fetched value
        """
        # Return cached if available and not forcing refresh
        if not force_refresh:
            cached = self.get(key, namespace)
            if cached is not None:
                return cached
        
        # Fetch value
        logger.info(f"Cache FETCH: {key} (namespace={namespace.value})")
        try:
            value = fetch_fn()
            self.set(key, value, ttl_hours, namespace)
            return value
        except Exception as e:
            logger.error(f"Fetch failed for {key}: {e}")
            raise
    
    def get_or_default(
        self,
        key: str,
        default: Any = None,
        namespace: CacheNamespace = CacheNamespace.ANALYSIS,
    ) -> Any:
        """Get from cache or return default."""
        cached = self.get(key, namespace)
        return cached if cached is not None else default
    
    # ─────────────────────────────────────────────────
    # Bulk Operations
    # ─────────────────────────────────────────────────
    
    def clear_namespace(self, namespace: CacheNamespace) -> int:
        """
        Clear all entries in a namespace.
        
        Returns:
            Number of entries cleared
        """
        if not self.enabled:
            return 0
        
        try:
            prefix = f"{namespace.value}:"
            cleared = 0
            
            for key in list(self.cache.keys()):
                if key.startswith(prefix):
                    del self.cache[key]
                    cleared += 1
            
            logger.info(f"[DiskCache] Cleared {cleared} entries in {namespace.value}")
            return cleared
        except Exception as e:
            logger.warning(f"Clear namespace failed: {e}")
            return 0
    
    def clear_all(self):
        """Clear entire cache."""
        if self.enabled and self.cache:
            try:
                self.cache.clear()
                self.stats = CacheStats()
                logger.warning("[DiskCache] All cache cleared")
            except Exception as e:
                logger.warning(f"Clear all failed: {e}")
    
    def get_namespace_keys(self, namespace: CacheNamespace) -> List[str]:
        """Get all keys in a namespace."""
        if not self.enabled:
            return []
        
        try:
            prefix = f"{namespace.value}:"
            return [k for k in self.cache.keys() if k.startswith(prefix)]
        except Exception as e:
            logger.warning(f"Get keys failed: {e}")
            return []
    
    # ─────────────────────────────────────────────────
    # Statistics & Monitoring
    # ─────────────────────────────────────────────────
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats_dict = self.stats.to_dict()
        
        if self.enabled and self.cache:
            try:
                stats_dict['cache_entries'] = len(self.cache)
                stats_dict['cache_size_mb'] = self.cache.volume() / (1024 * 1024)
            except Exception as e:
                logger.warning(f"Get cache stats failed: {e}")
        
        return stats_dict
    
    def print_stats(self):
        """Print cache statistics."""
        stats = self.get_stats()
        logger.info(
            f"[DiskCache] Hit rate: {stats['hit_rate']:.1%} | "
            f"Requests: {stats['total_requests']} | "
            f"Entries: {stats.get('cache_entries', 0)} | "
            f"Size: {stats.get('cache_size_mb', 0):.1f} MB"
        )


# ─────────────────────────────────────────────────────
# Singleton Factory
# ─────────────────────────────────────────────────────

_cache_instance: Optional[DiskCacheLayer] = None


def get_cache(cache_dir: str = "data/.cache") -> DiskCacheLayer:
    """
    Get or create singleton DiskCacheLayer instance.
    
    Args:
        cache_dir: Directory for cache storage
    
    Returns:
        DiskCacheLayer singleton
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DiskCacheLayer(cache_dir)
    return _cache_instance
