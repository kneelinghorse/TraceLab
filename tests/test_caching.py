"""Unit tests for the application-level caching utilities."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.cache import CacheRegistry, ttl_cache
from app.services.cache_manager import CacheManager


def test_ttl_cache_decorator_deduplicates_calls() -> None:
    registry = CacheRegistry()
    call_count = {"value": 0}

    @ttl_cache("unit-test-cache", ttl_seconds=30, maxsize=32, registry=registry)
    def add(a: int, b: int) -> int:
        call_count["value"] += 1
        return a + b

    assert add(2, 3) == 5
    assert add(2, 3) == 5
    assert call_count["value"] == 1


def test_cache_manager_document_cache_round_trip(tmp_path: Path) -> None:
    registry = CacheRegistry()
    manager = CacheManager(registry=registry, telemetry_path=tmp_path / "caches.jsonl")
    key = manager.document_list_key(
        project_id="project-1",
        processed=True,
        search="Plan",
        page=1,
        page_size=10,
    )
    calls = {"value": 0}

    def _loader() -> dict:
        calls["value"] += 1
        return {"data": [calls["value"]], "pagination": {"page": 1, "pages": 1}}

    _, hit = manager.cached_value("document_lists", key, _loader)
    assert hit is False
    _, hit = manager.cached_value("document_lists", key, _loader)
    assert hit is True
    manager.invalidate_document_lists(project_id="project-1")
    _, hit = manager.cached_value("document_lists", key, _loader)
    assert hit is False
    assert calls["value"] == 2


def test_project_stats_cache_key_is_per_project() -> None:
    """Different projects must get different stats cache keys."""
    key_a = CacheManager.project_metadata_key(kind="stats", identifier="project-aaa")
    key_b = CacheManager.project_metadata_key(kind="stats", identifier="project-bbb")
    assert key_a != key_b
    assert key_a == ("stats", "project-aaa")
    assert key_b == ("stats", "project-bbb")


def test_project_stats_cache_key_differs_from_detail_and_list() -> None:
    """Stats, detail, and list keys must never collide."""
    stats_key = CacheManager.project_metadata_key(kind="stats", identifier="proj-1")
    detail_key = CacheManager.project_metadata_key(kind="detail", identifier="proj-1")
    list_key = CacheManager.project_metadata_key(kind="list", page=1, page_size=20)
    assert stats_key != detail_key
    assert stats_key != list_key
    assert detail_key != list_key


def test_invalidate_project_metadata_clears_stats(tmp_path: Path) -> None:
    """invalidate_project_metadata must clear stats entries for that project."""
    registry = CacheRegistry()
    manager = CacheManager(registry=registry, telemetry_path=tmp_path / "caches.jsonl")

    key_a = manager.project_metadata_key(kind="stats", identifier="proj-a")
    key_b = manager.project_metadata_key(kind="stats", identifier="proj-b")

    manager.cached_value("project_metadata", key_a, lambda: {"docs": 10})
    manager.cached_value("project_metadata", key_b, lambda: {"docs": 5})

    # Both should be cached
    _, hit_a = manager.get_value("project_metadata", key_a)
    _, hit_b = manager.get_value("project_metadata", key_b)
    assert hit_a is True
    assert hit_b is True

    # Invalidate only proj-a
    manager.invalidate_project_metadata("proj-a")

    _, hit_a = manager.get_value("project_metadata", key_a)
    _, hit_b = manager.get_value("project_metadata", key_b)
    assert hit_a is False, "proj-a stats should have been invalidated"
    assert hit_b is True, "proj-b stats should still be cached"


def test_cache_manager_snapshot_writes_telemetry(tmp_path: Path) -> None:
    registry = CacheRegistry()
    telemetry_path = tmp_path / "cache-metrics.jsonl"
    manager = CacheManager(registry=registry, telemetry_path=telemetry_path)
    key = manager.project_metadata_key(kind="detail", identifier="proj-1")
    manager.cached_value("project_metadata", key, lambda: {"id": "proj-1"})

    snapshot = manager.snapshot(log=True)
    assert "project_metadata" in snapshot
    assert telemetry_path.exists()
    lines = telemetry_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "telemetry snapshot not written"
    payload = json.loads(lines[-1])
    assert "caches" in payload
    assert "project_metadata" in payload["caches"]
