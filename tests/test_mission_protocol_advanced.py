"""Expanded tests for Mission Protocol validation helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services import mission_protocol_validation as mp_validation


def _complete_payload(**overrides):
    payload = {
        "mission_id": "B4.4-demo",
        "title": "Testing & Documentation",
        "summary": "Consolidate coverage and docs",
        "status": "complete",
        "research_statement": {
            "topic": "Mission Protocol",
            "objective": "Raise coverage",
            "scope": "Backend",
        },
        "key_questions": [
            {
                "question": "Is coverage above 80%?",
                "status": "answered",
                "answer": "Yes",
            }
        ],
        "synthesis": {
            "key_insights": ["Coverage and docs share a single source"],
            "recommendations": ["Automate validation"],
            "next_steps": ["Publish tutorial"],
        },
        "evidence": [
            {
                "evidence_id": "EV-001",
                "source": "pytest-cov",
                "summary": "Coverage report stored under cmos/reports",
            }
        ],
        "quality_checkpoints": [
            {"gate": gate, "status": "pass"}
            for gate in (
                "research_statement",
                "evidence_links",
                "synthesis_quality",
                "traceability",
                "contradictions_resolved",
            )
        ],
    }
    payload.update(overrides)
    return payload


def test_parse_mission_yaml_requires_object_payload():
    with pytest.raises(ValueError, match="cannot be empty"):
        mp_validation.parse_mission_yaml("   \n")
    with pytest.raises(ValueError, match="must represent an object"):
        mp_validation.parse_mission_yaml("- not-an-object")


def test_validate_mission_payload_enforces_completion_rules():
    payload = _complete_payload(
        quality_checkpoints=[{"gate": "research_statement", "status": "fail"}]
    )
    with pytest.raises(ValidationError):
        mp_validation.validate_mission_payload(payload, state="complete")

    validated = mp_validation.validate_mission_payload(
        _complete_payload(), state="complete"
    )
    assert validated.title == "Testing & Documentation"


def test_sqlite_constraint_includes_structural_guards():
    constraint = mp_validation.build_mission_data_check_constraint(backend="sqlite")
    assert "json_valid" in constraint
    assert (
        "json_array_length(COALESCE(json_extract(mission_data, '$.quality_checkpoints')"
        in constraint
    )
    assert (
        "json_array_length(COALESCE(json_extract(mission_data, '$.key_questions')"
        in constraint
    )


def test_validate_mission_payload_defaults_to_draft_state():
    draft_payload = {"mission_id": "B4.4-draft"}
    draft = mp_validation.validate_mission_payload(draft_payload)
    assert draft.status == "draft"
