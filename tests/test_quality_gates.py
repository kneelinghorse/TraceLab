"""Unit tests for individual quality gate validators."""

from __future__ import annotations

from app.models.mission_protocol import MissionProtocolDraft
from app.services import quality_gates


def _base_payload() -> dict:
    return {
        "mission_id": "QA-1",
        "research_statement": {
            "topic": "Traceability",
            "objective": "Enforce evidence coverage",
            "scope": "Backend",
        },
        "synthesis": {
            "key_insights": [
                "Traceability enforcement requires chunk-linked evidence routed through Mission Protocol."
            ],
            "recommendations": ["Publish gate results"],
            "next_steps": ["Expose quality endpoint"],
            "contradictory_information": [],
            "contradiction_resolutions": [],
        },
        "key_questions": [
            {
                "question": "How do gates work?",
                "status": "answered",
                "answer": "Deterministic validators",
            }
        ],
        "evidence": [
            {
                "evidence_id": "EV-1",
                "source": "docs/quality_gates.md",
                "summary": "Quality gates overview",
                "chunk_id": "00000000-0000-0000-0000-000000000010",
            }
        ],
        "quality_checkpoints": [],
    }


def test_research_statement_gate_reports_missing_fields():
    payload = _base_payload()
    payload.pop("research_statement")
    result = quality_gates.check_research_statement_completeness(payload)
    assert result.status == "fail"
    assert set(result.metadata["missing_fields"]) == {"topic", "scope", "hypothesis"}


def test_evidence_links_gate_enforces_threshold():
    mission = MissionProtocolDraft.model_validate(_base_payload())
    mission.evidence = []  # drop evidence entirely
    result = quality_gates.check_evidence_links(mission)
    assert result.status == "fail"
    assert "Mission provides no evidence" in result.details


def test_contradictions_gate_requires_resolution_notes():
    payload = _base_payload()
    payload["synthesis"]["contradictory_information"] = [
        "Interview contradicts survey",
    ]
    result = quality_gates.check_contradictions_resolved(payload)
    assert result.status == "fail"
    assert result.metadata["contradictions"] == 1


def test_traceability_gate_requires_chunk_ids():
    payload = _base_payload()
    payload["evidence"][0].pop("chunk_id")
    result = quality_gates.check_source_traceability(payload)
    assert result.status == "fail"
    assert result.metadata["evidence_ids"] == ["EV-1"]
