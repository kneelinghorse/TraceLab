"""Integration tests for the quality automation workflow."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.insight import Insight, InsightSource
from app.models.mission_protocol import MissionProtocolDraft
from app.models.quality import QualityCheck
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_protocol_service import MissionProtocolService
from app.services.quality_checks import QualityAutomationRunner


def _build_mission_payload(project_id, chunk_id, insight_id):
    return MissionProtocolDraft.model_validate(
        {
            "mission_id": "QA-AUTO",
            "project_id": str(project_id),
            "title": "Quality Automation",
            "research_statement": {
                "topic": "Automation",
                "objective": "Validate automation stack",
                "scope": "Platform",
                "methodology": "qualitative",
            },
            "key_questions": [
                {"question": "Don't you think automation helps?", "status": "open"}
            ],
            "synthesis": {
                "key_insights": [
                    "Automation closes the loop between quality gates and telemetry so researchers act faster."
                ],
                "recommendations": [
                    "Provide dashboards for automation status",
                    "Capture reviewer notes in telemetry",
                ],
                "next_steps": ["Implement dashboards", "review telemetry weekly"],
            },
            "discussion_guide": [
                "Don't you think automation helps?",
                "Walk me through current process gaps.",
            ],
            "methodology_details": {
                "participant_segments": [
                    {"segment": "North America", "percentage": 0.55},
                    {"segment": "Europe", "percentage": 0.45},
                ],
                "validation_steps_completed": [
                    "transcription_validation",
                    "theme_validation",
                ],
            },
            "quality_checkpoints": [
                {"gate": "research_statement", "status": "pass"},
                {"gate": "evidence_links", "status": "pass"},
                {"gate": "synthesis_quality", "status": "pass"},
                {"gate": "traceability", "status": "pass"},
                {"gate": "contradictions_resolved", "status": "pass"},
            ],
            "evidence": [
                {
                    "evidence_id": "EV-automation",
                    "source": "docs/quality_automation.md",
                    "summary": "Traceability sample",
                    "chunk_id": str(chunk_id),
                    "insight_id": str(insight_id),
                    "relevance_score": 0.92,
                }
            ],
        }
    )


def _seed_supporting_documents(db_session, project):
    document = Document(
        project_id=project.id,
        name="Automation Transcript",
        source_type="interview",
        participant_count=4,
        content="Automation transcript content",
        validation_status="validated",
    )
    db_session.add(document)
    db_session.flush()

    chunk_id = uuid4()
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=document.id,
        chunk_index=0,
        content="Automation chunk",
    )
    db_session.add(chunk)
    db_session.flush()

    insight_id = uuid4()
    insight = Insight(
        id=insight_id,
        project_id=project.id,
        title="Quality automation finding",
        content="Automation preserves traceability across quality checks.",
        insight_type="finding",
        created_by="ai",
        validated=True,
    )
    db_session.add(insight)
    db_session.flush()

    insight_source = InsightSource(
        insight_id=insight_id, chunk_id=chunk_id, relevance_score=0.95
    )
    db_session.add(insight_source)
    db_session.commit()
    return chunk_id, insight_id


def test_mission_updates_trigger_quality_automation(db_session, project):
    chunk_id, insight_id = _seed_supporting_documents(db_session, project)
    runner = QualityAutomationRunner(
        async_enabled=False,
        session_factory=sessionmaker(
            bind=db_session.get_bind(),
            join_transaction_mode="create_savepoint",
        ),
    )
    service = MissionProtocolService(
        evidence_service=EvidenceLinkingService(require_entities=False),
        quality_runner=runner,
    )
    mission_payload = _build_mission_payload(project.id, chunk_id, insight_id)
    mission = service.create_mission_from_draft(
        db_session,
        project_id=project.id,
        draft=mission_payload,
    )

    db_session.expire_all()
    records = (
        db_session.query(QualityCheck)
        .filter(QualityCheck.entity_id == mission.id)
        .all()
    )
    assert len(records) == 4  # bias, traceability, rigor, synthesis


def test_quality_automation_api_run_and_history(
    client: TestClient, db_session, project
):
    chunk_id, insight_id = _seed_supporting_documents(db_session, project)
    payload = _build_mission_payload(project.id, chunk_id, insight_id)
    runner = QualityAutomationRunner(
        async_enabled=False,
        session_factory=sessionmaker(
            bind=db_session.get_bind(),
            join_transaction_mode="create_savepoint",
        ),
    )
    service = MissionProtocolService(
        evidence_service=EvidenceLinkingService(require_entities=False),
        quality_runner=runner,
    )
    mission = service.create_mission_from_draft(
        db_session,
        project_id=project.id,
        draft=payload,
    )
    mission_id = mission.id
    baseline_ids = {
        str(check_id)
        for (check_id,) in db_session.query(QualityCheck.id)
        .filter(QualityCheck.entity_id == mission_id)
        .all()
    }
    assert len(baseline_ids) == 4

    # Canonical missions may carry context that is not a Mission Protocol draft.
    # Automation must fall back to canonical columns instead of failing the route.
    mission.context = {"mission_id": "QA-AUTO", "canonical_only": True}
    db_session.commit()

    run_resp = client.post(
        "/api/v1/quality/automated/run",
        json={"mission_id": str(mission_id), "performed_by": "integration_test"},
    )
    assert run_resp.status_code == 201
    body = run_resp.json()
    assert body["mission_id"] == str(mission_id)
    assert len(body["checks"]) == 4
    assert {check["performed_by"] for check in body["checks"]} == {
        "integration_test"
    }
    run_ids = {check["id"] for check in body["checks"]}
    assert run_ids.isdisjoint(baseline_ids)

    history_resp = client.get(
        f"/api/v1/quality/automated/history/{mission_id}?limit=10"
    )
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history["mission_id"] == str(mission_id)
    assert len(history["history"]) == 8
    assert {
        check["id"]
        for check in history["history"]
        if check["performed_by"] == "integration_test"
    } == run_ids
