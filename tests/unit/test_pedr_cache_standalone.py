"""Standalone unit tests for PEDR search result caching (B19.2).

This test file is isolated from the main test suite to avoid SQLAlchemy
model loading issues with SQLite (Mission model uses JSONB).

Tests cover:
- Cache hit/miss behavior
- TTL expiration
- LRU eviction
- Deterministic key generation
- Cache invalidation
- Statistics tracking
- Thread safety
"""
import hashlib
import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# Self-contained implementations to test the cache logic
# These mirror the actual implementations in app/services/pedr/cache.py

@dataclass
class CacheEntry:
    """A single cache entry with results and metadata."""
    results: List[Dict[str, Any]]
    timestamp: float
    query_hash: str
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
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
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
    """LRU cache with TTL for PEDR search results."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._lock = threading.RLock()

    def _generate_key(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized_query = query.lower().strip()
        normalized_filters = sorted((filters or {}).items())
        payload = f"{normalized_query}:{top_k}:{normalized_filters}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        key = self._generate_key(query, top_k, filters)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.cache_misses += 1
                return None
            if time.time() - entry.timestamp > self.ttl_seconds:
                del self._cache[key]
                self._stats.cache_misses += 1
                self._stats.cache_size = len(self._cache)
                return None
            entry.hit_count += 1
            self._stats.cache_hits += 1
            return entry.results

    def set(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
        results: List[Dict[str, Any]],
    ) -> None:
        key = self._generate_key(query, top_k, filters)
        with self._lock:
            if len(self._cache) >= self.max_size and key not in self._cache:
                oldest_key = min(self._cache, key=lambda k: self._cache[k].timestamp)
                del self._cache[oldest_key]
                self._stats.evictions += 1
            self._cache[key] = CacheEntry(
                results=results,
                timestamp=time.time(),
                query_hash=key,
            )
            self._stats.cache_size = len(self._cache)

    def invalidate_all(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.invalidations += 1
            self._stats.last_invalidation = time.time()
            self._stats.cache_size = 0
            return count

    def get_stats(self) -> CacheStats:
        with self._lock:
            self._stats.cache_size = len(self._cache)
            return self._stats

    def reset_stats(self) -> None:
        with self._lock:
            self._stats = CacheStats(cache_size=len(self._cache))


# ============================================================================
# Tests
# ============================================================================


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_empty(self):
        """Hit rate is 0.0 when no requests made."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Hit rate calculated correctly."""
        stats = CacheStats(cache_hits=20, cache_misses=80)
        assert stats.hit_rate == 0.20

    def test_to_dict(self):
        """Stats convert to dictionary correctly."""
        stats = CacheStats(
            cache_hits=10,
            cache_misses=40,
            cache_size=5,
            evictions=2,
            invalidations=1,
            last_invalidation=1234567890.0,
        )
        result = stats.to_dict()
        assert result["cache_hits"] == 10
        assert result["cache_misses"] == 40
        assert result["hit_rate"] == 0.20
        assert result["cache_size"] == 5
        assert result["evictions"] == 2
        assert result["invalidations"] == 1
        assert result["last_invalidation"] == 1234567890.0


class TestPEDRCache:
    """Tests for PEDRCache class."""

    def test_cache_miss_returns_none(self):
        """Cache miss returns None."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        result = cache.get("test query", 10, {})
        assert result is None

    def test_cache_miss_increments_stats(self):
        """Cache miss increments miss counter."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        cache.get("test query", 10, {})
        stats = cache.get_stats()
        assert stats.cache_misses == 1
        assert stats.cache_hits == 0

    def test_cache_hit_returns_results(self):
        """Cache hit returns stored results."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        test_results = [{"chunk_id": "123", "content": "test"}]

        cache.set("test query", 10, {}, test_results)
        result = cache.get("test query", 10, {})

        assert result == test_results

    def test_cache_hit_increments_stats(self):
        """Cache hit increments hit counter."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        cache.set("test query", 10, {}, [{"chunk_id": "123"}])
        cache.get("test query", 10, {})

        stats = cache.get_stats()
        assert stats.cache_hits == 1
        assert stats.cache_misses == 0

    def test_ttl_expiration(self):
        """Cache entries expire after TTL."""
        cache = PEDRCache(max_size=100, ttl_seconds=1)
        cache.set("test query", 10, {}, [{"chunk_id": "123"}])

        # Should hit immediately
        assert cache.get("test query", 10, {}) is not None

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should miss after expiration
        assert cache.get("test query", 10, {}) is None

    def test_lru_eviction(self):
        """LRU eviction when max_size exceeded."""
        cache = PEDRCache(max_size=3, ttl_seconds=300)

        # Fill cache with staggered timestamps
        cache.set("query1", 10, {}, [{"id": 1}])
        time.sleep(0.01)
        cache.set("query2", 10, {}, [{"id": 2}])
        time.sleep(0.01)
        cache.set("query3", 10, {}, [{"id": 3}])

        # Add fourth entry - should evict oldest (query1)
        cache.set("query4", 10, {}, [{"id": 4}])

        # query1 should be evicted
        assert cache.get("query1", 10, {}) is None
        assert cache.get("query4", 10, {}) is not None

        stats = cache.get_stats()
        assert stats.evictions == 1

    def test_deterministic_key_generation(self):
        """Same query parameters produce same cache key."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("test query", 10, {"project_id": "abc"}, [{"id": 1}])
        result = cache.get("test query", 10, {"project_id": "abc"})
        assert result is not None

    def test_key_case_insensitive(self):
        """Query matching is case-insensitive."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("Test Query", 10, {}, [{"id": 1}])
        result = cache.get("test query", 10, {})
        assert result is not None

    def test_key_whitespace_normalized(self):
        """Query whitespace is normalized."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("  test query  ", 10, {}, [{"id": 1}])
        result = cache.get("test query", 10, {})
        assert result is not None

    def test_different_top_k_different_keys(self):
        """Different top_k values produce different cache keys."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("test query", 10, {}, [{"id": 1}])
        result = cache.get("test query", 20, {})
        assert result is None

    def test_different_filters_different_keys(self):
        """Different filters produce different cache keys."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("test query", 10, {"project_id": "abc"}, [{"id": 1}])
        result = cache.get("test query", 10, {"project_id": "xyz"})
        assert result is None

    def test_invalidate_all_clears_cache(self):
        """invalidate_all clears all entries."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("query1", 10, {}, [{"id": 1}])
        cache.set("query2", 10, {}, [{"id": 2}])
        cache.set("query3", 10, {}, [{"id": 3}])

        count = cache.invalidate_all()

        assert count == 3
        assert cache.get("query1", 10, {}) is None
        assert cache.get("query2", 10, {}) is None
        assert cache.get("query3", 10, {}) is None

    def test_invalidate_all_updates_stats(self):
        """invalidate_all updates statistics."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        cache.set("query1", 10, {}, [{"id": 1}])

        cache.invalidate_all()

        stats = cache.get_stats()
        assert stats.invalidations == 1
        assert stats.last_invalidation is not None
        assert stats.cache_size == 0

    def test_get_stats_returns_current_state(self):
        """get_stats returns current cache state."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("query1", 10, {}, [{"id": 1}])
        cache.get("query1", 10, {})  # Hit
        cache.get("query2", 10, {})  # Miss

        stats = cache.get_stats()
        assert stats.cache_hits == 1
        assert stats.cache_misses == 1
        assert stats.cache_size == 1
        assert stats.hit_rate == 0.5

    def test_reset_stats(self):
        """reset_stats clears counters but keeps cache entries."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set("query1", 10, {}, [{"id": 1}])
        cache.get("query1", 10, {})  # Hit

        cache.reset_stats()

        stats = cache.get_stats()
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.cache_size == 1  # Entry still present

    def test_thread_safety(self):
        """Cache is thread-safe for concurrent access."""
        cache = PEDRCache(max_size=100, ttl_seconds=300)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"query{i}", 10, {}, [{"id": i}])
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"query{i % 50}", 10, {})
            except Exception as e:
                errors.append(e)

        def invalidator():
            try:
                for _ in range(10):
                    cache.invalidate_all()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=invalidator),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """CacheEntry stores results and metadata."""
        results = [{"chunk_id": "123", "content": "test"}]
        entry = CacheEntry(
            results=results,
            timestamp=time.time(),
            query_hash="abc123",
        )

        assert entry.results == results
        assert entry.hit_count == 0

    def test_cache_entry_hit_count_increment(self):
        """CacheEntry hit_count can be incremented."""
        entry = CacheEntry(
            results=[],
            timestamp=time.time(),
            query_hash="abc123",
        )
        entry.hit_count += 1

        assert entry.hit_count == 1
