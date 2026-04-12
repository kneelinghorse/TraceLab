"""Tests for the CostMonitor service."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.services.cost_monitor import CostMonitor


def test_cost_monitor_tracks_usage_and_summary(tmp_path):
    telemetry = tmp_path / "perf.jsonl"
    monitor = CostMonitor(telemetry_path=telemetry, retention_days=3)

    ts = datetime(2025, 1, 5, 12, 30, tzinfo=UTC)
    monitor.track_usage(
        model="gpt-5.1",
        prompt_tokens=1000,
        completion_tokens=500,
        latency_ms=128.4,
        project_id="proj-123",
        query="Measure cache hit rate",
        timestamp=ts,
    )

    summary = monitor.summary()
    assert summary["totals"]["queries"] == 1
    assert summary["totals"]["prompt_tokens"] == 1000
    assert summary["totals"]["completion_tokens"] == 500
    assert summary["totals"]["cost_usd"] == pytest.approx(0.00625)
    assert summary["recent"][0]["model"] == "gpt-5.1"
    assert telemetry.exists()
    with telemetry.open() as handle:
        line = json.loads(handle.readline())
        assert line["model"] == "gpt-5.1"


def test_cost_monitor_retention_and_cache_hits(tmp_path):
    telemetry = tmp_path / "perf.jsonl"
    monitor = CostMonitor(telemetry_path=telemetry, retention_days=1)

    old_ts = datetime.now(UTC) - timedelta(days=2)
    monitor.track_usage(
        model="gpt-5.2", prompt_tokens=2000, completion_tokens=1000, timestamp=old_ts
    )
    monitor.record_cache_hit(
        latency_ms=42.5, project_id="proj-cache", query="cached result"
    )

    summary = monitor.summary()
    assert summary["totals"]["queries"] == 1  # old entry pruned
    assert summary["totals"]["cache_hit_rate"] == pytest.approx(1.0)
