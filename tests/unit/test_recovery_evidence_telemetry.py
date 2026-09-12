"""Evidence linking must not fail because an optional telemetry sink is down."""

import json
from types import SimpleNamespace

import pytest

from app.services.evidence_auto_linking import (
    EvidenceAutoLinkingResult,
    EvidenceAutoLinkingService,
)

pytestmark = pytest.mark.unit


def test_auto_linking_telemetry_uses_shared_envelope(tmp_path):
    service = EvidenceAutoLinkingService(telemetry_path=tmp_path / "events.jsonl")
    service._log_telemetry(
        SimpleNamespace(mission_id="RECOVER-1"), None, EvidenceAutoLinkingResult()
    )
    event = json.loads(service.telemetry_path.read_text())
    assert event["event_type"] == "evidence.auto_linking.completed"
    assert event["source"] == "tracelab"
    assert event["payload"]["mission_id"] == "RECOVER-1"
    assert "ts" in event


def test_telemetry_failure_does_not_break_linking(tmp_path):
    path = tmp_path / "file"
    path.write_text("not a directory")
    service = EvidenceAutoLinkingService(telemetry_path=path / "events.jsonl")
    service._log_telemetry(
        SimpleNamespace(mission_id="RECOVER-1"), None, EvidenceAutoLinkingResult()
    )
