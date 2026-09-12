"""RECOVER-2: real writers preserve analytics fields and isolate sink failures."""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.schemas.corrections import CorrectionErrorType, CorrectionStatus
from app.schemas.pedr_preflight import PreflightRecommendation
from app.services.cache_manager import CacheManager
from app.services.correction_queue import CorrectionQueueService
from app.services.cost_monitor import CostMonitor
from app.services.pedr.delta_sync import DeltaSyncService, EntityType, SyncMode
from app.services.pedr.fusion import LayerResult
from app.services.pedr.preflight import PreflightService
from app.services.pedr.search_orchestrator import (
    LayerTimings,
    PEDRConfig,
    _emit_graph_telemetry,
)
from app.services.quality_checks import _QualityAutomationTelemetry
from app.services.quality_gate_service import _FileTelemetrySink
from app.services.webhook_client import WebhookClient, WebhookDeliveryResult

pytestmark = pytest.mark.unit


@pytest.fixture(params=["cache", "cost", "correction", "sync", "preflight", "automation", "gate", "webhook", "graph"])
def writer(request, tmp_path):
    path = tmp_path / "events" / "sprint-11-preflight.jsonl"
    kind = request.param
    source = "tracelab"
    if kind == "cache":
        service = CacheManager(telemetry_path=path)
        payload = {"caches": {"search": {"hits": 7}}}

        def call():
            return service._write_telemetry(payload["caches"])

        event_type = "cache.metrics.snapshot"
    elif kind == "cost":
        service = CostMonitor(telemetry_path=path)
        payload = {"model": "test-model", "cost": 0.25}

        def call():
            return service._append_telemetry(payload)

        event_type = "cost.monitor.event"
    elif kind == "correction":
        service = CorrectionQueueService(auto_linker=object(), webhook_client=object(), telemetry_path=path)
        item = SimpleNamespace(
            mission_id="RECOVER-2",
            evidence_id="ev-1",
            error_type=next(iter(CorrectionErrorType)),
            retry_count=2,
            best_similarity=0.9,
            similarity_threshold=0.8,
            status=CorrectionStatus.COMPLETED,
        )
        payload = {
            "mission_id": item.mission_id,
            "evidence_id": item.evidence_id,
            "error_type": item.error_type.value,
            "retry_count": 2,
            "similarity": 0.9,
            "threshold": 0.8,
            "status": item.status.value,
            "success": True,
        }

        def call():
            return service._log_telemetry("completed", item)

        event_type = "correction.completed"
    elif kind == "sync":
        service = DeltaSyncService(transformer=object(), telemetry_path=path)
        payload = {
            "entity_type": "document",
            "mode": "delta",
            "synced_count": 3,
            "failed_count": 1,
            "skipped_count": 2,
            "duration_ms": 12.35,
            "success": False,
        }

        def call():
            return service._log_sync_event(EntityType.DOCUMENT, SyncMode.DELTA, 3, 1, 2, 12.345)

        event_type, source = "pedr.delta_sync.completed", "pedr"
    elif kind == "preflight":
        service = PreflightService(search_service=object())
        service.TELEMETRY_DIR = path.parent
        recommendation = PreflightRecommendation(
            action="review",
            summary="Review prior evidence",
            query="café research",
            top_score=0.75,
            match_count=1,
            latency_ms=4,
            filters_applied={"min_quality_gates": 5, "status": ["complete"]},
        )
        payload = {
            "query": "café research",
            "action": "review",
            "top_score": 0.75,
            "match_count": 1,
            "latency_ms": 4,
            "min_quality_gates": 5,
            "status_filters": ["complete"],
            "agent": "recovery",
        }

        def call():
            return service._emit_telemetry(recommendation, "recovery")

        event_type = "preflight.query.completed"
    elif kind == "automation":
        service = _QualityAutomationTelemetry(path)
        record = SimpleNamespace(
            entity_type="mission", entity_id="RECOVER-2", check_type="bias_detection", status="pass"
        )
        result = SimpleNamespace(
            summary="No bias", metrics={"score": 0.95}, recommendations=[], evaluated_at=datetime.now()
        )
        payload = {**vars(record), "summary": result.summary, "metrics": result.metrics, "recommendations": []}

        def call():
            return service(record, result)

        event_type, source = "quality.automation.bias_detection", "quality"
    elif kind == "gate":
        service = _FileTelemetrySink(path)
        original = {"ts": "2026-01-01T00:00:00Z", "gate": "evidence", "status": "pass"}
        payload = {"gate": "evidence", "status": "pass"}

        def call():
            service(original)
            assert original["ts"] == "2026-01-01T00:00:00Z"

        event_type, source = "quality.gate.evaluated", "quality"
    elif kind == "webhook":
        service = WebhookClient(telemetry_path=path)
        result = WebhookDeliveryResult(False, status_code=503, duration_ms=20, attempt=2, error_message="Unavailable")
        payload = {
            "mission_id": "RECOVER-2",
            "evidence_id": "ev-1",
            "notification_type": "failed",
            "success": False,
            "status_code": 503,
            "duration_ms": 20,
            "attempt": 2,
            "error": "Unavailable",
            "context": {},
        }

        def call():
            return service._log_telemetry("failed", payload, result, None)

        event_type = "webhook.failed"
    else:
        graph_layer = LayerResult(
            layer_name="graph",
            results=[],
            weight=0.12,
            metadata={"cache_hits": 3, "cache_misses": 1, "total_candidates": 9},
        )
        fusion = SimpleNamespace(layers_used=["graph"], total_unique=9, fusion_latency_ms=1, telemetry={"fused": True})

        def call():
            return _emit_graph_telemetry(
                query="graph evidence",
                config=PEDRConfig(),
                layer_weights={"graph": 0.12},
                graph_layer=graph_layer,
                fusion_output=fusion,
                final_results=[],
                timings=LayerTimings(graph_ms=2, fusion_ms=1, total_ms=4),
                graph_candidates_expanded=9,
                telemetry_path=path,
            )

        payload = None
        event_type, source = "pedr.graph.telemetry", "pedr"
    return call, path, event_type, source, payload


def test_real_writer_preserves_analytics_contract(writer):
    call, path, event_type, source, payload = writer
    call()
    call()
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(events) == 2, "Writers must append without replacing earlier observations"
    for event in events:
        assert set(event) == {"ts", "event_type", "source", "payload"}
        assert datetime.fromisoformat(event["ts"]).tzinfo is not None
        assert event["event_type"] == event_type
        assert event["source"] == source
        if payload is not None:
            assert event["payload"] == payload
        else:
            assert event["payload"]["graph"]["cache"]["hit_rate"] == 0.75
            assert event["payload"]["graph"]["graph_candidates_expanded"] == 9
            assert event["payload"]["rrf"]["telemetry"] == {"fused": True}
            assert event["payload"]["timings"]["total_ms"] == 4
            assert "ts" not in event["payload"]
            assert "event" not in event["payload"]


def test_sink_failure_does_not_interrupt_caller(writer, caplog):
    call, path, *_ = writer
    path.parent.write_text("A file prevents creation of the telemetry directory")
    call()
    assert "telemetry" in caplog.text.lower()
    assert not path.exists()
