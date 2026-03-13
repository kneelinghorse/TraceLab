"""Unit tests for Mission Protocol validation framework."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.mission_protocol import (
    MissionProtocolComplete,
    MissionProtocolDraft,
)
from app.services.mission_protocol_validation import (
    build_mission_data_check_constraint,
    promote_to_complete,
)
from app.services.validation_errors import transform_validation_error


def _complete_payload(**overrides):
    payload = {
        "mission_id": "B3.1-demo",
        "title": "Validation Framework",
        "summary": "Implement Mission Protocol validation",
        "status": "complete",
        "research_statement": {
            "topic": "Mission Protocol Integration",
            "objective": "Ship validation framework",
            "scope": "Backend services",
        },
        "key_questions": [
            {
                "question": "What layers are required?",
                "status": "answered",
                "answer": "API + business + DB",
            },
        ],
        "synthesis": {
            "key_insights": [
                "Pydantic + JSON schema keeps parity across API, services, and database layers."
            ],
            "recommendations": [
                "Adopt MissionProtocolDraft and MissionProtocolComplete"
            ],
            "next_steps": ["Publish schema diffs to docs"],
        },
        "evidence": [
            {
                "evidence_id": "EV-1",
                "source": "design-doc",
                "summary": "Architecture doc mandates Pydantic models",
                "chunk_id": "00000000-0000-0000-0000-000000000004",
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


def test_draft_allows_partial_payload():
    """Draft validation should accept payloads with sparse data."""
    draft = MissionProtocolDraft.model_validate({"mission_id": "B3.1-draft"})
    assert draft.key_questions == []
    assert draft.status == "draft"


def test_complete_requires_evidence_and_answered_question():
    """Quality gates trigger when required completion data is missing."""
    payload = _complete_payload(evidence=[])
    with pytest.raises(ValidationError) as excinfo:
        MissionProtocolComplete.model_validate(payload)
    details = transform_validation_error(excinfo.value)["details"]
    assert details[0]["field"] == ""
    assert "evidence" in details[0]["message"].lower()


def test_promote_draft_to_complete_success():
    """Draft payloads containing all fields can be promoted."""
    draft_payload = _complete_payload(status="draft")
    draft = MissionProtocolDraft.model_validate(draft_payload)
    promoted = promote_to_complete(draft)
    assert promoted.status == "complete"
    assert promoted.title == "Validation Framework"


def test_constraint_expression_contains_required_fields():
    """Generated check constraint references schema-derived fields."""
    constraint = build_mission_data_check_constraint()
    assert "mission_id" in constraint
    assert "research_statement" in constraint
    assert "?&" in constraint
