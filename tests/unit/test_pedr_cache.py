"""Unit tests for PEDR cache behavior in production implementation."""

from __future__ import annotations

import pytest

from app.services.pedr.cache import PEDRCache

pytestmark = pytest.mark.unit


def test_lru_eviction_tracks_recent_reads():
    """Most recently accessed entries should be retained on eviction."""
    cache = PEDRCache(max_size=2, ttl_seconds=300)
    cache.set("q1", 5, {"project_id": "p1"}, [{"chunk_id": "1"}])
    cache.set("q2", 5, {"project_id": "p2"}, [{"chunk_id": "2"}])

    # Touch q1 so q2 becomes LRU.
    assert cache.get("q1", 5, {"project_id": "p1"}) is not None

    cache.set("q3", 5, {"project_id": "p3"}, [{"chunk_id": "3"}])

    assert cache.get("q1", 5, {"project_id": "p1"}) is not None
    assert cache.get("q2", 5, {"project_id": "p2"}) is None
    assert cache.get("q3", 5, {"project_id": "p3"}) is not None


def test_get_stats_returns_detached_copy():
    """Mutating returned stats should not alter internal cache counters."""
    cache = PEDRCache(max_size=5, ttl_seconds=300)
    cache.get("missing", 5, {})
    stats = cache.get_stats()
    stats.cache_hits = 999

    fresh = cache.get_stats()
    assert fresh.cache_hits == 0
    assert fresh.cache_misses == 1


def test_invalidate_project_is_scoped():
    """Project invalidation removes only matching project entries."""
    cache = PEDRCache(max_size=5, ttl_seconds=300)
    cache.set("q1", 5, {"project_id": "alpha"}, [{"chunk_id": "a"}])
    cache.set("q2", 5, {"project_id": "beta"}, [{"chunk_id": "b"}])

    removed = cache.invalidate_project("alpha")

    assert removed == 1
    assert cache.get("q1", 5, {"project_id": "alpha"}) is None
    assert cache.get("q2", 5, {"project_id": "beta"}) is not None
