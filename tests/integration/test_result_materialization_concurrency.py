"""PostgreSQL concurrency contract for terminal result materialization."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
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
