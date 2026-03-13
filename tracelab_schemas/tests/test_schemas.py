from tracelab_schemas import (
    MissionProtocolComplete,
    MissionProtocolDraft,
    REQUIRED_COMPLETION_GATES,
)


def _base_payload() -> dict:
    return {
        "mission_id": "B10.3-validation",
        "status": "complete",
        "title": "Validate Schema Package",
        "research_statement": {
            "topic": "Schema sharing",
            "objective": "Ensure package import works",
            "scope": "Local validation script",
        },
        "key_questions": [
            {"question": "Can models validate?", "status": "answered", "answer": "Yes"}
        ],
        "synthesis": {
            "key_insights": ["Schemas validated"],
        },
        "evidence": [
            {
                "evidence_id": "E-1",
                "source": "unit-test",
                "summary": "payload validated",
            }
        ],
        "quality_checkpoints": [
            {"gate": gate, "status": "pass"} for gate in REQUIRED_COMPLETION_GATES
        ],
    }


def test_promote_draft_to_complete() -> None:
    draft = MissionProtocolDraft.model_validate(_base_payload())
    promoted = draft.promote()
    assert isinstance(promoted, MissionProtocolComplete)


def test_complete_payload_round_trip() -> None:
    payload = _base_payload()
    mission = MissionProtocolComplete.model_validate(payload)
    dumped = mission.model_dump()
    assert dumped["mission_id"] == payload["mission_id"]
    assert (
        dumped["quality_checkpoints"][0]["gate"]
        == payload["quality_checkpoints"][0]["gate"]
    )
