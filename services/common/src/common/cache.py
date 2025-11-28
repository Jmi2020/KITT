"""Semantic cache backed by Redis Streams with TTL and size limits."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import redis

from .config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheRecord:
    key: str
    prompt: str
    response: str
    confidence: float


@dataclass
class CacheStats:
    """Cache statistics for monitoring"""
    size_bytes: int
    entry_count: int
    hits: int
    misses: int
    hit_rate: float
    max_entries: int
    ttl_seconds: int


class SemanticCache:
    """Persist prompts/responses in Redis Streams for reuse and observability.

    Features:
    - TTL-based expiration (default: 12 hours)
    - Max entry limit to prevent unbounded growth (default: 10,000)
    - Automatic trimming via MAXLEN
    - Hit/miss tracking for observability
    - Cache size monitoring
    """

    STREAM_KEY = "kitty:semantic-cache"
    STATS_KEY = "kitty:semantic-cache:stats"

    # Default configuration
    DEFAULT_TTL_SECONDS = int(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", "43200"))  # 12 hours
    DEFAULT_MAX_ENTRIES = int(os.getenv("SEMANTIC_CACHE_MAX_ENTRIES", "10000"))

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        max_entries: Optional[int] = None
    ) -> None:
        """Initialize semantic cache.

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Cache entry TTL (default: 12 hours)
            max_entries: Maximum entries before trimming (default: 10,000)
        """
        self._client = redis.from_url(redis_url or settings.redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds or self.DEFAULT_TTL_SECONDS
        self._max_entries = max_entries or self.DEFAULT_MAX_ENTRIES

        logger.info(
            f"SemanticCache initialized: TTL={self._ttl_seconds}s, "
            f"max_entries={self._max_entries}"
        )

    def store(self, record: CacheRecord) -> Optional[str]:
        """Store cache entry with TTL and size limiting.

        Args:
            record: Cache record to store

        Returns:
            Entry ID in stream, or None if Redis unavailable
        """
        payload = {
            "prompt": record.prompt,
            "response": record.response,
            "confidence": record.confidence,
        }

        try:
            # Add to stream with MAXLEN trimming to prevent unbounded growth
            entry_id = self._client.xadd(
                self.STREAM_KEY,
                {record.key: json.dumps(payload)},
                maxlen=self._max_entries,
                approximate=True  # ~= allows faster trimming
            )

            # Set TTL on the stream itself (resets on each write)
            self._client.expire(self.STREAM_KEY, self._ttl_seconds)

            return entry_id
        except redis.ConnectionError:
            # Redis unavailable - skip caching, don't crash
            logger.warning("Redis unavailable for cache store, skipping")
            return None

    def fetch(self, key: str) -> Optional[CacheRecord]:
        """Fetch cache entry and track hit/miss.

        Args:
            key: Cache key to fetch

        Returns:
            CacheRecord if found, None otherwise
        """
        # Search recent entries (last 100 for better hit rate)
        try:
            entries = self._client.xrevrange(self.STREAM_KEY, count=100)
        except redis.ResponseError:
            # Stream doesn't exist
            self._increment_stat("misses")
            return None
        except redis.ConnectionError:
            # Redis unavailable - treat as cache miss, don't crash
            logger.warning("Redis unavailable for cache fetch, treating as miss")
            return None

        for _, fields in entries:
            if key in fields:
                # Cache hit
                self._increment_stat("hits")

                data = json.loads(fields[key])
                return CacheRecord(
                    key=key,
                    prompt=data["prompt"],
                    response=data["response"],
                    confidence=data["confidence"],
                )

        # Cache miss
        self._increment_stat("misses")
        return None

    def hit_ratio(self) -> float:
        """Calculate actual cache hit ratio.

        Returns:
            Hit rate (0.0 to 1.0)
        """
        stats = self.get_stats()
        return stats.hit_rate

    def get_stats(self) -> CacheStats:
        """Get cache statistics for monitoring.

        Returns:
            CacheStats with current metrics
        """
        try:
            # Get stream info
            info = self._client.xinfo_stream(self.STREAM_KEY)
            entry_count = info.get("length", 0)

            # Approximate size (rough estimate)
            size_bytes = entry_count * 500  # ~500 bytes per entry average

            # Get hit/miss stats
            hits = int(self._client.hget(self.STATS_KEY, "hits") or 0)
            misses = int(self._client.hget(self.STATS_KEY, "misses") or 0)

            total_requests = hits + misses
            hit_rate = (hits / total_requests) if total_requests > 0 else 0.0

            return CacheStats(
                size_bytes=size_bytes,
                entry_count=entry_count,
                hits=hits,
                misses=misses,
                hit_rate=hit_rate,
                max_entries=self._max_entries,
                ttl_seconds=self._ttl_seconds
            )

        except (redis.ResponseError, redis.ConnectionError):
            # Stream doesn't exist yet or Redis unavailable
            return CacheStats(
                size_bytes=0,
                entry_count=0,
                hits=0,
                misses=0,
                hit_rate=0.0,
                max_entries=self._max_entries,
                ttl_seconds=self._ttl_seconds
            )

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of keys deleted
        """
        deleted = self._client.delete(self.STREAM_KEY, self.STATS_KEY)
        logger.info("Semantic cache cleared")
        return deleted

    def trim(self, max_entries: Optional[int] = None) -> int:
        """Manually trim cache to max entries.

        Args:
            max_entries: Max entries to keep (default: configured max)

        Returns:
            Number of entries trimmed
        """
        limit = max_entries or self._max_entries

        try:
            info = self._client.xinfo_stream(self.STREAM_KEY)
            current_length = info.get("length", 0)

            if current_length > limit:
                # Trim to max length
                self._client.xtrim(self.STREAM_KEY, maxlen=limit, approximate=True)
                trimmed = current_length - limit
                logger.info(f"Trimmed {trimmed} cache entries (kept {limit})")
                return trimmed

            return 0

        except redis.ResponseError:
            return 0

    def _increment_stat(self, stat_name: str) -> None:
        """Increment a statistics counter.

        Args:
            stat_name: Name of stat to increment (hits/misses)
        """
        try:
            self._client.hincrby(self.STATS_KEY, stat_name, 1)
            # Set TTL on stats hash
            self._client.expire(self.STATS_KEY, self._ttl_seconds)
        except redis.ConnectionError:
            # Redis unavailable - skip stat tracking, don't crash
            pass


__all__ = ["SemanticCache", "CacheRecord", "CacheStats"]
