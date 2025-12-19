"""
Search Results Cache

Redis-backed cache for search results with 24-hour TTL.
Reduces API costs by reusing results for identical queries.

Usage:
    from brain.research.search_cache import search_cache

    # Check cache before executing search
    cached = await search_cache.get(query, provider_id)
    if cached:
        return cached

    # Execute search...
    results = await execute_search(query, provider_id)

    # Cache results
    await search_cache.set(query, provider_id, results)
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_PREFIX = "kitt:search_cache:"
DEFAULT_TTL = 86400  # 24 hours in seconds
STATS_KEY = "kitt:search_cache:stats"


class SearchCache:
    """
    Redis-backed search results cache.

    Provides:
    - 24-hour TTL for search results
    - Graceful degradation if Redis unavailable
    - Cache hit/miss statistics
    - Normalized query hashing for better cache hits
    """

    def __init__(self):
        """Initialize cache (lazy Redis connection)."""
        self._redis = None
        self._redis_available = True  # Assume available until proven otherwise

    def _get_redis(self):
        """Get Redis connection (lazy initialization)."""
        if not self._redis_available:
            return None

        if self._redis is None:
            try:
                import redis
                from common.config import settings

                self._redis = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
                # Test connection
                self._redis.ping()
                logger.info("Search cache connected to Redis")
            except Exception as e:
                logger.warning(f"Redis unavailable for search cache: {e}")
                self._redis = None
                self._redis_available = False
                return None

        return self._redis

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent caching."""
        # Lowercase, strip, collapse whitespace
        normalized = " ".join(query.lower().strip().split())
        return normalized

    def _cache_key(self, query: str, provider: str) -> str:
        """Generate cache key from query and provider."""
        normalized = self._normalize_query(query)
        query_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"{CACHE_PREFIX}{provider}:{query_hash}"

    async def get(
        self, query: str, provider: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached search results.

        Args:
            query: Search query
            provider: Provider ID (e.g., "duckduckgo", "brave")

        Returns:
            Cached results dict with keys: results, cached_at, cache_age
            None if not cached or Redis unavailable
        """
        r = self._get_redis()
        if not r:
            return None

        try:
            key = self._cache_key(query, provider)
            data = r.get(key)

            if data:
                cached = json.loads(data)
                cached_at = cached.get("cached_at", 0)
                cached["cache_age"] = time.time() - cached_at

                # Update stats
                r.hincrby(STATS_KEY, "hits", 1)

                logger.debug(
                    f"Cache HIT for query '{query[:50]}...' "
                    f"(provider={provider}, age={cached['cache_age']:.0f}s)"
                )
                return cached

            # Cache miss
            r.hincrby(STATS_KEY, "misses", 1)
            return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set(
        self,
        query: str,
        provider: str,
        results: List[Dict[str, Any]],
        ttl: int = DEFAULT_TTL,
    ) -> bool:
        """
        Cache search results.

        Args:
            query: Search query
            provider: Provider ID
            results: List of search result dicts
            ttl: Time-to-live in seconds (default: 24 hours)

        Returns:
            True if cached successfully, False otherwise
        """
        r = self._get_redis()
        if not r:
            return False

        try:
            key = self._cache_key(query, provider)
            payload = {
                "results": results,
                "cached_at": time.time(),
                "query": query,
                "provider": provider,
            }

            r.setex(key, ttl, json.dumps(payload))

            logger.debug(
                f"Cached {len(results)} results for query '{query[:50]}...' "
                f"(provider={provider}, ttl={ttl}s)"
            )
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        r = self._get_redis()
        if not r:
            return {"hits": 0, "misses": 0, "entries": 0}

        try:
            stats = r.hgetall(STATS_KEY) or {}
            # Count cached entries
            entries = len(list(r.scan_iter(f"{CACHE_PREFIX}*")))

            return {
                "hits": int(stats.get("hits", 0)),
                "misses": int(stats.get("misses", 0)),
                "entries": entries,
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"hits": 0, "misses": 0, "entries": 0}

    async def clear(self) -> int:
        """
        Clear all cached search results.

        Returns:
            Number of entries cleared
        """
        r = self._get_redis()
        if not r:
            return 0

        try:
            keys = list(r.scan_iter(f"{CACHE_PREFIX}*"))
            if keys:
                r.delete(*keys)
            # Reset stats
            r.delete(STATS_KEY)

            logger.info(f"Cleared {len(keys)} cached search results")
            return len(keys)

        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return 0

    async def invalidate(self, query: str, provider: str) -> bool:
        """
        Invalidate a specific cached query.

        Args:
            query: Search query
            provider: Provider ID

        Returns:
            True if invalidated, False otherwise
        """
        r = self._get_redis()
        if not r:
            return False

        try:
            key = self._cache_key(query, provider)
            deleted = r.delete(key)
            return deleted > 0
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")
            return False


# Singleton instance
search_cache = SearchCache()
