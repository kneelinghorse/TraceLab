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
