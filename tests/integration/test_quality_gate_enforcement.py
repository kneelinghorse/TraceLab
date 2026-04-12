"""Integration tests for automated quality gate enforcement."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.mission import MissionUpdate
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_protocol_service import (
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_gate_service import QualityGateService


def _payload(with_chunk: bool) -> MissionProtocolDraft:
    evidence = {
        "evidence_id": "EV-trace",
        "source": "docs/quality_gates.md",
        "summary": "Traceability requirements",
    }
    if with_chunk:
        evidence["chunk_id"] = str(uuid4())

    return MissionProtocolDraft.model_validate(
        {
            "mission_id": "QA-BLOCK",
            "title": "Quality Enforcement",
            "research_statement": {
                "topic": "Telemetry",
                "objective": "Validate gate blocking",
                "scope": "API",
            },
            "key_questions": [
                {
                    "question": "Are gates blocking?",
                    "status": "answered",
                    "answer": "Yes",
                },
            ],
            "synthesis": {
                "key_insights": [
                    "Mission Protocol only marks review/complete when all gates, including traceability, pass."
                ],
                "recommendations": ["Record telemetry events"],
                "next_steps": ["Expose status endpoint"],
            },
            "evidence": [evidence],
        }
    )


def test_gates_block_completion_until_traceability_ok(db_session, project):
    telemetry_events = []
    service = MissionProtocolService(
        evidence_service=EvidenceLinkingService(require_entities=False),
        quality_gate_service=QualityGateService(telemetry_sink=telemetry_events.append),
    )

    draft = _payload(with_chunk=False)
    mission = service.create_mission_from_draft(
        db_session,
        project_id=project.id,
        draft=draft,
    )

    assert mission.status in {"in_progress", "draft"}
    exec_meta = mission.execution_metadata or {}
    quality_gates = exec_meta.get("quality_gates", {})
    assert "traceability" in quality_gates
    assert quality_gates["traceability"]["status"] == "fail"

    # Update with traceability-passing draft
    update_draft = _payload(with_chunk=True)
    mission.context = update_draft.model_dump(mode="json")
    db_session.commit()

    updated = service.update_mission(
        db_session,
        mission.id,
        MissionUpdate(status="completed"),
    )

    assert updated.status == "completed"
    updated_meta = updated.execution_metadata or {}
    updated_gates = updated_meta.get("quality_gates", {})
    assert updated_gates["traceability"]["status"] == "pass"
    assert any(event["gate"] == "traceability" for event in telemetry_events)


def test_explicit_complete_request_raises_when_gates_fail(db_session, project):
    service = MissionProtocolService(
        evidence_service=EvidenceLinkingService(require_entities=False),
        quality_gate_service=QualityGateService(telemetry_sink=lambda _: None),
    )
    draft = _payload(with_chunk=False)
    mission = service.create_mission_from_draft(
        db_session,
        project_id=project.id,
        draft=draft,
    )

    with pytest.raises(MissionProtocolServiceError):
        service.update_mission(
            db_session,
            mission.id,
            MissionUpdate(status="completed"),
        )
