"""Unit tests for Mission Protocol service operations."""
from __future__ import annotations

from textwrap import dedent
from typing import Any, Dict
from uuid import UUID

import pytest

from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_protocol_service import (
    MissionNotFoundError,
    MissionProtocolService,
)


def _mission_payload(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "mission_id": "B3.2-demo",
        "title": "Protocol Engine",
        "summary": "Implement CRUD + YAML flows",
        "status": "draft",
        "research_statement": {
            "topic": "Mission Protocol",
            "objective": "Ship Protocol Engine",
            "scope": "Backend services",
        },
        "key_questions": [
            {"question": "How do we track progress?", "status": "answered", "answer": "Derived metrics"}
        ],
        "synthesis": {
            "key_insights": [
                "Mission Protocol gating enforces rigor with automated validators and telemetry hooks."
            ],
            "recommendations": ["Document gating outcomes in quality_gates.md"],
            "next_steps": ["Wire UI indicators to the quality status endpoint"],
        },
        "evidence": [
            {
                "evidence_id": "EV-101",
                "source": "docs/mission_protocol_validation.md",
                "summary": "Validation rules",
                "chunk_id": "00000000-0000-0000-0000-000000000001",
            }
        ],
        "quality_checkpoints": [
            {"gate": "research_statement", "status": "pass"},
            {"gate": "evidence_links", "status": "pass"},
            {"gate": "synthesis_quality", "status": "pass"},
            {"gate": "traceability", "status": "pass"},
            {"gate": "contradictions_resolved", "status": "pass"},
        ],
    }
    payload.update(overrides)
    return payload


def _service() -> MissionProtocolService:
    return MissionProtocolService(evidence_service=EvidenceLinkingService(require_entities=False))


def test_create_mission_uses_progress_metrics(db_session, project):
    service = _service()
    draft = MissionProtocolDraft.model_validate(_mission_payload())
    mission = service.create_mission(
        db_session,
        MissionCreate(project_id=project.id, mission_data=draft),
    )
    assert mission.status == "complete"
    assert mission.completion_percentage == 100
    assert mission.quality_gates["research_statement"]["status"] == "pass"


def test_update_mission_promotes_status_when_ready(db_session, project):
    service = _service()
    initial_payload = _mission_payload(
        evidence=[],
        key_questions=[{"question": "Q1", "status": "open"}],
        quality_checkpoints=[],
    )
    draft = MissionProtocolDraft.model_validate(initial_payload)
    mission = service.create_mission(
        db_session,
        MissionCreate(project_id=project.id, mission_data=draft),
    )
    assert mission.status in {"draft", "in_progress"}

    update_payload = MissionProtocolDraft.model_validate(_mission_payload())
    updated = service.update_mission(
        db_session,
        mission.id,
        MissionUpdate(mission_data=update_payload),
    )
    assert updated.status == "complete"
    assert updated.completion_percentage == 100


def test_import_and_export_yaml_round_trip(db_session, project):
    service = _service()
    yaml_text = dedent(
        """
        mission_id: B3.2-import
        title: Imported Mission
        research_statement:
          topic: Mission Protocol
          objective: Import YAML
          scope: Backend
        key_questions:
          - question: How to import?
            status: answered
            answer: Via helper
        synthesis:
          key_insights:
            - YAML works and feeds the automated quality gating pipeline.
          recommendations:
            - Publish the import results to telemetry.
          next_steps:
            - Build UI wiring for quality gates.
        evidence:
          - evidence_id: EV-1
            source: docs
            summary: YAML proof
            chunk_id: 00000000-0000-0000-0000-000000000001
        quality_checkpoints:
          - gate: research_statement
            status: pass
          - gate: evidence_links
            status: pass
          - gate: synthesis_quality
            status: pass
          - gate: traceability
            status: pass
          - gate: contradictions_resolved
            status: pass
        """
    ).strip()

    mission = service.import_mission_yaml(
        db_session,
        project_id=project.id,
        yaml_text=yaml_text,
    )
    exported = service.export_mission_yaml(db_session, mission.id)
    assert "mission_id: B3.2-import" in exported


def test_get_mission_raises_for_missing_record(db_session):
    service = _service()
    with pytest.raises(MissionNotFoundError):
        service.get_mission(db_session, UUID("00000000-0000-0000-0000-000000000000"))
