"""Tests for the CostMonitor service."""
from datetime import datetime, timedelta, timezone

import json
import pytest

from app.services.cost_monitor import CostMonitor


def test_cost_monitor_tracks_usage_and_summary(tmp_path):
    telemetry = tmp_path / "perf.jsonl"
    monitor = CostMonitor(telemetry_path=telemetry, retention_days=3)

    ts = datetime(2025, 1, 5, 12, 30, tzinfo=timezone.utc)
    monitor.track_usage(
        model="gpt-4o-mini",
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
    assert summary["totals"]["cost_usd"] == pytest.approx(0.00045)
    assert summary["recent"][0]["model"] == "gpt-4o-mini"
    assert telemetry.exists()
    with telemetry.open() as handle:
        line = json.loads(handle.readline())
        assert line["model"] == "gpt-4o-mini"


def test_cost_monitor_retention_and_cache_hits(tmp_path):
    telemetry = tmp_path / "perf.jsonl"
    monitor = CostMonitor(telemetry_path=telemetry, retention_days=1)

    old_ts = datetime.now(timezone.utc) - timedelta(days=2)
    monitor.track_usage(model="gpt-4o", prompt_tokens=2000, completion_tokens=1000, timestamp=old_ts)
    monitor.record_cache_hit(latency_ms=42.5, project_id="proj-cache", query="cached result")

    summary = monitor.summary()
    assert summary["totals"]["queries"] == 1  # old entry pruned
    assert summary["totals"]["cache_hit_rate"] == pytest.approx(1.0)
