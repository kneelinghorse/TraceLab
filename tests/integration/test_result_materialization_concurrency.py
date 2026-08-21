"""PostgreSQL concurrency contract for terminal result materialization."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.services.auto_ingest import AutoIngestService
from app.services.result_materialization import MissionResultMaterializationService

pytestmark = pytest.mark.integration


class _SuccessfulSlowIngestion:
    """Hold the first materialization open long enough to exercise contention."""

    def process_document(self, *, db, document_id, **_kwargs):
        time.sleep(0.15)
        document = db.query(Document).filter(Document.id == document_id).one()
        document.processed = True
        document.chunked = True
        document.embedded = True
        db.commit()
        return {"status": "completed"}

    def embed_existing_document(self, *, db, document_id):
        return self.process_document(db=db, document_id=document_id)


def _active_result_protocol() -> dict[str, object]:
    """Return a protocol that was substantive but skeletal under formatter v1."""
    return {
        "synthesis": {
            "key_insights": ["PostgreSQL repair preserves this insight."],
            "recommendations": ["Repair the linked row in place."],
        },
        "quality_checkpoints": [
            {"gate": "traceability", "status": "pass"},
        ],
    }


def test_concurrent_receipts_create_one_document_and_report(pg_engine):
    """Receipt plus reconciler contention is serialized for one mission UUID."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"Materialization concurrency {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"CONCURRENT-{uuid4().hex}",
        title="Concurrent materialization",
        objective="Create each terminal artifact exactly once under contention.",
        success_criteria=["One document and one report exist"],
        status="completed",
        result_markdown="# Concurrent result",
        result_protocol={"synthesis": "Concurrent result"},
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    seed.close()

    service = MissionResultMaterializationService(
        auto_ingest_service=AutoIngestService(
            ingestion_service=_SuccessfulSlowIngestion(),
            status_recorder=MagicMock(),
        )
    )
    barrier = Barrier(2)

    def run_once():
        db = session_factory()
        try:
            current = db.query(Mission).filter(Mission.id == mission_id).one()
            barrier.wait(timeout=5)
            return service.materialize(db, current)
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: run_once(), range(2)))

        verify = session_factory()
        try:
            persisted = verify.query(Mission).filter(Mission.id == mission_id).one()
            assert verify.query(Document).filter(Document.source_mission_id == mission_id).count() == 1
            assert verify.query(Report).filter(Report.id == persisted.result_report_id).count() == 1
            assert len(persisted.result_document_ids) == 1
            assert sum(outcome.changed for outcome in outcomes) == 1
        finally:
            verify.close()
    finally:
        cleanup = session_factory()
        try:
            cleanup.query(Document).filter(Document.source_mission_id == mission_id).delete()
            cleanup.query(Report).filter(Report.project_id == project.id).delete()
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project.id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_reconciler_repairs_linked_legacy_report_once(pg_engine):
    """The real JSONB candidate scan finds one v1 draft, then converges."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG report repair {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-REPORT-REPAIR-{uuid4().hex}",
        title="PostgreSQL linked report repair",
        objective="Repair the existing generated report without new artifacts.",
        success_criteria=["The second pass has no candidate"],
        status="completed",
        result_markdown="# Already materialized and searchable",
        result_protocol=_active_result_protocol(),
    )
    seed.add(mission)
    seed.flush()
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
        embedded=True,
    )
    report = Report(
        project_id=project.id,
        title=f"Research: {mission.title}",
        report_type="markdown",
        prompt=f"Auto-generated from mission {mission.mission_id}",
        content=(
            f"# Research: {mission.title}\n\n"
            "## Quality Checkpoints\n\n"
            "- [ ] Checkpoint\n\n"
            "---\n"
            "*Generated automatically from DeepSearch results at "
            "2026-08-21T12:00:00Z*"
        ),
        status="draft",
    )
    seed.add_all([document, report])
    seed.flush()
    source_id = uuid4()
    seed.add(
        ReportSource(
            report_id=report.id,
            source_type="chunk",
            source_id=source_id,
        )
    )
    mission.result_document_ids = [str(document.id)]
    mission.result_report_id = report.id
    seed.commit()
    mission_id = mission.id
    document_id = document.id
    report_id = report.id
    project_id = project.id
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(auto_ingest_service=auto_ingest)

    try:
        first = service.reconcile_completed(seed, limit=10)
        second = service.reconcile_completed(seed, limit=10)

        seed.expire_all()
        persisted = seed.query(Mission).filter(Mission.id == mission_id).one()
        repaired_report = seed.query(Report).filter(Report.id == report_id).one()
        persisted_sources = (
            seed.query(ReportSource)
            .filter(ReportSource.report_id == report_id)
            .all()
        )
        assert first.scanned == 1
        assert first.eligible == 1
        assert first.repaired == 1
        assert first.failed == 0
        assert second.scanned == 0
        assert second.eligible == 0
        assert persisted.result_document_ids == [str(document_id)]
        assert persisted.result_report_id == report_id
        assert "PostgreSQL repair preserves this insight." in repaired_report.content
        assert "Repair the linked row in place." in repaired_report.content
        assert "[tracelab-auto-report:v2]" in repaired_report.prompt
        assert len(persisted_sources) == 1
        assert persisted_sources[0].source_id == source_id
        assert (
            seed.query(Document)
            .filter(Document.source_mission_id == mission_id)
            .count()
            == 1
        )
        assert seed.query(Report).filter(Report.project_id == project_id).count() == 1
        auto_ingest.auto_ingest_result.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(ReportSource).filter(
                ReportSource.report_id == report_id
            ).delete()
            cleanup.query(Document).filter(Document.id == document_id).delete()
            cleanup.query(Report).filter(Report.id == report_id).delete()
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_concurrent_linked_legacy_report_repair_updates_same_row_once(pg_engine):
    """The advisory lock serializes two repairers around the existing report ID."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"Concurrent report repair {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"CONCURRENT-RPT-{uuid4().hex}",
        title="Concurrent linked report repair",
        objective="Update one generated report under contention.",
        success_criteria=["Exactly one repair changes the existing row"],
        status="completed",
        result_markdown="# Existing searchable result",
        result_protocol=_active_result_protocol(),
    )
    seed.add(mission)
    seed.flush()
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
        embedded=True,
    )
    report = Report(
        project_id=project.id,
        title=f"Research: {mission.title}",
        report_type="markdown",
        prompt=f"Auto-generated from mission {mission.mission_id}",
        content=(
            f"# Research: {mission.title}\n\n"
            "## Quality Checkpoints\n\n"
            "- [ ] Checkpoint\n\n"
            "---\n"
            "*Generated automatically from DeepSearch results at "
            "2026-08-21T12:00:00Z*"
        ),
        status="draft",
    )
    seed.add_all([document, report])
    seed.flush()
    source_id = uuid4()
    seed.add(
        ReportSource(
            report_id=report.id,
            source_type="chunk",
            source_id=source_id,
        )
    )
    mission.result_document_ids = [str(document.id)]
    mission.result_report_id = report.id
    seed.commit()
    mission_id = mission.id
    document_id = document.id
    report_id = report.id
    project_id = project.id
    seed.close()
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(auto_ingest_service=auto_ingest)
    barrier = Barrier(2)

    def repair_once():
        db = session_factory()
        try:
            current = db.query(Mission).filter(Mission.id == mission_id).one()
            barrier.wait(timeout=5)
            return service.materialize(db, current)
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: repair_once(), range(2)))

        verify = session_factory()
        try:
            persisted = verify.query(Mission).filter(Mission.id == mission_id).one()
            repaired_report = verify.query(Report).filter(Report.id == report_id).one()
            persisted_sources = (
                verify.query(ReportSource)
                .filter(ReportSource.report_id == report_id)
                .all()
            )
            assert sum(outcome.changed for outcome in outcomes) == 1
            assert all(outcome.errors == [] for outcome in outcomes)
            assert persisted.result_document_ids == [str(document_id)]
            assert persisted.result_report_id == report_id
            assert "PostgreSQL repair preserves this insight." in repaired_report.content
            assert "[tracelab-auto-report:v2]" in repaired_report.prompt
            assert len(persisted_sources) == 1
            assert persisted_sources[0].source_id == source_id
            assert (
                verify.query(Document)
                .filter(Document.source_mission_id == mission_id)
                .count()
                == 1
            )
            assert (
                verify.query(Report).filter(Report.project_id == project_id).count()
                == 1
            )
            auto_ingest.auto_ingest_result.assert_not_called()
        finally:
            verify.close()
    finally:
        cleanup = session_factory()
        try:
            cleanup.query(ReportSource).filter(
                ReportSource.report_id == report_id
            ).delete()
            cleanup.query(Document).filter(Document.id == document_id).delete()
            cleanup.query(Report).filter(Report.id == report_id).delete()
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_jsonb_tombstone_settles_mixed_links_once(pg_engine):
    """The PostgreSQL JSONB candidate query honors any-deleted dominance."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG tombstone {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-TOMBSTONE-{uuid4().hex}",
        title="PostgreSQL tombstone convergence",
        objective="Settle a deleted result without recreating it.",
        success_criteria=["The second scan sees no candidate"],
        status="completed",
        result_markdown="# Deleted result",
        result_protocol=None,
        execution_metadata={
            "result_materialization": {
                "status": "failed",
                "attempt_count": 1,
                "attempted_at": "2026-01-01T00:00:00+00:00",
                "error_categories": ["soft_deleted_document"],
            }
        },
    )
    seed.add(mission)
    seed.flush()
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
        embedded=True,
    )
    document.soft_delete(deleted_by="owner@example.com")
    seed.add(document)
    seed.flush()
    mission.result_document_ids = [str(document.id), str(uuid4())]
    seed.commit()
    mission_id = mission.id
    document_id = document.id
    project_id = project.id

    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    try:
        first = service.reconcile_completed(seed, limit=10)
        second = service.reconcile_completed(seed, limit=10)

        seed.expire_all()
        persisted = seed.query(Mission).filter(Mission.id == mission_id).one()
        assert first.scanned == 1
        assert first.eligible == 0
        assert first.repaired == 0
        assert first.failed == 0
        assert first.skipped_soft_deleted == 1
        assert second.scanned == 0
        assert second.skipped_soft_deleted == 0
        assert persisted.execution_metadata["result_materialization"]["status"] == (
            "blocked_soft_deleted"
        )
        assert seed.query(Document).filter(Document.id == document_id).one().deleted_at
        auto_ingest.auto_ingest_result.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Document).filter(Document.id == document_id).delete()
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


@pytest.mark.parametrize("renamed", [False, True], ids=["canonical", "renamed"])
def test_postgres_unlinked_legacy_tombstone_settles_without_recreation(
    pg_engine,
    renamed,
):
    """R7's legacy JSONB provenance blocks an unlinked deleted result once."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG unlinked tombstone {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-UL-{uuid4().hex}",
        title="PostgreSQL unlinked tombstone convergence",
        objective="Honor a deleted legacy result that was never linked.",
        success_criteria=["The second scan sees no candidate"],
        status="completed",
        result_markdown="# Deleted legacy result",
        result_protocol=None,
        result_document_ids=[],
    )
    seed.add(mission)
    seed.flush()
    document = Document(
        project_id=project.id,
        name=f"{mission.mission_id}_report.md",
        file_type="report",
        content=mission.result_markdown,
        source_type="deepsearch",
        source_mission_id=None,
        document_metadata={"mission_id": mission.mission_id},
        processed=True,
        chunked=True,
        embedded=True,
    )
    document.soft_delete(deleted_by="owner@example.com")
    seed.add(document)
    if renamed:
        document.name = "owner-renamed-deepsearch-result.md"
    seed.commit()
    mission_id = mission.id
    document_id = document.id
    project_id = project.id

    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    try:
        first = service.reconcile_completed(seed, limit=10)
        second = service.reconcile_completed(seed, limit=10)

        seed.expire_all()
        persisted = seed.query(Mission).filter(Mission.id == mission_id).one()
        persisted_document = (
            seed.query(Document).filter(Document.id == document_id).one()
        )
        assert first.scanned == 1
        assert first.eligible == 0
        assert first.repaired == 0
        assert first.failed == 0
        assert first.skipped_soft_deleted == 1
        assert second.scanned == 0
        assert second.skipped_soft_deleted == 0
        assert persisted.result_document_ids in (None, [])
        assert persisted.execution_metadata["result_materialization"]["status"] == (
            "blocked_soft_deleted"
        )
        assert persisted_document.deleted_at is not None
        assert (
            seed.query(Document)
            .filter(
                Document.project_id == project_id,
                Document.name == persisted_document.name,
            )
            .count()
            == 1
        )
        auto_ingest.auto_ingest_result.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Document).filter(Document.id == document_id).delete()
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


@pytest.mark.parametrize("falsey_protocol", [{}, [], "", 0, False])
def test_postgres_falsey_protocol_is_never_a_structural_candidate(
    pg_engine,
    falsey_protocol,
):
    """PostgreSQL JSONB truthiness matches Python artifact eligibility."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG falsey protocol {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-FP-{uuid4().hex}",
        title="PostgreSQL falsey protocol",
        objective="Do not repeatedly scan empty structured results.",
        success_criteria=["Both reconciliation passes scan zero rows"],
        status="completed",
        result_markdown=None,
        result_protocol=falsey_protocol,
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    baseline_updated_at = mission.updated_at
    baseline_metadata = deepcopy(mission.execution_metadata or {})
    auto_ingest = MagicMock(spec=AutoIngestService)
    auto_report = MagicMock()
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=auto_report,
    )

    try:
        first = service.reconcile_completed(seed, limit=10)
        second = service.reconcile_completed(seed, limit=10)

        seed.refresh(mission)
        assert first.scanned == 0
        assert second.scanned == 0
        assert first.eligible == second.eligible == 0
        assert first.failed == second.failed == 0
        assert mission.updated_at == baseline_updated_at
        assert (mission.execution_metadata or {}) == baseline_metadata
        assert seed.query(Document).filter(Document.source_mission_id == mission_id).count() == 0
        assert seed.query(Report).filter(Report.project_id == project_id).count() == 0
        auto_ingest.auto_ingest_result.assert_not_called()
        auto_report.create_report_from_protocol.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_hard_delete_between_scan_and_lock_reload_is_skipped(
    pg_engine,
    monkeypatch,
):
    """A row deleted after outer load cannot abort the production PG batch."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG hard-delete race {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-HARD-DELETE-{uuid4().hex}",
        title="PostgreSQL hard-delete race",
        objective="Skip a candidate removed before advisory-session reload.",
        success_criteria=["The batch completes without a false failure"],
        status="completed",
        result_markdown="# Candidate removed during the scan",
        result_protocol=None,
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    materialize = service.materialize
    deletions: list[int] = []

    def delete_before_advisory_reload(db, selected_mission):
        assert db is seed
        assert selected_mission.id == mission_id
        deleter = session_factory()
        try:
            deletions.append(
                deleter.query(Mission)
                .filter(Mission.id == mission_id)
                .delete(synchronize_session=False)
            )
            deleter.commit()
        finally:
            deleter.close()
        return materialize(db, selected_mission)

    monkeypatch.setattr(service, "materialize", delete_before_advisory_reload)
    try:
        summary = service.reconcile_completed(seed, limit=10)

        assert deletions == [1]
        assert summary.scanned == 1
        assert summary.eligible == 0
        assert summary.repaired == 0
        assert summary.failed == 0
        assert summary.skipped_soft_deleted == 0
        assert seed.query(Mission).filter(Mission.id == mission_id).count() == 0
        auto_ingest.auto_ingest_result.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_hard_delete_after_lock_reload_before_refresh_is_skipped(
    pg_engine,
    monkeypatch,
):
    """A row deleted after advisory reload cannot abort the production batch."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG inner hard-delete race {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-IHD-{uuid4().hex}",
        title="PostgreSQL inner hard-delete race",
        objective="Skip a candidate removed after advisory-session reload.",
        success_criteria=["The batch completes without a false failure"],
        status="completed",
        result_markdown=None,
        result_protocol=None,
        execution_metadata={
            "result_materialization": {
                "status": "failed",
                "attempt_count": 1,
                "attempted_at": "2026-01-01T00:00:00+00:00",
                "error_categories": ["unexpected_materialization_error"],
            }
        },
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    auto_ingest = MagicMock(spec=AutoIngestService)
    service = MissionResultMaterializationService(
        auto_ingest_service=auto_ingest,
        auto_report_service=MagicMock(),
    )
    classify = service.document_materialization_state
    deletions: list[int] = []

    def delete_after_advisory_reload(db, selected_mission):
        assert db is not seed
        assert selected_mission.id == mission_id
        if not deletions:
            deleter = session_factory()
            try:
                deletions.append(
                    deleter.query(Mission)
                    .filter(Mission.id == mission_id)
                    .delete(synchronize_session=False)
                )
                deleter.commit()
            finally:
                deleter.close()
        return classify(db, selected_mission)

    monkeypatch.setattr(
        service,
        "document_materialization_state",
        delete_after_advisory_reload,
    )
    try:
        summary = service.reconcile_completed(seed, limit=10)

        assert deletions == [1]
        assert summary.scanned == 1
        assert summary.eligible == 0
        assert summary.repaired == 0
        assert summary.failed == 0
        assert summary.skipped_soft_deleted == 0
        assert seed.query(Mission).filter(Mission.id == mission_id).count() == 0
        auto_ingest.auto_ingest_result.assert_not_called()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_unrelated_error_is_not_masked_when_mission_disappears(
    pg_engine,
    monkeypatch,
):
    """A concurrent deletion cannot hide a genuine materializer exception."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG hard-delete error {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-HDE-{uuid4().hex}",
        title="PostgreSQL hard-delete genuine error",
        objective="Preserve an unrelated failure during a concurrent deletion.",
        success_criteria=["The sentinel exception propagates"],
        status="completed",
        result_markdown="# Candidate removed during a genuine failure",
        result_protocol=None,
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    service = MissionResultMaterializationService()
    deletions: list[int] = []

    def delete_then_raise(_db, selected_mission):
        assert selected_mission.id == mission_id
        deleter = session_factory()
        try:
            deletions.append(
                deleter.query(Mission)
                .filter(Mission.id == mission_id)
                .delete(synchronize_session=False)
            )
            deleter.commit()
        finally:
            deleter.close()
        raise RuntimeError("sentinel materialization failure")

    monkeypatch.setattr(service, "_materialize_locked", delete_then_raise)
    try:
        with pytest.raises(RuntimeError, match="sentinel materialization failure"):
            service.materialize(seed, mission)

        assert deletions == [1]
        assert seed.query(Mission).filter(Mission.id == mission_id).count() == 0
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_advisory_lock_is_released_when_materialization_raises(
    pg_engine,
    monkeypatch,
):
    """A genuine failure cannot strand the per-mission advisory lock."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG advisory cleanup {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-LOCK-CLEANUP-{uuid4().hex}",
        title="PostgreSQL advisory cleanup",
        objective="Release the lock when materialization raises.",
        success_criteria=["A later owner can acquire the same lock"],
        status="completed",
        result_markdown="# Pending result",
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    lock_key = MissionResultMaterializationService._advisory_lock_key(mission_id)
    statements: list[str] = []
    lock_connections: list[object] = []

    def capture_statement(conn, _cursor, statement, _params, _context, _many):
        normalized = " ".join(statement.split())
        statements.append(normalized)
        if normalized.startswith("SELECT pg_advisory_lock"):
            lock_connections.append(conn.connection.driver_connection)

    service = MissionResultMaterializationService()

    def explode(_db, _mission):
        raise RuntimeError("sentinel materialization failure")

    monkeypatch.setattr(service, "_materialize_locked", explode)
    event.listen(pg_engine, "before_cursor_execute", capture_statement)
    try:
        with pytest.raises(RuntimeError, match="sentinel materialization failure"):
            service.materialize(seed, mission)
    finally:
        event.remove(pg_engine, "before_cursor_execute", capture_statement)

    assert any(statement.startswith("SET lock_timeout") for statement in statements)
    assert any("pg_advisory_lock" in statement for statement in statements)
    assert any("pg_advisory_unlock" in statement for statement in statements)
    assert any(statement == "RESET lock_timeout" for statement in statements)
    assert len(lock_connections) == 1
    probe_engine = create_engine(pg_engine.url, poolclass=NullPool)
    try:
        with probe_engine.connect() as connection:
            assert connection.connection.driver_connection is not lock_connections[0]
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            ).scalar_one()
            assert acquired is True
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            )
            connection.commit()
    finally:
        probe_engine.dispose()

    seed.close()
    cleanup = session_factory()
    try:
        cleanup.query(Mission).filter(Mission.id == mission_id).delete()
        cleanup.query(Project).filter(Project.id == project_id).delete()
        cleanup.commit()
    finally:
        cleanup.close()


def test_postgres_unlock_failure_discards_connection_and_releases_lock(
    pg_engine,
):
    """A failed explicit unlock must never return a lock-owning session to pool."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    project = Project(name=f"PG unlock failure {uuid4().hex}")
    seed.add(project)
    seed.flush()
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-UNLOCK-FAILURE-{uuid4().hex}",
        title="PostgreSQL unlock failure cleanup",
        objective="Discard a physical connection whose explicit unlock failed.",
        success_criteria=["A fresh session can acquire the same advisory key"],
        status="completed",
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    lock_key = MissionResultMaterializationService._advisory_lock_key(mission_id)
    failed_connections: list[object] = []
    invalidated_connections: list[object] = []

    def fail_unlock(conn, _cursor, statement, _params, _context, _many):
        if statement.strip().startswith("SELECT pg_advisory_unlock"):
            failed_connections.append(conn.connection.driver_connection)
            raise RuntimeError("forced advisory unlock failure")

    def record_invalidation(dbapi_connection, _record, _exception):
        invalidated_connections.append(dbapi_connection)

    try:
        event.listen(pg_engine, "before_cursor_execute", fail_unlock)
        event.listen(pg_engine.pool, "invalidate", record_invalidation)
        try:
            outcome = MissionResultMaterializationService().materialize(seed, mission)
        finally:
            event.remove(pg_engine, "before_cursor_execute", fail_unlock)
            event.remove(pg_engine.pool, "invalidate", record_invalidation)

        assert outcome.errors == []
        assert len(failed_connections) == 1
        assert invalidated_connections == failed_connections
        with pg_engine.connect() as connection:
            assert connection.connection.driver_connection is not failed_connections[0]
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            ).scalar_one()
            assert acquired is True
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            )
            connection.commit()
    finally:
        seed.close()
        cleanup = session_factory()
        try:
            cleanup.query(Mission).filter(Mission.id == mission_id).delete()
            cleanup.query(Project).filter(Project.id == project_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()
