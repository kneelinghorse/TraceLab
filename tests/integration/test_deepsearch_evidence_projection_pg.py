"""Real-PostgreSQL concurrency contract for DeepSearch Evidence projection."""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from app.models.evidence_ledger import (
    DeepSearchEvidenceOutbox,
    DeepSearchLedgerBatch,
    LedgerEntry,
    LedgerSource,
)
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.services.evidence_ledger import EvidenceLedgerService

pytestmark = pytest.mark.integration

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "deepsearch_evidence_projection_v1.json"
_HASH = "placeholder-not-a-real-hash"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_concurrent_identical_triggers_create_one_batch_and_one_entry_set(pg_engine):
    """The mission lock plus unique key make a request race an idempotent replay.

    This is deliberately exercised with independent PostgreSQL sessions.  A
    SQLite or same-session test cannot prove that the second request waits for
    the first commit instead of inserting another batch and incrementing every
    canonical source a second time.
    """
    fixture = _fixture()
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    owner = User(
        email=f"pg-projection-{uuid4()}@example.test",
        display_name="pg-projection-owner",
        password_hash=_HASH,
        role="owner",
    )
    workspace = Workspace(name=f"PG projection space {uuid4().hex}")
    seed.add_all([owner, workspace])
    seed.flush()
    project = Project(
        name=f"PG projection project {uuid4().hex}",
        owner_id=owner.id,
        workspace_id=workspace.id,
    )
    seed.add(project)
    seed.flush()
    stored = fixture["mission"]
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-LEDGER-{uuid4().hex}",
        title="Concurrent DeepSearch evidence projection",
        objective="Create one immutable evidence batch under request contention.",
        success_criteria=["Both callers observe the same entry identifiers."],
        status="completed",
        deepsearch_job_id=stored["deepsearch_job_id"],
        result_markdown=stored["result_markdown"],
        result_protocol=deepcopy(stored["result_protocol"]),
        execution_metadata=deepcopy(stored["execution_metadata"]),
        owner_id=owner.id,
        workspace_id=workspace.id,
    )
    seed.add(mission)
    seed.commit()
    mission_id = mission.id
    project_id = project.id
    workspace_id = workspace.id
    owner_id = owner.id
    job_id = mission.deepsearch_job_id
    seed.close()

    barrier = Barrier(2)

    def project_once():
        db = session_factory()
        try:
            barrier.wait(timeout=5)
            return EvidenceLedgerService().capture_deepsearch_mission_evidence(
                db,
                mission_id,
                job_id,
            )
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: project_once(), range(2)))

        assert {outcome.status for outcome in outcomes} == {
            "captured",
            "already_processed",
        }
        assert outcomes[0].entry_ids == outcomes[1].entry_ids
        assert outcomes[0].entry_count == outcomes[1].entry_count
        assert outcomes[0].entry_count == fixture["expected_projection"]["entry_count"]

        verify = session_factory()
        try:
            batches = verify.query(DeepSearchLedgerBatch).filter(DeepSearchLedgerBatch.mission_id == mission_id).all()
            entries = verify.query(LedgerEntry).filter(LedgerEntry.mission_id == mission_id).all()
            sources = verify.query(LedgerSource).filter(LedgerSource.project_id == project_id).all()

            assert len(batches) == 1
            assert batches[0].entry_count == len(entries)
            assert len(entries) == fixture["expected_projection"]["entry_count"]
            assert {entry.deepsearch_batch_id for entry in entries} == {batches[0].id}
            assert {entry.owner_id for entry in entries} == {owner_id}
            assert {entry.workspace_id for entry in entries} == {workspace_id}
            assert {str(entry.id) for entry in entries} == {str(entry_id) for entry_id in outcomes[0].entry_ids}

            expected_sightings = Counter(entry.source_url for entry in entries)
            assert {source.source_url for source in sources} == set(expected_sightings)
            assert {source.source_url: source.sighting_count for source in sources} == dict(
                expected_sightings
            ), "the replaying contender must not increment a source a second time"
        finally:
            verify.close()
    finally:
        cleanup = session_factory()
        try:
            project = cleanup.get(Project, project_id)
            if project is not None:
                cleanup.delete(project)
            workspace = cleanup.get(Workspace, workspace_id)
            if workspace is not None:
                cleanup.delete(workspace)
            owner = cleanup.get(User, owner_id)
            if owner is not None:
                cleanup.delete(owner)
            cleanup.commit()
        finally:
            cleanup.close()


def test_mission_hard_delete_cancels_delivery_but_retains_projected_evidence(
    pg_engine,
):
    """PostgreSQL cascades cancel work while SET NULL retains ledger claims."""
    fixture = _fixture()
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    db = session_factory()
    owner = User(
        email=f"pg-retention-{uuid4()}@example.test",
        display_name="pg-retention-owner",
        password_hash=_HASH,
        role="owner",
    )
    workspace = Workspace(name=f"PG retention space {uuid4().hex}")
    db.add_all([owner, workspace])
    db.flush()
    project = Project(
        name=f"PG retention project {uuid4().hex}",
        owner_id=owner.id,
        workspace_id=workspace.id,
    )
    db.add(project)
    db.flush()
    stored = fixture["mission"]
    mission = Mission(
        project_id=project.id,
        mission_id=f"PG-RETENTION-{uuid4().hex}",
        title="Retain DeepSearch evidence after mission deletion",
        objective="Cancel delivery without deleting captured claims.",
        success_criteria=["Projected provenance survives with nullable links."],
        status="completed",
        deepsearch_job_id=stored["deepsearch_job_id"],
        deepsearch_result_key="pg-retention-result",
        deepsearch_attempt_count=1,
        result_markdown=stored["result_markdown"],
        result_protocol=deepcopy(stored["result_protocol"]),
        execution_metadata=deepcopy(stored["execution_metadata"]),
        owner_id=owner.id,
        workspace_id=workspace.id,
    )
    db.add(mission)
    db.commit()
    mission_id = mission.id
    project_id = project.id
    workspace_id = workspace.id
    owner_id = owner.id
    job_id = mission.deepsearch_job_id

    try:
        result = EvidenceLedgerService().capture_deepsearch_mission_evidence(
            db,
            mission_id,
            job_id,
        )
        assert result.status == "captured"
        db.add(
            DeepSearchEvidenceOutbox(
                mission_id=mission_id,
                deepsearch_job_id=job_id,
                deepsearch_result_key="pg-retention-result",
                mission_attempt_count=1,
                terminal_status="completed",
            )
        )
        db.commit()

        entries = db.query(LedgerEntry).filter(LedgerEntry.mission_id == mission_id).all()
        entry_ids = {entry.id for entry in entries}
        provenance = {
            entry.id: (
                entry.project_id,
                entry.session_key,
                entry.origin,
                entry.claim,
                entry.summary,
                entry.source_url,
                entry.source_id,
                entry.snippet,
                entry.disposition,
                entry.owner_id,
                entry.workspace_id,
            )
            for entry in entries
        }
        assert db.query(DeepSearchLedgerBatch).filter_by(mission_id=mission_id).count() == 1
        assert db.query(DeepSearchEvidenceOutbox).filter_by(mission_id=mission_id).count() == 1

        db.execute(delete(Mission).where(Mission.id == mission_id))
        db.commit()
        db.expire_all()

        assert db.get(Mission, mission_id) is None
        assert db.query(DeepSearchLedgerBatch).filter_by(mission_id=mission_id).count() == 0
        assert db.query(DeepSearchEvidenceOutbox).filter_by(mission_id=mission_id).count() == 0
        retained = db.query(LedgerEntry).filter(LedgerEntry.id.in_(entry_ids)).all()
        assert {entry.id for entry in retained} == entry_ids
        assert {entry.mission_id for entry in retained} == {None}
        assert {entry.deepsearch_batch_id for entry in retained} == {None}
        assert {
            entry.id: (
                entry.project_id,
                entry.session_key,
                entry.origin,
                entry.claim,
                entry.summary,
                entry.source_url,
                entry.source_id,
                entry.snippet,
                entry.disposition,
                entry.owner_id,
                entry.workspace_id,
            )
            for entry in retained
        } == provenance
    finally:
        cleanup = session_factory()
        try:
            project = cleanup.get(Project, project_id)
            if project is not None:
                cleanup.delete(project)
            workspace = cleanup.get(Workspace, workspace_id)
            if workspace is not None:
                cleanup.delete(workspace)
            owner = cleanup.get(User, owner_id)
            if owner is not None:
                cleanup.delete(owner)
            cleanup.commit()
        finally:
            cleanup.close()
            db.close()
