"""Home must prioritize real work and never infer totals from a result page."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

API = f"{settings.api_v1_prefix}/home"
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def actor(db, *, role="member"):
    user = User(email=f"{uuid4()}@example.test", display_name="Researcher", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    return user, headers


def mission(db, status="draft", **kwargs):
    row = Mission(
        mission_id=uuid4().hex,
        title="Research the evidence",
        objective="Keep results auditable",
        success_criteria=["Every result links to its evidence"],
        status=status,
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def test_totals_are_database_counts_beyond_100_and_attention_reorders_on_refresh(client, db_session):
    _, headers = actor(db_session, role="admin")
    for _ in range(137):
        mission(db_session)
    now = datetime.utcnow()
    done = mission(db_session, "completed", completed_at=now)
    stale = mission(db_session, "queued", queued_at=now - timedelta(hours=2))
    blocked = mission(db_session, "blocked")
    running = mission(db_session, "in_progress")
    mission(db_session, "queued", queued_at=now)
    db_session.commit()

    response = client.get(API, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    direct = dict(db_session.query(Mission.status, func.count(Mission.id)).group_by(Mission.status).all())
    assert body["missions"]["total"] == sum(direct.values()) == 142
    assert {k: v for k, v in body["missions"]["by_status"].items() if v} == direct
    listed = client.get(f"{settings.api_v1_prefix}/missions?page_size=100", headers=headers).json()
    assert body["missions"]["total"] == listed["pagination"]["total"]
    assert [row["id"] for row in body["attention"]["items"]] == [str(blocked.id), str(stale.id), str(done.id)]
    assert body["active_runs"]["total"] == 1
    assert body["active_runs"]["items"][0]["progress"]["percent"] is None

    running.status = "validation_failed"
    db_session.commit()
    refreshed = client.get(API, headers=headers).json()
    assert refreshed["attention"]["items"][0]["id"] == str(running.id)
    assert refreshed["attention"]["total"] == 4
    assert refreshed["active_runs"]["total"] == 0


def test_review_is_explicit_per_user_and_rejects_a_stale_result(client, db_session):
    _, first = actor(db_session, role="admin")
    _, second = actor(db_session, role="admin")
    row = mission(db_session, "completed", completed_at=datetime.utcnow())
    db_session.commit()
    item = client.get(API, headers=first).json()["attention"]["items"][0]
    path = f"{API}/missions/{row.id}/review"
    for _ in range(2):
        assert client.put(path, headers=first, json={"updated_at": item["updated_at"]}).status_code == 204
    assert client.get(API, headers=first).json()["attention"]["total"] == 0
    assert client.get(API, headers=second).json()["attention"]["total"] == 1

    row.updated_at = row.updated_at + timedelta(seconds=1)
    db_session.commit()
    assert client.get(API, headers=first).json()["attention"]["total"] == 1
    assert client.put(path, headers=first, json={"updated_at": item["updated_at"]}).status_code == 409
    row.status = "in_progress"
    db_session.commit()
    assert client.put(path, headers=first, json={"updated_at": row.updated_at.isoformat()}).status_code == 409


def test_every_section_and_result_link_is_scoped_before_counting(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    member, headers = actor(db_session)
    outsider, _ = actor(db_session)
    space = Workspace(name="Member research")
    private_space = Workspace(name="Private research")
    db_session.add_all([space, private_space])
    db_session.flush()
    db_session.add(SpaceMember(workspace_id=space.id, user_id=member.id))
    visible = Project(name="Accessible project", workspace_id=space.id)
    private = Project(name="Hidden project", workspace_id=private_space.id)
    db_session.add_all([visible, private])
    db_session.flush()
    report = Report(title="Accessible report", content="Evidence", project_id=visible.id)
    secret = Report(title="Hidden report", content="Private", project_id=private.id)
    db_session.add_all([report, secret])
    db_session.flush()
    done = mission(db_session, "completed", project_id=visible.id, result_report_id=report.id)
    hidden = mission(db_session, "validation_failed", project_id=private.id, owner_id=outsider.id)
    mismatched = mission(db_session, "completed", project_id=visible.id, result_report_id=secret.id)
    for project, run in [(visible, done), (private, hidden)]:
        source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash="a" * 64)
        db_session.add(source)
        db_session.flush()
        for index in range(25):
            db_session.add(
                LedgerEntry(
                    project_id=project.id,
                    mission_id=run.id,
                    session_key="worker-run",
                    source_id=source.id,
                    claim=f"Finding {index}",
                    source_url="https://example.test/source",
                    disposition="supporting",
                    origin="deepsearch-worker",
                )
            )
    db_session.commit()
    body = client.get(API, headers=headers).json()
    assert body["missions"]["total"] == 2
    assert body["recent_projects"]["total"] == 1
    assert body["recent_reports"]["total"] == 1
    assert body["evidence_activity"]["total"] == 1
    group = body["evidence_activity"]["items"][0]
    assert group["entry_count"] == 25
    assert group["mission_id"] == str(done.id)
    items = {item["id"]: item for item in body["attention"]["items"]}
    assert items[str(done.id)]["report_id"] == str(report.id)
    assert items[str(done.id)]["evidence_count"] == 25
    assert items[str(mismatched.id)]["report_id"] is None
    assert str(secret.id) not in str(body)
    assert str(private.id) not in str(body)
    assert (
        client.put(
            f"{API}/missions/{hidden.id}/review", headers=headers, json={"updated_at": hidden.updated_at.isoformat()}
        ).status_code
        == 404
    )


def test_progress_only_projects_observed_values_and_does_not_invent_loop_percent(client, db_session):
    _, headers = actor(db_session, role="admin")
    observed = mission(
        db_session,
        "in_progress",
        execution_metadata={
            "current_phase": "synthesis",
            "progress_percent": 60,
            "current_step": 3,
            "total_steps": 5,
        },
    )
    legacy = mission(db_session, "in_progress", execution_metadata={"current_loop": 2, "sources": 40})
    invalid = mission(db_session, "in_progress", execution_metadata={"progress_percent": 250, "current_phase": []})
    db_session.commit()
    runs = {r["id"]: r["progress"] for r in client.get(API, headers=headers).json()["active_runs"]["items"]}
    assert runs[str(observed.id)] == {"phase": "synthesis", "percent": 60, "current_step": 3, "total_steps": 5}
    assert runs[str(legacy.id)]["percent"] is None
    assert runs[str(invalid.id)]["percent"] is None
    assert runs[str(invalid.id)]["phase"] is None


def test_home_requires_authentication_and_rejects_service_principals(client, db_session):
    assert client.get(API).status_code == 401
    _, service = actor(db_session, role="service")
    db_session.commit()
    assert client.get(API, headers=service).status_code == 403


def test_empty_home_does_not_leak_totals_and_ledger_requires_project_access(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    member, headers = actor(db_session)
    other, _ = actor(db_session)
    private = Project(name="Private", owner_id=other.id)
    owned = Project(name="Owned", owner_id=member.id)
    deleted = Project(name="Deleted", owner_id=member.id, deleted_at=datetime.utcnow())
    db_session.add_all([private, owned, deleted])
    db_session.flush()
    mission(db_session, "blocked", project_id=private.id, owner_id=other.id)
    for project in (private, owned, deleted):
        source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash="b" * 64)
        db_session.add(source)
        db_session.flush()
        db_session.add(
            LedgerEntry(
                project_id=project.id,
                session_key="owner-scope",
                claim="Owned claim in a project",
                owner_id=member.id if project != owned else other.id,
                source_id=source.id,
                source_url=source.source_url,
                disposition="background",
            )
        )
    db_session.commit()
    response = client.get(API, headers=headers)
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["missions"]["total"] == 0
    assert all(count == 0 for count in body["missions"]["by_status"].values())
    assert body["attention"] == {"total": 0, "items": []}
    assert body["active_runs"] == {"total": 0, "items": []}
    assert body["evidence_activity"]["total"] == 1
    assert body["evidence_activity"]["items"][0]["project_id"] == str(owned.id)
    assert str(private.id) not in str(body)
    assert str(deleted.id) not in str(body)
