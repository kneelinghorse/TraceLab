from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime
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
from app.services.soft_delete_service import DocumentSoftDeleteService
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


def _result_document(
    db_session,
    mission: Mission,
    *,
    ready: bool = True,
    deleted: bool = False,
    linked: bool = True,
) -> Document:
    """Create a DeepSearch result document with explicit live disposition."""
    document = Document(
        project_id=mission.project_id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=mission.id,
        document_metadata={
            "mission_id": mission.mission_id,
            "deepsearch_job_id": mission.deepsearch_job_id,
            "auto_generated": True,
        },
        processed=ready,
        chunked=ready,
        embedded=ready,
    )
    if deleted:
        document.soft_delete(deleted_by="owner@example.com")
    db_session.add(document)
    db_session.flush()
    if linked:
        mission.result_document_ids = [
            *(mission.result_document_ids or []),
            str(document.id),
        ]
    db_session.commit()
    db_session.refresh(document)
    db_session.refresh(mission)
    return document


def _set_retry_state(db_session, mission: Mission, status: str = "failed") -> None:
    mission.execution_metadata = {
        **(mission.execution_metadata or {}),
        "result_materialization": {
            "status": status,
            "attempt_count": 1,
            "attempted_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "error_categories": ["soft_deleted_document"],
        },
    }
    db_session.commit()
    db_session.refresh(mission)


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
    assert response.json()["detail"].endswith("unexpected_ingest_error")
    assert "Qdrant unavailable" not in response.json()["detail"]
    db_session.refresh(mission)
    assert mission.status == "completed"
    materialization = mission.execution_metadata["result_materialization"]
    assert materialization["status"] == "failed"
    assert materialization["attempt_count"] == 1
    assert materialization["error_categories"] == ["unexpected_ingest_error"]
    assert "errors" not in materialization
    assert "Qdrant unavailable" not in json.dumps(materialization)
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
    assert response.json()["detail"].endswith("materialization_incomplete")
    db_session.refresh(mission)
    materialization = mission.execution_metadata["result_materialization"]
    assert materialization["status"] == "failed"
    assert materialization["error_categories"] == ["materialization_incomplete"]
    assert "errors" not in materialization


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

    with pytest.raises(
        AutoIngestError,
        match="temporary embedding failure",
    ) as exc_info:
        service.auto_ingest_result(db_session, mission, mission.result_markdown)

    assert exc_info.value.category == "ingestion_failed"

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


def test_tombstone_batch_converges_once_without_mutating_deleted_documents(
    db_session,
    project,
):
    """Production's ten intentional deletions settle once, then leave the scan."""
    missions: list[Mission] = []
    documents: list[Document] = []
    for index in range(10):
        mission = _completed_mission(
            db_session,
            project,
            f"TOMBSTONE-{index}-{uuid.uuid4().hex}",
        )
        mission.result_protocol = None
        document = _result_document(
            db_session,
            mission,
            deleted=True,
        )
        _set_retry_state(db_session, mission)
        missions.append(mission)
        documents.append(document)

    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    original_deletions = {
        document.id: (document.deleted_at, document.deleted_by)
        for document in documents
    }
    deleted_at_writes: list[tuple[object, object]] = []

    def capture_deleted_at_write(_target, value, old_value, _initiator):
        deleted_at_writes.append((old_value, value))

    event.listen(Document.deleted_at, "set", capture_deleted_at_write)
    try:
        first = service.reconcile_completed(db_session, limit=20)
        second = service.reconcile_completed(db_session, limit=20)
    finally:
        event.remove(Document.deleted_at, "set", capture_deleted_at_write)

    assert first.scanned == 10
    assert first.eligible == 0
    assert first.repaired == 0
    assert first.failed == 0
    assert first.skipped_soft_deleted == 10
    assert second.scanned == 0
    assert second.eligible == 0
    assert second.repaired == 0
    assert second.failed == 0
    assert second.skipped_soft_deleted == 0
    assert deleted_at_writes == []
    auto_ingest.auto_ingest_result.assert_not_called()

    for mission, document in zip(missions, documents, strict=True):
        db_session.refresh(mission)
        db_session.refresh(document)
        assert (document.deleted_at, document.deleted_by) == original_deletions[
            document.id
        ]
        state = mission.execution_metadata["result_materialization"]
        assert set(state) == {
            "status",
            "attempt_count",
            "attempted_at",
            "error_categories",
        }
        assert state["status"] == "blocked_soft_deleted"
        assert isinstance(state["error_categories"], list)
        encoded_state = json.dumps(state)
        assert str(document.id) not in encoded_state
        assert "owner@example.com" not in encoded_state


@pytest.mark.parametrize("renamed", [False, True], ids=["canonical", "renamed"])
def test_unlinked_tombstone_settles_without_recreating_deleted_content(
    db_session,
    project,
    renamed,
):
    """R7 preserves deletion intent even when the deleted result was never linked."""
    mission = _completed_mission(
        db_session,
        project,
        f"UNLINKED-TOMBSTONE-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    deleted = _result_document(db_session, mission, deleted=True, linked=False)
    if renamed:
        deleted.name = "owner-renamed-deepsearch-result.md"
        db_session.commit()
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )

    first = service.reconcile_completed(db_session, limit=10)
    second = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    db_session.refresh(deleted)
    assert first.scanned == 1
    assert first.eligible == 0
    assert first.skipped_soft_deleted == 1
    assert first.failed == 0
    assert second.scanned == 0
    assert mission.result_document_ids in (None, [])
    assert mission.execution_metadata["result_materialization"]["status"] == (
        "blocked_soft_deleted"
    )
    assert deleted.deleted_at is not None
    assert db_session.query(Document).count() == 1
    auto_ingest.auto_ingest_result.assert_not_called()


def test_unrelated_tombstone_with_non_object_metadata_is_ignored(
    db_session,
    project,
):
    """Arbitrary legacy JSON cannot turn an unrelated deletion into a blocker."""
    mission = _completed_mission(
        db_session,
        project,
        f"UNRELATED-TOMBSTONE-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    _result_document(db_session, mission, ready=True)
    unrelated = Document(
        project_id=project.id,
        name="unrelated-deleted-result.md",
        file_type="report",
        content="# Unrelated",
        source_type="deepsearch",
        source_mission_id=None,
        document_metadata=["legacy", "metadata"],
        processed=True,
        chunked=True,
        embedded=True,
    )
    unrelated.soft_delete(deleted_by="owner@example.com")
    db_session.add(unrelated)
    db_session.commit()
    service = MissionResultMaterializationService(
        auto_ingest_service=MagicMock(spec=AutoIngestService),
        auto_report_service=MagicMock(),
    )

    assert service.needs_materialization(db_session, mission) is False
    summary = service.reconcile_completed(db_session, limit=10)

    assert summary.scanned == 0
    assert summary.skipped_soft_deleted == 0
    db_session.refresh(unrelated)
    assert unrelated.deleted_at is not None


def test_any_deleted_link_dominates_missing_links_and_settles(db_session, project):
    """A tombstone prevents recreation even when another linked UUID is missing."""
    mission = _completed_mission(
        db_session,
        project,
        f"TOMBSTONE-DOMINATES-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    deleted = _result_document(db_session, mission, deleted=True)
    missing_id = uuid.uuid4()
    mission.result_document_ids = [str(deleted.id), str(missing_id)]
    db_session.commit()
    _set_retry_state(db_session, mission)
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )

    first = service.reconcile_completed(db_session, limit=10)
    second = service.reconcile_completed(db_session, limit=10)

    assert first.scanned == 1
    assert first.eligible == 0
    assert first.skipped_soft_deleted == 1
    assert first.failed == 0
    assert second.scanned == 0
    assert db_session.query(Document).count() == 1
    db_session.refresh(deleted)
    assert deleted.deleted_at is not None
    auto_ingest.auto_ingest_result.assert_not_called()


def test_candidate_tombstoned_after_precheck_counts_as_skipped(
    db_session,
    project,
    monkeypatch,
):
    """Batch accounting follows the disposition observed at materialization time."""
    mission = _completed_mission(
        db_session,
        project,
        f"TOMBSTONE-RACE-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    document = _result_document(db_session, mission, ready=False)
    _set_retry_state(db_session, mission)
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    materialize = service.materialize

    def tombstone_before_materialize(db, selected_mission):
        document.soft_delete(deleted_by="owner@example.com")
        db.commit()
        return materialize(db, selected_mission)

    monkeypatch.setattr(service, "materialize", tombstone_before_materialize)

    summary = service.reconcile_completed(db_session, limit=10)

    assert summary.scanned == 1
    assert summary.eligible == 0
    assert summary.repaired == 0
    assert summary.failed == 0
    assert summary.skipped_soft_deleted == 1
    auto_ingest.auto_ingest_result.assert_not_called()


def test_tombstoned_document_does_not_block_report_materialization(
    db_session,
    project,
):
    """The report side can repair while document deletion intent remains blocked."""
    mission = _completed_mission(
        db_session,
        project,
        f"TOMBSTONE-REPORT-{uuid.uuid4().hex}",
    )
    deleted = _result_document(db_session, mission, deleted=True)
    _set_retry_state(db_session, mission)
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(auto_ingest_service=auto_ingest)

    first = service.reconcile_completed(db_session, limit=10)
    second = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    db_session.refresh(deleted)
    assert first.scanned == 1
    assert first.eligible == 1
    assert first.repaired == 1
    assert first.failed == 0
    assert first.skipped_soft_deleted == 0
    assert mission.result_report_id is not None
    assert mission.execution_metadata["result_materialization"]["status"] == (
        "blocked_soft_deleted"
    )
    assert deleted.deleted_at is not None
    assert second.scanned == 0
    auto_ingest.auto_ingest_result.assert_not_called()


def test_restored_ready_document_reenters_live_classification_without_work(
    db_session,
    project,
):
    mission = _completed_mission(
        db_session,
        project,
        f"RESTORE-READY-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    document = _result_document(db_session, mission, ready=True, deleted=True)
    _set_retry_state(db_session, mission)
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )

    blocked = service.reconcile_completed(db_session, limit=10)
    with patch(
        "app.services.soft_delete_service.invalidate_pedr_cache",
        return_value=0,
    ):
        assert DocumentSoftDeleteService().restore_document(db_session, document.id)
    restored = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    db_session.refresh(document)
    assert blocked.skipped_soft_deleted == 1
    assert restored.scanned == 1
    assert restored.eligible == 0
    assert restored.failed == 0
    assert mission.execution_metadata["result_materialization"]["status"] == "ready"
    assert document.deleted_at is None
    assert document.deleted_by is None
    assert service.needs_materialization(db_session, mission) is False
    auto_ingest.auto_ingest_result.assert_not_called()


def test_restored_unready_document_becomes_eligible_and_repairs(
    db_session,
    project,
):
    mission = _completed_mission(
        db_session,
        project,
        f"RESTORE-UNREADY-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    document = _result_document(db_session, mission, ready=False, deleted=True)
    _set_retry_state(db_session, mission)
    ingestion = _successful_ingestion()
    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=ingestion,
            status_recorder=MagicMock(),
        ),
        auto_report_service=MagicMock(),
    )

    blocked = service.reconcile_completed(db_session, limit=10)
    with patch(
        "app.services.soft_delete_service.invalidate_pedr_cache",
        return_value=0,
    ):
        assert DocumentSoftDeleteService().restore_document(db_session, document.id)
    repaired = service.reconcile_completed(db_session, limit=10)

    db_session.refresh(mission)
    db_session.refresh(document)
    assert blocked.skipped_soft_deleted == 1
    assert repaired.scanned == 1
    assert repaired.eligible == 1
    assert repaired.repaired == 1
    assert repaired.failed == 0
    assert repaired.skipped_soft_deleted == 0
    assert document.deleted_at is None
    assert document.processed is True
    assert document.chunked is True
    assert document.embedded is True
    assert db_session.query(Document).count() == 1
    assert mission.execution_metadata["result_materialization"]["status"] == "ready"
    ingestion.process_document.assert_called_once()


def test_terminal_tombstone_webhook_replay_acknowledges_without_mutation(
    db_session,
    project,
):
    mission = _completed_mission(
        db_session,
        project,
        f"TOMBSTONE-REPLAY-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    document = _result_document(db_session, mission, deleted=True)
    deleted_at = document.deleted_at
    handler = _handler()
    signing_key = "tombstone-replay-key"
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
    assert response.json()["status"] == "completed"
    assert response.json()["message"] == "Webhook already processed (idempotent)"
    db_session.refresh(document)
    assert document.deleted_at == deleted_at
    assert db_session.query(Document).count() == 1
    assert db_session.query(Report).count() == 0


@pytest.mark.parametrize(
    "persisted_status",
    ["in_progress", "completed"],
    ids=["initial-complete", "terminal-replay"],
)
def test_webhook_materializer_exception_is_category_only(
    db_session,
    project,
    persisted_status,
):
    """Both completion paths hide private exception details and identifiers."""
    mission = _completed_mission(
        db_session,
        project,
        f"MATERIALIZER-EXCEPTION-{persisted_status}-{uuid.uuid4().hex}",
    )
    mission.status = persisted_status
    db_session.commit()
    private_id = uuid.uuid4()
    handler = _handler()
    materializer = MagicMock(spec=MissionResultMaterializationService)
    materializer.materialize.side_effect = RuntimeError(
        f"private provider failure for document {private_id}"
    )
    handler._materialization_service = materializer
    signing_key = f"materializer-exception-{persisted_status}"
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
    assert response.json()["detail"] == (
        "Mission completed but result materialization is incomplete: "
        "unexpected_materialization_error"
    )
    assert str(private_id) not in response.text
    assert "private provider failure" not in response.text
    materializer.materialize.assert_called_once()


@pytest.mark.parametrize("falsey_protocol", [{}, [], "", 0, False])
def test_falsey_protocol_does_not_remain_a_structural_candidate(
    db_session,
    project,
    falsey_protocol,
):
    """Empty protocol JSON cannot create a perpetual healthy-row scan."""
    mission = _completed_mission(
        db_session,
        project,
        f"FALSEY-PROTOCOL-{uuid.uuid4().hex}",
    )
    mission.result_markdown = None
    mission.result_protocol = falsey_protocol
    db_session.commit()
    baseline_updated_at = mission.updated_at
    baseline_metadata = json.loads(json.dumps(mission.execution_metadata or {}))
    auto_ingest = MagicMock(spec=AutoIngestService)
    auto_report = MagicMock()
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=auto_report,
    )

    first = service.reconcile_completed(db_session, limit=10)
    db_session.refresh(mission)
    settled_updated_at = mission.updated_at
    settled_metadata = json.loads(json.dumps(mission.execution_metadata or {}))
    second = service.reconcile_completed(db_session, limit=10)
    db_session.refresh(mission)

    assert first.scanned == 0
    assert first.eligible == 0
    assert first.failed == 0
    assert second.scanned == 0
    assert second.eligible == 0
    assert second.repaired == 0
    assert second.failed == 0
    assert settled_updated_at == baseline_updated_at
    assert settled_metadata == baseline_metadata
    assert mission.updated_at == settled_updated_at
    assert (mission.execution_metadata or {}) == settled_metadata
    assert db_session.query(Document).count() == 0
    assert db_session.query(Report).count() == 0
    auto_ingest.auto_ingest_result.assert_not_called()
    auto_report.create_report_from_protocol.assert_not_called()


@pytest.mark.parametrize("stale_status", ["failed", "pending"])
def test_stale_retry_state_heals_once_without_updated_at_churn(
    db_session,
    project,
    stale_status,
):
    mission = _completed_mission(
        db_session,
        project,
        f"STALE-{stale_status}-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    _result_document(db_session, mission, ready=True)
    _set_retry_state(db_session, mission, stale_status)
    service = MissionResultMaterializationService(
        auto_ingest_service=MagicMock(spec=AutoIngestService),
        auto_report_service=MagicMock(),
    )

    healed = service.reconcile_completed(db_session, limit=10)
    db_session.refresh(mission)
    healed_updated_at = mission.updated_at
    healed_state = json.loads(
        json.dumps(mission.execution_metadata["result_materialization"])
    )
    no_op = service.materialize(db_session, mission)
    db_session.refresh(mission)
    steady = service.reconcile_completed(db_session, limit=10)

    assert healed.scanned == 1
    assert healed.eligible == 0
    assert healed.failed == 0
    assert mission.execution_metadata["result_materialization"]["status"] == "ready"
    assert no_op.changed is False
    assert no_op.errors == []
    assert mission.updated_at == healed_updated_at
    assert mission.execution_metadata["result_materialization"] == healed_state
    assert steady.scanned == 0


def test_hard_deleted_candidate_disappearing_mid_scan_is_skipped(
    db_session,
    project,
    monkeypatch,
):
    mission = _completed_mission(
        db_session,
        project,
        f"HARD-DELETE-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    db_session.commit()
    mission_id = mission.id
    original_query = db_session.query
    mission_lookup = MagicMock()
    mission_lookup.filter.return_value = mission_lookup

    def delete_before_load():
        original_query(Mission).filter(Mission.id == mission_id).delete(
            synchronize_session=False
        )
        db_session.flush()
        db_session.expunge(mission)
        return None

    mission_lookup.one_or_none.side_effect = delete_before_load

    def query_with_disappearing_mission(*entities, **kwargs):
        if entities == (Mission,):
            return mission_lookup
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db_session, "query", query_with_disappearing_mission)
    service = MissionResultMaterializationService()

    summary = service.reconcile_completed(db_session, limit=10)

    assert summary.scanned == 1
    assert summary.eligible == 0
    assert summary.repaired == 0
    assert summary.failed == 0
    assert summary.skipped_soft_deleted == 0
    assert original_query(Mission).filter(Mission.id == mission_id).count() == 0


def test_tombstone_evidence_surfaces_are_counts_only(
    db_session,
    project,
    monkeypatch,
    caplog,
):
    from app.services import reconciler_scheduler as scheduler

    mission = _completed_mission(
        db_session,
        project,
        f"TOMBSTONE-EVIDENCE-{uuid.uuid4().hex}",
    )
    mission.result_protocol = None
    document = _result_document(db_session, mission, deleted=True)
    _set_retry_state(db_session, mission)
    summary = MissionResultMaterializationService().reconcile_completed(
        db_session,
        limit=10,
    )
    counts = {
        "scanned": summary.scanned,
        "eligible": summary.eligible,
        "repaired": summary.repaired,
        "failed": summary.failed,
        "skipped_soft_deleted": summary.skipped_soft_deleted,
    }
    previous_state = scheduler._state
    scheduler._state = scheduler.ReconcilerState()
    monkeypatch.setattr(scheduler, "run_reconciliation_once", lambda: counts)
    try:
        with caplog.at_level(logging.INFO, logger=scheduler.__name__):
            import asyncio

            asyncio.run(scheduler.run_tick())
        health_body = TestClient(app).get("/api/v1/health").json()
    finally:
        scheduler._state = previous_state

    reconciler_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("reconciler_run")
    ]
    reconciler_lines = [record.getMessage() for record in reconciler_records]
    assert len(reconciler_lines) == 1
    assert reconciler_records[0].levelno == logging.INFO
    assert "skipped_soft_deleted=1" in reconciler_lines[0]
    assert str(document.id) not in reconciler_lines[0]
    assert str(document.id) not in json.dumps(health_body["reconciler"])
    db_session.refresh(mission)
    persisted = json.dumps(mission.execution_metadata["result_materialization"])
    assert str(document.id) not in persisted
    assert "owner@example.com" not in persisted
