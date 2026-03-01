"""PEDR search result caching for latency optimization.

This module implements query result caching to reduce latency for repeated or
similar queries. The cache provides:
- Deterministic cache keys based on query parameters
- TTL-based expiration (default: 5 minutes)
- LRU eviction when max_size is reached
- Global invalidation on document changes
- Statistics tracking for hit/miss rates

Reference: B19.2 - Semantic Search Result Caching
           R19.0 - Qdrant Optimization Research (three-tier cache architecture)
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import event

from app.models import GraphEdge

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with results and metadata."""

    results: List[Dict[str, Any]]
    timestamp: float
    query_hash: str
    filters: Dict[str, Any]
    hit_count: int = 0


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    cache_hits: int = 0
    cache_misses: int = 0
    cache_size: int = 0
    evictions: int = 0
    invalidations: int = 0
    last_invalidation: Optional[float] = None

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(self.hit_rate, 4),
            "cache_size": self.cache_size,
            "evictions": self.evictions,
            "invalidations": self.invalidations,
            "last_invalidation": self.last_invalidation,
        }


class PEDRCache:
    """LRU cache with TTL for PEDR search results.

    Thread-safe implementation using a lock for concurrent access.
    Cache keys are deterministic hashes of normalized query parameters.

    Example:
        cache = PEDRCache(max_size=1000, ttl_seconds=300)

        # Check cache
        cached = cache.get(query="usability testing", top_k=10, filters={})
        if cached is not None:
            return cached  # Cache hit

        # Execute search and cache results
        results = execute_search(...)
        cache.set(query="usability testing", top_k=10, filters={}, results=results)
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 300,
    ) -> None:
        """Initialize the PEDR cache.

        Args:
            max_size: Maximum number of cache entries before LRU eviction.
            ttl_seconds: Time-to-live for cache entries in seconds.
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()
        self._lock = threading.RLock()

    def _generate_key(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate deterministic cache key from query parameters.

        The key is a SHA256 hash of the normalized query, top_k, and
        sorted filter items. This ensures that identical queries with
        the same parameters always produce the same cache key.

        Args:
            query: The search query text.
            top_k: Number of results requested.
            filters: Optional filter dictionary.

        Returns:
            16-character hex hash as cache key.
        """
        normalized_query = query.lower().strip()
        normalized_filters = sorted((filters or {}).items())

        # Build payload string
        payload = f"{normalized_query}:{top_k}:{normalized_filters}"

        # Generate hash
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached results if available and not expired.

        Args:
            query: The search query text.
            top_k: Number of results requested.
            filters: Optional filter dictionary.

        Returns:
            Cached results list or None if cache miss.
        """
        key = self._generate_key(query, top_k, filters)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.cache_misses += 1
                logger.debug("PEDR cache miss for key %s", key)
                return None

            # Check TTL expiration
            if time.time() - entry.timestamp > self.ttl_seconds:
                del self._cache[key]
                self._stats.cache_misses += 1
                self._stats.cache_size = len(self._cache)
                logger.debug("PEDR cache expired for key %s", key)
                return None

            # Cache hit
            entry.hit_count += 1
            self._stats.cache_hits += 1
            self._cache.move_to_end(key)
            logger.debug(
                "PEDR cache hit for key %s (hit_count=%d)",
                key,
                entry.hit_count,
            )
            return entry.results

    def set(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
        results: List[Dict[str, Any]],
    ) -> None:
        """Store search results in cache.

        If the cache is at max_size, the oldest entry is evicted (LRU).

        Args:
            query: The search query text.
            top_k: Number of results requested.
            filters: Optional filter dictionary.
            results: The search results to cache.
        """
        key = self._generate_key(query, top_k, filters)

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                self._stats.evictions += 1
                logger.debug("PEDR cache evicted LRU key %s", evicted_key)

            self._cache[key] = CacheEntry(
                results=results,
                timestamp=time.time(),
                query_hash=key,
                filters=dict(filters or {}),
            )
            self._stats.cache_size = len(self._cache)
            logger.debug("PEDR cache stored key %s", key)

    def invalidate_all(self) -> int:
        """Clear entire cache.

        Call this on document changes (upload, delete, update) to ensure
        search results reflect current data.

        Returns:
            Number of entries cleared.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.invalidations += 1
            self._stats.last_invalidation = time.time()
            self._stats.cache_size = 0
            logger.info("PEDR cache invalidated, cleared %d entries", count)
            return count

    def invalidate_project(self, project_id: str) -> int:
        """Invalidate cache entries for a specific project ID."""
        project_text = str(project_id).strip()
        if not project_text:
            return 0

        with self._lock:
            removed_keys = [
                key
                for key, entry in self._cache.items()
                if str(entry.filters.get("project_id") or "") == project_text
            ]
            for key in removed_keys:
                del self._cache[key]

            if removed_keys:
                self._stats.invalidations += 1
                self._stats.last_invalidation = time.time()
                self._stats.cache_size = len(self._cache)
                logger.info(
                    "PEDR cache invalidated %d project-scoped entries for project_id=%s",
                    len(removed_keys),
                    project_text,
                )

            return len(removed_keys)

    def get_stats(self) -> CacheStats:
        """Get current cache statistics.

        Returns:
            CacheStats with hit/miss counts and rates.
        """
        with self._lock:
            self._stats.cache_size = len(self._cache)
            return CacheStats(
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                cache_size=self._stats.cache_size,
                evictions=self._stats.evictions,
                invalidations=self._stats.invalidations,
                last_invalidation=self._stats.last_invalidation,
            )

    def reset_stats(self) -> None:
        """Reset cache statistics to zero."""
        with self._lock:
            self._stats = CacheStats(cache_size=len(self._cache))


# Lazy singleton - initialized on first access to allow config to load
_pedr_cache: Optional[PEDRCache] = None


def get_pedr_cache() -> PEDRCache:
    """Get the global PEDR cache singleton.

    Lazy initialization to allow config settings to load first.

    Returns:
        The global PEDRCache instance.
    """
    global _pedr_cache
    if _pedr_cache is None:
        from app.core.config import settings

        _pedr_cache = PEDRCache(
            max_size=getattr(settings, "pedr_cache_max_size", 1000),
            ttl_seconds=getattr(settings, "pedr_cache_ttl_seconds", 300),
        )
        logger.info(
            "PEDR cache initialized: max_size=%d, ttl=%ds",
            _pedr_cache.max_size,
            _pedr_cache.ttl_seconds,
        )
    return _pedr_cache


def invalidate_pedr_cache() -> int:
    """Invalidate the global PEDR cache.

    Convenience function for document change handlers.

    Returns:
        Number of entries cleared, or 0 if cache not initialized.
    """
    global _pedr_cache
    if _pedr_cache is not None:
        return _pedr_cache.invalidate_all()
    return 0


def _invalidate_pedr_cache_on_edge_change(*_args: object, **_kwargs: object) -> None:
    try:
        invalidate_pedr_cache()
    except Exception:
        logger.exception("Failed to invalidate PEDR cache after graph edge change.")


event.listen(GraphEdge, "after_insert", _invalidate_pedr_cache_on_edge_change)
event.listen(GraphEdge, "after_update", _invalidate_pedr_cache_on_edge_change)
event.listen(GraphEdge, "after_delete", _invalidate_pedr_cache_on_edge_change)


__all__ = [
    "CacheEntry",
    "CacheStats",
    "PEDRCache",
    "get_pedr_cache",
    "invalidate_pedr_cache",
]
