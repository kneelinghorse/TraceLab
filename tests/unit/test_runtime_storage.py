"""Runtime output must not overwrite the project's historical record."""

import json
import subprocess
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.cli import collect_performance_metrics, pedr
from app.services import cache_manager, correction_queue, evidence_auto_linking, webhook_client
from app.services.coverage_report import CoverageReportGenerator
from app.services.pedr import delta_sync, preflight, search_orchestrator, sync_events

pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[2]


def _assert_runtime_path(path, filename):
    expected = REPO_ROOT / "telemetry" / "runtime" / filename
    assert path.resolve() == expected
    # A correct directory name alone must not leave generated output tracked.
    result = subprocess.run(  # noqa: S603 - fixed Git verb and repository-owned path
        ["git", "check-ignore", "--quiet", str(expected)],  # noqa: S607 - repository Git tool
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("writer,filename", [
    ("cache", "sprint-08-cache-metrics.jsonl"),
    ("evidence", "sprint-10-deepsearch-ingestion.jsonl"),
    ("correction", "sprint-11-corrections.jsonl"),
    ("webhook", "sprint-11-corrections.jsonl"),
    ("delta", "sprint-11-pedr-sync.jsonl"),
    ("events", "sprint-11-pedr-sync.jsonl"),
    ("preflight", "sprint-11-preflight.jsonl"),
    ("graph", "sprint-26-graph-telemetry.jsonl"),
])
def test_default_writers_preserve_historical_receipts(monkeypatch, writer, filename):
    monkeypatch.chdir(REPO_ROOT)
    if writer == "cache":
        path = cache_manager.CacheManager().telemetry_path
    elif writer == "evidence":
        path = evidence_auto_linking.EvidenceAutoLinkingService().telemetry_path
    elif writer == "correction":
        path = correction_queue.CorrectionQueueService(
            auto_linker=object(), webhook_client=object()
        ).telemetry_path
    elif writer == "webhook":
        path = webhook_client.WebhookClient().telemetry_path
    elif writer == "delta":
        monkeypatch.setattr(delta_sync, "_delta_sync_service", None)
        path = delta_sync.get_delta_sync_service().telemetry_path
    elif writer == "events":
        monkeypatch.setattr(sync_events, "_sync_event_emitter", None)
        path = sync_events.get_sync_event_emitter()._telemetry_path
    elif writer == "preflight":
        path = preflight.PreflightService(search_service=object()).TELEMETRY_DIR / filename
    else:
        path = search_orchestrator.GRAPH_TELEMETRY_PATH
    _assert_runtime_path(path, filename)


def test_sync_cli_uses_the_runtime_sink(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    service = Mock()
    service.sync_documents.return_value = SimpleNamespace(
        synced_count=0, failed_count=0, skipped_count=0, duration_ms=0,
        last_sync_at=None, errors=[], success=True,
    )
    factory = Mock(return_value=service)
    monkeypatch.setattr(pedr, "get_delta_sync_service", factory)
    assert pedr.cmd_sync(Namespace(
        full=False, dry_run=True, entity_type="document", project=None,
    )) == 0
    _assert_runtime_path(factory.call_args.kwargs["telemetry_path"], "sprint-11-pedr-sync.jsonl")


def test_metrics_cli_writes_generated_output_outside_the_record(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    metrics = {"collection_info": {"points_count": 0}, "query_latency": []}
    monkeypatch.setattr(collect_performance_metrics, "collect_metrics", lambda: metrics)
    collect_performance_metrics.main()
    output = Path("telemetry/runtime/qdrant_performance.json")
    assert json.loads(output.read_text()) == metrics
    assert not (tmp_path / "cmos").exists()


def test_coverage_report_uses_runtime_storage_without_changing_response(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    db = Mock()
    db.query.return_value.all.return_value = [
        SimpleNamespace(file_path="study.pdf", name="study", processed=True,
                        chunked=True, embedded=True, validation_status="validated"),
        SimpleNamespace(file_path="failed.pdf", name="failed", processed=False,
                        chunked=False, embedded=False, validation_status="flagged"),
    ]
    generator = CoverageReportGenerator()
    assert generator.output_path == Path("telemetry/runtime/ingestion_format_coverage.json")
    result = generator.generate_report(db)
    assert result == json.loads(generator.output_path.read_text())
    assert result["generated_at"].endswith("Z")
    assert result["formats"] == {"PDF": {
        "extension": ".pdf", "total_uploaded": 2, "successfully_processed": 1,
        "failed": 1, "processed": 1, "chunked": 1, "embedded": 1,
        "success_rate_percent": 50.0, "processed_rate_percent": 50.0,
        "chunked_rate_percent": 50.0,
    }}
    assert not (tmp_path / "cmos").exists()
