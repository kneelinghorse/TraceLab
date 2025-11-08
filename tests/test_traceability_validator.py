"""Unit tests for the TraceabilityValidator."""
from __future__ import annotations

from uuid import uuid4

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.insight import InsightSource
from app.models.mission_protocol import MissionProtocolDraft
from app.services.traceability_validator import TraceabilityValidator


def test_traceability_validator_detects_missing_chunks_and_low_relevance(db_session, project):
    document = Document(project_id=project.id, name="Transcript", content="raw")
    db_session.add(document)
    db_session.flush()

    chunk_id = uuid4()
    chunk = DocumentChunk(id=chunk_id, document_id=document.id, chunk_index=0, content="chunk body")
    db_session.add(chunk)
    db_session.flush()

    linked_insight = uuid4()
    insight_source = InsightSource(insight_id=linked_insight, chunk_id=chunk_id, relevance_score=0.92)
    db_session.add(insight_source)
    db_session.commit()

    payload = MissionProtocolDraft.model_validate(
        {
            "mission_id": "QA-TRACE",
            "title": "Traceability",
            "research_statement": {
                "topic": "Automation",
                "objective": "Traceability",
                "scope": "Backend",
            },
            "synthesis": {
                "key_insights": ["Traceability validator test"],
                "recommendations": ["Ensure coverage"],
                "next_steps": ["Add validation suite"],
            },
            "evidence": [
                {
                    "evidence_id": "EV-valid",
                    "source": "docs",
                    "summary": "Valid chunk",
                    "chunk_id": str(chunk_id),
                    "insight_id": str(linked_insight),
                    "relevance_score": 0.3,
                },
                {
                    "evidence_id": "EV-missing",
                    "source": "docs",
                    "summary": "Missing chunk",
                    "chunk_id": str(uuid4()),
                    "insight_id": str(uuid4()),
                },
            ],
        }
    )

    validator = TraceabilityValidator()
    result = validator.evaluate(payload, db_session)
    assert result.status == "failed"
    issues = {issue.code for issue in result.issues}
    assert "low_relevance_sources" in issues
    assert "missing_chunks" in issues
    assert "unlinked_insights" in issues
