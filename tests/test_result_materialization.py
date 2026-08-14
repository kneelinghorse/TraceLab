from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.models.document import Document
from app.models.mission import Mission
from app.models.report import Report
from app.schemas.webhook import DeepSearchWebhookPayload, DeepSearchWebhookStatus
from app.services.auto_ingest import AutoIngestError, AutoIngestService
from app.services.document_ingestion import DocumentIngestionService
from app.services.result_materialization import MissionResultMaterializationService
from app.services.webhook_handler import WebhookHandler, get_webhook_handler


def _completed_mission(
    db_session,
    project,
    mission_id: str,
    *,
    mission_uuid: uuid.UUID | None = None,
) -> Mission:
    mission = Mission(
        id=mission_uuid,
        project_id=project.id,
        mission_id=mission_id,
        title="Direct-writer result",
        objective="Verify result convergence",
        success_criteria=["Result is materialized exactly once"],
        status="completed",
        deepsearch_job_id=f"job-{mission_id}",
        result_markdown="# Persisted result\n\nDeepSearch wrote this directly.",
        result_protocol={"synthesis": "Persisted protocol"},
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


def _successful_ingestion() -> MagicMock:
    ingestion = MagicMock(spec=DocumentIngestionService)

    def mark_search_ready(*, db, document_id, **_kwargs):
        document = db.query(Document).filter(Document.id == document_id).one()
        document.processed = True
        document.chunked = True
        document.embedded = True
        db.commit()
        return {"status": "completed"}

    ingestion.process_document.side_effect = mark_search_ready
    ingestion.embed_existing_document.side_effect = mark_search_ready
    return ingestion


def _handler() -> WebhookHandler:
    return WebhookHandler(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )


def _signed_receipt(
    mission: Mission,
    signing_key: str,
    *,
    job_id: str | None = None,
) -> tuple[bytes, str]:
    payload = {
        "job_id": job_id
        or mission.deepsearch_job_id
        or f"receipt-{mission.mission_id}",
        "mission_id": mission.mission_id,
        "status": "complete",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()
    return body, f"sha256={digest}"


def test_minimal_hmac_receipt_repairs_direct_writer_result_without_overwrite(
    db_session, project
):
    mission = _completed_mission(db_session, project, f"CONVERGE-{uuid.uuid4().hex}")
    stored_markdown = mission.result_markdown
    stored_protocol = mission.result_protocol
    handler = _handler()
    signing_key = "result-convergence-test-key"
    body, signature = _signed_receipt(mission, signing_key)

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 200
    db_session.refresh(mission)
    assert mission.result_markdown == stored_markdown
    assert mission.result_protocol == stored_protocol
    assert len(mission.result_document_ids) == 1
    assert mission.result_report_id is not None
    assert mission.execution_metadata["result_materialization"]["status"] == "ready"
    assert db_session.query(Document).count() == 1
    assert db_session.query(Report).count() == 1


def test_replayed_receipt_does_not_duplicate_document_or_report(db_session, project):
    mission = _completed_mission(db_session, project, f"REPLAY-{uuid.uuid4().hex}")
    handler = _handler()
    signing_key = "result-replay-test-key"
    body, signature = _signed_receipt(mission, signing_key)

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            client = TestClient(app)
            first = client.post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
            second = client.post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert first.status_code == 200
    assert second.status_code == 200
    db_session.refresh(mission)
    assert len(mission.result_document_ids) == 1
    assert db_session.query(Document).count() == 1
    assert db_session.query(Report).count() == 1


def test_minimal_receipt_preserves_reviewable_validation_failure(db_session, project):
    """A receipt materializes a failed gate result without relabeling its outcome."""
    mission = _completed_mission(db_session, project, f"REVIEW-{uuid.uuid4().hex}")
    mission.status = "validation_failed"
    mission.deepsearch_job_id = None
    db_session.commit()
    handler = _handler()
    signing_key = "validation-failure-receipt-key"
    body, signature = _signed_receipt(mission, signing_key)

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 200
    db_session.refresh(mission)
    assert mission.status == "validation_failed"
    assert mission.deepsearch_job_id is None
    assert len(mission.result_document_ids) == 1
    assert mission.result_report_id is not None


@pytest.mark.parametrize("terminal_status", ["completed", "validation_failed"])
def test_terminal_receipt_rejects_a_mismatched_persisted_job_id(
    db_session,
    project,
    terminal_status,
):
    """An HMAC-valid receipt still must identify the fenced terminal attempt."""
    mission = _completed_mission(db_session, project, f"JOB-MISMATCH-{uuid.uuid4().hex}")
    mission.status = terminal_status
    db_session.commit()
    handler = _handler()
    signing_key = "job-correlation-test-key"
    body, signature = _signed_receipt(
        mission,
        signing_key,
        job_id=f"stale-{mission.deepsearch_job_id}",
    )

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 409
    assert "job_id does not match" in response.json()["detail"]
    db_session.refresh(mission)
    assert mission.status == terminal_status
    assert not mission.result_document_ids
    assert mission.result_report_id is None


def test_minimal_receipt_never_nulls_results_while_transitioning(db_session, project):
    mission = _completed_mission(db_session, project, f"PRESERVE-{uuid.uuid4().hex}")
    mission.status = "in_progress"
    stored_markdown = mission.result_markdown
    stored_protocol = mission.result_protocol
    db_session.commit()

    updated, status = _handler().process_deepsearch_webhook(
        db_session,
        DeepSearchWebhookPayload(
            job_id=mission.deepsearch_job_id,
            mission_id=mission.mission_id,
            status=DeepSearchWebhookStatus.COMPLETE,
        ),
    )

    assert status == "completed"
    assert updated.result_markdown == stored_markdown
    assert updated.result_protocol == stored_protocol
    assert len(updated.result_document_ids) == 1
    assert updated.result_report_id is not None


def test_receipt_resumes_embedding_for_linked_unembedded_document(
    db_session, project
):
    mission = _completed_mission(db_session, project, f"UNREADY-{uuid.uuid4().hex}")
    document = Document(
        project_id=project.id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=mission.id,
        document_metadata={"mission_id": mission.mission_id},
        processed=True,
        chunked=True,
        embedded=False,
    )
    db_session.add(document)
    db_session.flush()
    mission.result_document_ids = [str(document.id)]
    mission.result_protocol = None
    db_session.commit()
    handler = WebhookHandler(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        ),
        auto_report_service=MagicMock(),
    )
    signing_key = "unready-result-test-key"
    body, signature = _signed_receipt(mission, signing_key)

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 200
    db_session.refresh(mission)
    assert mission.status == "completed"
    db_session.refresh(document)
    assert document.embedded is True
    assert db_session.query(Document).count() == 1


def test_receipt_fails_loud_when_embedding_resume_fails(db_session, project):
    mission = _completed_mission(db_session, project, f"EMBED-FAIL-{uuid.uuid4().hex}")
    document = Document(
        project_id=project.id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=mission.id,
        document_metadata={"mission_id": mission.mission_id},
        processed=True,
        chunked=True,
        embedded=False,
    )
    db_session.add(document)
    db_session.flush()
    mission.result_document_ids = [str(document.id)]
    mission.result_protocol = None
    db_session.commit()
    ingestion = MagicMock(spec=DocumentIngestionService)
    ingestion.embed_existing_document.side_effect = RuntimeError("Qdrant unavailable")
    handler = WebhookHandler(
        auto_ingest_service=AutoIngestService(
            ingestion_service=ingestion,
            status_recorder=MagicMock(),
        ),
        auto_report_service=MagicMock(),
    )
    signing_key = "embedding-resume-failure-key"
    body, signature = _signed_receipt(mission, signing_key)

    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 500
    assert "Qdrant unavailable" in response.json()["detail"]
    db_session.refresh(mission)
    assert mission.status == "completed"
    materialization = mission.execution_metadata["result_materialization"]
    assert materialization["status"] == "failed"
    assert materialization["attempt_count"] == 1
    assert "Qdrant unavailable" in materialization["errors"][0]
    assert db_session.query(Document).count() == 1


def test_receipt_fails_loud_when_legacy_links_remain_unresolved(db_session, project):
    """One ready link cannot hide another missing result document."""
    mission = _completed_mission(db_session, project, f"MULTILINK-{uuid.uuid4().hex}")
    ready_document = Document(
        project_id=project.id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=mission.id,
        document_metadata={"mission_id": mission.mission_id},
        processed=True,
        chunked=True,
        embedded=True,
    )
    db_session.add(ready_document)
    db_session.flush()
    mission.result_document_ids = [str(ready_document.id), str(uuid.uuid4())]
    mission.result_protocol = None
    db_session.commit()

    handler = _handler()
    signing_key = "multi-link-receipt-key"
    body, signature = _signed_receipt(mission, signing_key)
    app.dependency_overrides[get_webhook_handler] = lambda: handler
    try:
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = signing_key
            response = TestClient(app).post(
                "/api/v1/webhooks/deepsearch",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-DeepSearch-Signature": signature,
                },
            )
    finally:
        app.dependency_overrides.pop(get_webhook_handler, None)

    assert response.status_code == 500
    assert "remains pending" in response.json()["detail"]
    db_session.refresh(mission)
    materialization = mission.execution_metadata["result_materialization"]
    assert materialization["status"] == "failed"
    assert "remains pending" in materialization["errors"][0]


def test_auto_ingest_retry_reuses_document_created_before_pipeline_failure(
    db_session, project
):
    mission = _completed_mission(db_session, project, f"PARTIAL-{uuid.uuid4().hex}")
    mission.result_protocol = None
    db_session.commit()
    ingestion = MagicMock(spec=DocumentIngestionService)
    ingestion.process_document.side_effect = [
        {"status": "failed", "error": "temporary embedding failure"},
        {"status": "completed"},
    ]
    service = AutoIngestService(
        ingestion_service=ingestion,
        status_recorder=MagicMock(),
    )

    with pytest.raises(AutoIngestError, match="temporary embedding failure"):
        service.auto_ingest_result(db_session, mission, mission.result_markdown)

    partial_document = db_session.query(Document).one()
    assert not mission.result_document_ids

    recovered_document = service.auto_ingest_result(
        db_session, mission, mission.result_markdown
    )

    db_session.refresh(mission)
    assert recovered_document.id == partial_document.id
    assert db_session.query(Document).count() == 1
    assert mission.result_document_ids == [str(partial_document.id)]
    assert ingestion.process_document.call_count == 2


def test_bounded_reconciler_repairs_completed_mission(db_session, project):
    mission = _completed_mission(db_session, project, f"SCAN-{uuid.uuid4().hex}")
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )

    summary = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    assert summary.scanned == 1
    assert summary.repaired == 1
    assert summary.failed == 0
    assert len(mission.result_document_ids) == 1
    assert mission.result_report_id is not None


def test_bounded_reconciler_pages_the_terminal_id_scan(db_session, project):
    """A repair limit must bound memory, not only artifact attempts."""
    _completed_mission(db_session, project, f"SCAN-PAGED-{uuid.uuid4().hex}")
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", capture_statement)
    try:
        service.reconcile_completed(db_session, limit=1)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture_statement)

    terminal_scans = [
        statement
        for statement in statements
        if "missions.status IN" in statement and "ORDER BY" in statement
    ]
    assert terminal_scans
    assert all("LIMIT" in statement.upper() for statement in terminal_scans)


def test_bounded_reconciler_queries_structural_candidates_not_terminal_history(
    db_session, project
):
    """Healthy terminal history cannot consume a recurring repair pass."""
    for index in range(5):
        healthy = _completed_mission(
            db_session,
            project,
            f"SCAN-HEALTHY-{index}-{uuid.uuid4().hex}",
        )
        document = Document(
            project_id=project.id,
            name=f"{healthy.mission_id}_report.md",
            file_type="report",
            content=healthy.result_markdown,
            source_type="deepsearch",
            processed=True,
            chunked=True,
            embedded=True,
        )
        db_session.add(document)
        db_session.flush()
        healthy.result_document_ids = [str(document.id)]
        healthy.result_protocol = None
    repairable = _completed_mission(
        db_session,
        project,
        f"SCAN-STRUCTURAL-{uuid.uuid4().hex}",
    )
    db_session.commit()
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )

    summary = service.reconcile_completed(db_session, limit=1)

    db_session.refresh(repairable)
    assert summary.scanned == 1
    assert summary.eligible == 1
    assert summary.repaired == 1
    assert len(repairable.result_document_ids) == 1


def test_bounded_reconciler_rotates_failures_before_the_next_run(db_session, project):
    """A permanent early failure cannot starve later repairable missions."""
    blocked = _completed_mission(
        db_session,
        project,
        f"SCAN-BLOCKED-{uuid.uuid4().hex}",
        mission_uuid=uuid.UUID(int=1),
    )
    ready_document = Document(
        project_id=project.id,
        name=f"{blocked.mission_id}_report.md",
        file_type="report",
        content=blocked.result_markdown,
        source_type="deepsearch",
        source_mission_id=blocked.id,
        document_metadata={"mission_id": blocked.mission_id},
        processed=True,
        chunked=True,
        embedded=True,
    )
    db_session.add(ready_document)
    db_session.flush()
    blocked.result_document_ids = [str(ready_document.id), str(uuid.uuid4())]
    blocked.result_protocol = None
    repairable = _completed_mission(
        db_session,
        project,
        f"SCAN-NEXT-{uuid.uuid4().hex}",
        mission_uuid=uuid.UUID(int=2),
    )
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )

    first = service.reconcile_completed(db_session, limit=1)
    second = service.reconcile_completed(db_session, limit=1)

    db_session.refresh(repairable)
    assert first.failed == 1
    assert second.failed == 0
    assert second.repaired == 1
    assert len(repairable.result_document_ids) == 1
    assert repairable.result_report_id is not None


def test_bounded_reconciler_attempts_each_mission_once_per_run(db_session, project):
    """Updating retry state cannot re-enqueue the same row inside one scan."""
    blocked = _completed_mission(
        db_session,
        project,
        f"SCAN-ONCE-{uuid.uuid4().hex}",
    )
    ready_document = Document(
        project_id=project.id,
        name=f"{blocked.mission_id}_report.md",
        file_type="report",
        content=blocked.result_markdown,
        source_type="deepsearch",
        source_mission_id=blocked.id,
        document_metadata={"mission_id": blocked.mission_id},
        processed=True,
        chunked=True,
        embedded=True,
    )
    db_session.add(ready_document)
    db_session.flush()
    blocked.result_document_ids = [str(ready_document.id), str(uuid.uuid4())]
    blocked.result_protocol = None
    db_session.commit()
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        ),
        auto_report_service=MagicMock(),
    )

    summary = service.reconcile_completed(db_session, limit=5)

    db_session.refresh(blocked)
    state = blocked.execution_metadata["result_materialization"]
    assert summary.eligible == 1
    assert summary.failed == 1
    assert state["attempt_count"] == 1


def test_bounded_reconciler_repairs_validation_failed_result(db_session, project):
    """Reviewable terminal artifacts receive the same durable materialization."""
    mission = _completed_mission(db_session, project, f"SCAN-REVIEW-{uuid.uuid4().hex}")
    mission.status = "validation_failed"
    db_session.commit()
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        )
    )

    summary = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    assert summary.scanned == 1
    assert summary.repaired == 1
    assert summary.failed == 0
    assert len(mission.result_document_ids) == 1
    assert mission.result_report_id is not None


def test_bounded_reconciler_counts_residual_links_as_failure(db_session, project):
    """A bounded run exits dirty when an attempted mission remains pending."""
    mission = _completed_mission(db_session, project, f"SCAN-LINKS-{uuid.uuid4().hex}")
    ready_document = Document(
        project_id=project.id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=mission.id,
        document_metadata={"mission_id": mission.mission_id},
        processed=True,
        chunked=True,
        embedded=True,
    )
    db_session.add(ready_document)
    db_session.flush()
    mission.result_document_ids = [str(ready_document.id), str(uuid.uuid4())]
    mission.result_protocol = None
    db_session.commit()
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_successful_ingestion(),
            status_recorder=MagicMock(),
        ),
        auto_report_service=MagicMock(),
    )

    summary = service.reconcile_completed(db_session, limit=10)

    assert summary.eligible == 1
    assert summary.repaired == 0
    assert summary.failed == 1
