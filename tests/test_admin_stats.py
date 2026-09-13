"""System observability must count the database, restrict access and expose unknowns."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.adapters.external.worker_probe import HTTPWorkerProbe
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.graph_edge import GraphEdge
from app.models.ingestion_job import IngestionJob
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.schemas.admin_stats import WorkerObservation

API = f"{settings.api_v1_prefix}/admin/stats"
_HASH = "placeholder-not-a-real-hash"


def actor(db, role):
    user = User(email=f"{uuid4()}@example.test", display_name="Operator", password_hash=_HASH, role=role)
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


@pytest.fixture
def client(monkeypatch):
    async def unavailable(self):
        return WorkerObservation(checked_at=datetime.now(UTC), error="Worker health check timed out")

    monkeypatch.setattr(HTTPWorkerProbe, "observe", unavailable)
    monkeypatch.setattr("app.services.admin_stats.reconciler_health", lambda: {"last_run_at": None, "runs": 0})
    monkeypatch.setattr(
        "app.services.admin_stats.get_correction_queue",
        lambda: SimpleNamespace(
            get_status=lambda limit: SimpleNamespace(
                stats=SimpleNamespace(model_dump=lambda: {"pending": 125, "total": 125})
            )
        ),
    )
    with TestClient(app) as client:
        yield client


def test_system_counts_are_not_a_page_and_refresh_reads_persisted_changes(client, db_session):
    headers = actor(db_session, "admin")
    for i in range(143):
        db_session.add(
            Mission(
                mission_id=uuid4().hex,
                title="Observed work",
                objective="Count all work",
                success_criteria=["Full total"],
                status="completed" if i < 130 else "draft",
            )
        )
    project = Project(name="Active")
    db_session.add_all([project, Project(name="Deleted", deleted_at=datetime.utcnow())])
    db_session.flush()
    doc = Document(project_id=project.id, name="Active", file_type="txt")
    deleted = Document(project_id=project.id, name="Deleted", file_type="txt", deleted_at=datetime.utcnow())
    db_session.add_all([doc, deleted])
    db_session.flush()
    for d in (doc, deleted):
        db_session.add(DocumentChunk(document_id=d.id, chunk_index=0, content="Count only live document chunks"))
    for state in ("PENDING", "PENDING", "COMPLETED"):
        db_session.add(IngestionJob(project_id=project.id, document_id=doc.id, status=state))
    for i, kind in enumerate(("references", "references", "derived_from")):
        db_session.add(GraphEdge(from_urn=f"urn:test:{i}", to_urn="urn:target", edge_type=kind))
    db_session.commit()
    response = client.get(API, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["missions"]["total"] == 143
    assert body["missions"]["by_status"]["completed"] == 130
    assert "complete" not in body["missions"]["by_status"]
    assert sum(body["missions"]["by_status"].values()) == 143
    assert body["projects"] == body["documents"] == body["chunks"] == 1
    assert body["ingestion_jobs"] == {"total": 3, "by_status": {"PENDING": 2, "COMPLETED": 1}}
    assert body["graph_edges"] == 3
    assert body["graph_edges_by_type"] == {"references": 2, "derived_from": 1}
    assert len(body["recent_missions"]) == 6
    assert body["corrections"]["total"] == 125
    assert body["worker"]["status"] == "unavailable"
    assert body["worker"]["missions_completed"] is None
    assert body["reconciler"]["last_run_at"] is None
    db_session.query(Mission).filter(Mission.status == "draft").first().status = "validation_failed"
    db_session.commit()
    refreshed = client.get(API, headers=headers).json()
    direct = dict(db_session.query(Mission.status, func.count()).group_by(Mission.status))
    assert {k: v for k, v in refreshed["missions"]["by_status"].items() if v} == direct


@pytest.mark.parametrize("role,expected", [("member", 403), ("service", 403), ("owner", 200)])
def test_admin_boundary_does_not_depend_on_rbac_rollout(client, db_session, monkeypatch, role, expected):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    assert client.get(API).status_code == 401
    response = client.get(API, headers=actor(db_session, role))
    assert response.status_code == expected
    if expected == 403:
        assert "missions" not in response.json()


def test_queue_failure_does_not_erase_database_counts_or_pretend_empty(client, db_session, monkeypatch):
    def broken():
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr("app.services.admin_stats.get_correction_queue", broken)
    response = client.get(API, headers=actor(db_session, "admin"))
    assert response.status_code == 200
    assert response.json()["missions"]["total"] == 0
    assert response.json()["corrections"] is None
    assert response.json()["corrections_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {"status": "healthy", "missions_processed": 42, "missions_completed": 0, "uptime_seconds": 15},
            {"missions_processed": 42, "missions_completed": 0, "missions_failed": None},
        ),
        (
            {"missions_processed": True, "missions_failed": -1, "missions_completed": "25", "uptime_seconds": "15"},
            {"missions_processed": None, "missions_completed": None, "missions_failed": None},
        ),
        ([], {"status": "unavailable", "missions_processed": None}),
    ],
)
async def test_worker_probe_preserves_observed_zero_and_missing_or_invalid_values(monkeypatch, payload, expected):
    async def get(self, url):
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    result = (await HTTPWorkerProbe().observe()).model_dump()
    for key, value in expected.items():
        assert result[key] == value


@pytest.mark.asyncio
async def test_worker_timeout_does_not_claim_offline_or_zero_completed(monkeypatch):
    async def get(self, url):
        raise httpx.ReadTimeout("internal URL must not leak")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    result = await HTTPWorkerProbe().observe()
    assert result.status == "unavailable"
    assert result.missions_completed is None
    assert result.error == "Worker health check timed out"
