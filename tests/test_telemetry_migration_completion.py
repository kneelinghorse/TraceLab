"""T38.3: Telemetry Migration Completion Tests.

Verifies that all 3 previously non-conforming emitters now produce
TelemetryEnvelope-compliant output:
1. _FileTelemetrySink (quality_gate_service.py)
2. _QualityAutomationTelemetry (quality_checks.py)
3. _emit_graph_telemetry (search_orchestrator.py)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.telemetry import is_envelope_format


class TestQualityGateTelemetryEnvelope:
    """_FileTelemetrySink now emits TelemetryEnvelope format."""

    def test_emits_envelope_format(self, tmp_path):
        from app.services.quality_gate_service import _FileTelemetrySink

        path = tmp_path / "quality-gates.jsonl"
        sink = _FileTelemetrySink(path=path)

        sink({
            "ts": "2026-03-13T00:00:00Z",
            "mission_id": "T38.3",
            "gate": "research_statement",
            "status": "pass",
            "details": "Statement present",
            "metadata": None,
        })

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])

        assert is_envelope_format(event), f"Not envelope format: {event.keys()}"
        assert event["event_type"] == "quality.gate.evaluated"
        assert event["source"] == "quality"
        assert isinstance(event["payload"], dict)
        assert event["payload"]["gate"] == "research_statement"
        assert event["payload"]["status"] == "pass"
        # ts should NOT be in payload (it's at envelope level)
        assert "ts" not in event["payload"]

    def test_multiple_events_all_conform(self, tmp_path):
        from app.services.quality_gate_service import _FileTelemetrySink

        path = tmp_path / "quality-gates.jsonl"
        sink = _FileTelemetrySink(path=path)

        for gate in ["research_statement", "evidence_links", "synthesis_quality"]:
            sink({"gate": gate, "status": "pass", "details": "ok"})

        lines = [l for l in path.read_text().strip().split("\n") if l]
        assert len(lines) == 3
        for line in lines:
            event = json.loads(line)
            assert is_envelope_format(event)


class TestQualityAutomationTelemetryEnvelope:
    """_QualityAutomationTelemetry now emits TelemetryEnvelope format."""

    def test_emits_envelope_format(self, tmp_path):
        from app.services.quality_checks import _QualityAutomationTelemetry

        path = tmp_path / "quality-automation.jsonl"
        sink = _QualityAutomationTelemetry(path=path)

        # Create minimal mock objects with required attributes
        class MockRecord:
            entity_type = "mission"
            entity_id = "test-mission-id"
            check_type = "bias_detection"
            status = "pass"

        class MockResult:
            evaluated_at = datetime(2026, 3, 13, tzinfo=timezone.utc)
            summary = "No bias detected"
            metrics = {"score": 0.95}
            recommendations = []

        sink(MockRecord(), MockResult())

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])

        assert is_envelope_format(event)
        assert event["event_type"] == "quality.automation.bias_detection"
        assert event["source"] == "quality"
        assert event["payload"]["entity_type"] == "mission"
        assert event["payload"]["status"] == "pass"


class TestGraphTelemetryEnvelope:
    """_emit_graph_telemetry now emits TelemetryEnvelope format."""

    def test_emits_envelope_format(self, tmp_path):
        from app.core.telemetry import emit_telemetry

        path = tmp_path / "graph-telemetry.jsonl"

        # Simulate what the migrated _emit_graph_telemetry does
        graph_payload = {
            "query": "test query",
            "graph": {"depth": 2, "decay": 0.7, "total_candidates": 5},
            "rrf": {"k": 60, "layers_used": ["lexical", "semantic", "graph"]},
            "ranking": {"final_result_count": 10},
            "timings": {"graph_ms": 0.5, "fusion_ms": 1.0, "total_ms": 3.0},
        }

        emit_telemetry(
            path=path,
            event_type="pedr.graph.telemetry",
            source="pedr",
            payload=graph_payload,
        )

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])

        assert is_envelope_format(event)
        assert event["event_type"] == "pedr.graph.telemetry"
        assert event["source"] == "pedr"
        assert event["payload"]["query"] == "test query"
        assert event["payload"]["graph"]["total_candidates"] == 5


class TestNoRemainingNonConformingEmitters:
    """Verify there are no raw json.dumps writes to telemetry files in emitter code."""

    def test_quality_gate_sink_uses_emit_telemetry(self):
        """_FileTelemetrySink should import and call emit_telemetry."""
        import inspect
        from app.services.quality_gate_service import _FileTelemetrySink
        source = inspect.getsource(_FileTelemetrySink.__call__)
        assert "emit_telemetry" in source
        assert "json.dumps" not in source

    def test_quality_automation_sink_uses_emit_telemetry(self):
        """_QualityAutomationTelemetry should import and call emit_telemetry."""
        import inspect
        from app.services.quality_checks import _QualityAutomationTelemetry
        source = inspect.getsource(_QualityAutomationTelemetry.__call__)
        assert "emit_telemetry" in source
        assert "json.dumps" not in source

    def test_graph_telemetry_uses_emit_telemetry(self):
        """_emit_graph_telemetry should use emit_telemetry instead of raw file write."""
        import inspect
        from app.services.pedr.search_orchestrator import _emit_graph_telemetry
        source = inspect.getsource(_emit_graph_telemetry)
        assert "emit_telemetry" in source
        assert "handle.write" not in source
