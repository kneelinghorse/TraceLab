"""Integration tests for the Mission Protocol validation pipeline."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.mission import Mission
from app.services.mission_protocol_validation import (
    parse_mission_yaml,
    promote_to_complete,
    validate_mission_payload,
)
from app.services.validation_errors import transform_validation_error

MISSION_YAML = """
mission_id: VAL-123
title: Mission Protocol Validation
status: complete
research_statement:
  topic: Mission Protocol Validation
  objective: Ship validation layers
  scope: Backend + Database
key_questions:
  - question: How will FastAPI enforce validation?
    status: answered
    answer: By binding MissionProtocolDraft in request schemas
synthesis:
  key_insights:
    - MissionProtocolComplete enforces quality gates
  recommendations:
    - Generate JSON Schema from the same models
  next_steps:
    - Wire UI indicators once gates pass
evidence:
  - evidence_id: EV-001
    source: docs/roadmap.md
    summary: Roadmap documents validation requirements
    chunk_id: 00000000-0000-0000-0000-000000000005
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


def test_yaml_to_database_round_trip(db_session, project):
    """Validate YAML parsing through to persisted mission rows."""
    draft = parse_mission_yaml(MISSION_YAML)
    complete = promote_to_complete(draft)

    mission = Mission(
        project_id=project.id,
        mission_data=complete.model_dump(),
        status=complete.status,
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)

    stored = validate_mission_payload(mission.mission_data, state="complete")
    assert stored.title == "Mission Protocol Validation"
    assert stored.evidence[0].evidence_id == "EV-001"


def test_invalid_yaml_reports_structured_error():
    """Invalid YAML payloads surface structured validation errors."""
    with pytest.raises(ValueError):
        parse_mission_yaml("[]")

    with pytest.raises(ValidationError) as excinfo:
        validate_mission_payload({"mission_id": "", "status": "complete"}, state="complete")
    response = transform_validation_error(excinfo.value)
    assert response["error"] == "validation_error"
    assert response["details"]
