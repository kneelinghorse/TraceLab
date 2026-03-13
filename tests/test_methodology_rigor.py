"""Unit tests for the MethodologyRigorChecker."""

from __future__ import annotations

from app.models.document import Document
from app.models.mission_protocol import MissionProtocolDraft
from app.services.methodology_rigor import MethodologyRigorChecker


def test_methodology_rigor_flags_sample_and_metadata_gaps(db_session, project):
    doc_a = Document(
        project_id=project.id,
        name="Interview 1",
        source_type=None,
        participant_count=2,
        content="",
        validation_status="pending",
    )
    doc_b = Document(
        project_id=project.id,
        name="Interview 2",
        source_type="interview",
        participant_count=1,
        content="",
        validation_status="validated",
    )
    db_session.add_all([doc_a, doc_b])
    db_session.commit()

    payload = MissionProtocolDraft.model_validate(
        {
            "mission_id": "QA-RIGOR",
            "title": "Rigor",
            "project_id": str(project.id),
            "research_statement": {
                "topic": "Automation",
                "objective": "Validate rigor",
                "scope": "Ops",
                "methodology": "qualitative",
            },
            "synthesis": {
                "key_insights": ["Rigor automation test"],
                "recommendations": ["Add metadata"],
                "next_steps": ["Document recruitment"],
            },
            "evidence": [],
            "methodology_details": {
                "validation_steps_completed": ["transcription_validation"],
            },
        }
    )

    checker = MethodologyRigorChecker()
    result = checker.evaluate(mission=payload, db=db_session)
    assert result.status == "failed"
    codes = {issue.code for issue in result.issues}
    assert "insufficient_sample" in codes
    assert "metadata_gaps" in codes
    assert "missing_validation_steps" in codes
