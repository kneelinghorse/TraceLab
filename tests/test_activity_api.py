"""Recent activity is one recency-ordered stream; new until opened, never floated by status."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.user import User
from app.models.user_item_view import UserItemView

API = f"{settings.api_v1_prefix}/activity"
HOME = f"{settings.api_v1_prefix}/home"
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def actor(db, *, role="admin"):
    user = User(email=f"{uuid4()}@example.test", display_name="Researcher", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    return user, {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def mission(db, status="draft", **kwargs):
    row = Mission(
        mission_id=uuid4().hex, title="Research the evidence", objective="Keep results auditable",
        success_criteria=["Every result links to its evidence"], status=status, **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def evidence(db, project, run, count=3, when=None):
    source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash="a" * 64)
    db.add(source)
    db.flush()
    for index in range(count):
        db.add(LedgerEntry(
            project_id=project.id, mission_id=run.id, session_key="worker-run", source_id=source.id,
            claim=f"Finding {index}", source_url=source.source_url, disposition="supporting",
            origin="deepsearch-worker", created_at=(when or datetime.utcnow()) + timedelta(seconds=index),
        ))
    db.flush()


def test_stream_orders_by_when_things_happened_and_status_is_only_a_label(client, db_session):
    _, headers = actor(db_session)
    now = datetime.utcnow()
    old_failure = mission(db_session, "validation_failed", updated_at=now - timedelta(days=21))
    done = mission(db_session, "completed", completed_at=now - timedelta(hours=2), updated_at=now)
    running = mission(db_session, "in_progress", started_at=now - timedelta(minutes=5), updated_at=now - timedelta(hours=9))
    report = Report(title="Fresh report", content="Findings", updated_at=now - timedelta(minutes=1))
    db_session.add(report)
    db_session.flush()
    project = Project(name="Scoped")
    db_session.add(project)
    db_session.flush()
    evidence(db_session, project, running, when=now - timedelta(minutes=30))
    db_session.commit()

    body = client.get(API, headers=headers).json()
    assert body["total"] == 5 and body["new_total"] == 5
    assert [(i["type"], i["id"]) for i in body["items"]] == [
        ("report", str(report.id)), ("mission", str(running.id)), ("evidence", body["items"][2]["id"]),
        ("mission", str(done.id)), ("mission", str(old_failure.id)),
    ]
    assert body["items"][-1]["status"] == "validation_failed" and body["items"][-1]["new"] is True
    assert body["items"][2]["title"] == "3 evidence entries · DeepSearch"
    assert body["items"][2]["href"].startswith("/evidence?project_id=")
    home = client.get(HOME, headers=headers).json()
    assert "attention" not in home
    assert [i["id"] for i in home["activity"]["items"]] == [i["id"] for i in body["items"]]
    assert home["activity"]["new_total"] == 5


def test_items_stay_new_until_viewed_per_user_and_return_when_they_change(client, db_session):
    _, first = actor(db_session)
    _, second = actor(db_session)
    now = datetime.utcnow()
    done = mission(db_session, "completed", completed_at=now)
    db_session.commit()
    item = client.get(API, headers=first).json()["items"][0]
    payload = {"items": [{"type": "mission", "id": item["id"], "occurred_at": item["occurred_at"]}]}
    for _ in range(2):
        response = client.put(f"{API}/viewed", headers=first, json=payload)
        assert response.status_code == 200, response.text
        assert response.json() == {"viewed": 1, "new_total": 0}
    assert db_session.query(UserItemView).count() == 1
    assert client.get(API, headers=first).json()["items"][0]["new"] is False
    assert client.get(f"{API}/summary", headers=first).json()["by_type"] == {"mission": 0, "report": 0, "evidence": 0}
    assert client.get(API, headers=second).json()["items"][0]["new"] is True

    done.completed_at = now + timedelta(seconds=5)
    db_session.commit()
    assert client.get(f"{API}/summary", headers=first).json()["new_total"] == 1
    # A stale mark cannot hide a newer revision.
    assert client.put(f"{API}/viewed", headers=first, json=payload).json()["new_total"] == 1


def test_pages_split_one_merged_stream_and_summary_counts_the_whole_scope(client, db_session):
    _, headers = actor(db_session)
    now = datetime.utcnow()
    for index in range(7):
        mission(db_session, "completed", completed_at=now - timedelta(minutes=index * 2))
        db_session.add(Report(title=f"Report {index}", content="x", updated_at=now - timedelta(minutes=index * 2 + 1)))
    db_session.commit()
    first = client.get(API, params={"page_size": 5}, headers=headers).json()
    second = client.get(API, params={"page_size": 5, "page": 2}, headers=headers).json()
    third = client.get(API, params={"page_size": 5, "page": 3}, headers=headers).json()
    ids = [i["id"] for i in first["items"] + second["items"] + third["items"]]
    assert first["total"] == 14 and len(ids) == len(set(ids)) == 14
    stamps = [i["occurred_at"] for i in first["items"] + second["items"] + third["items"]]
    assert stamps == sorted(stamps, reverse=True)
    assert [i["type"] for i in first["items"]] == ["mission", "report", "mission", "report", "mission"]
    assert client.get(f"{API}/summary", headers=headers).json()["by_type"] == {"mission": 7, "report": 7, "evidence": 0}


def test_stream_and_viewed_marks_are_scoped(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    member, headers = actor(db_session, role="member")
    outsider, _ = actor(db_session, role="member")
    visible = Project(name="Mine", owner_id=member.id)
    hidden = Project(name="Theirs", owner_id=outsider.id)
    db_session.add_all([visible, hidden])
    db_session.flush()
    mine = mission(db_session, "completed", project_id=visible.id, owner_id=member.id, completed_at=datetime.utcnow())
    theirs = mission(db_session, "blocked", project_id=hidden.id, owner_id=outsider.id)
    secret = Report(title="Hidden report", content="Private", project_id=hidden.id, owner_id=outsider.id)
    db_session.add(secret)
    db_session.flush()
    evidence(db_session, hidden, theirs)
    db_session.commit()
    body = client.get(API, headers=headers).json()
    assert body["total"] == 1 and [i["id"] for i in body["items"]] == [str(mine.id)]
    assert str(theirs.id) not in str(body) and str(secret.id) not in str(body) and str(hidden.id) not in str(body)
    response = client.put(f"{API}/viewed", headers=headers, json={"items": [
        {"type": "mission", "id": str(theirs.id), "occurred_at": theirs.updated_at.isoformat()},
        {"type": "report", "id": str(secret.id), "occurred_at": secret.updated_at.isoformat()},
    ]})
    assert response.status_code == 200 and response.json()["viewed"] == 0
    assert db_session.query(UserItemView).count() == 0


def test_activity_requires_authentication_and_rejects_service_principals(client, db_session):
    assert client.get(API).status_code == 401
    assert client.get(f"{API}/summary").status_code == 401
    assert client.put(f"{API}/viewed", json={"items": []}).status_code == 401
    _, service = actor(db_session, role="service")
    db_session.commit()
    assert client.get(API, headers=service).status_code == 403
    _, headers = actor(db_session)
    db_session.commit()
    response = client.get(API, headers=headers)
    assert response.headers["cache-control"] == "private, no-store"
    assert client.put(f"{API}/viewed", headers=headers, json={"items": []}).status_code == 422


def test_opening_a_group_of_evidence_marks_the_whole_group_seen(client, db_session):
    """BADGE-1 (decision #528): one run is one group; opening it clears it without paging.

    WALK-1 finding 7: a 296-entry run meant 29 pages to clear the badge, because
    nothing on the Evidence page ever marked the group viewed.
    """
    _, headers = actor(db_session)
    project, other = Project(name="Alpha"), Project(name="Beta")
    db_session.add_all([project, other])
    db_session.flush()
    now = datetime.utcnow()
    run = mission(db_session, "completed", project_id=project.id, completed_at=now)
    other_run = mission(db_session, "completed", project_id=other.id, completed_at=now)
    evidence(db_session, project, run, count=300)
    evidence(db_session, other, other_run, count=2)
    db_session.commit()
    assert client.get(f"{API}/summary", headers=headers).json()["by_type"] == {"mission": 2, "report": 0, "evidence": 2}

    response = client.put(f"{API}/viewed/evidence", headers=headers, json={"project_id": str(project.id), "mission_id": str(run.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"viewed": 1, "new_total": 3}
    assert db_session.query(UserItemView).filter(UserItemView.item_type == "evidence").count() == 1, "300 entries, one mark"
    assert client.get(f"{API}/summary", headers=headers).json()["by_type"]["evidence"] == 1

    # The project-wide scope reaches the other run; a second call changes nothing.
    assert client.put(f"{API}/viewed/evidence", headers=headers, json={"project_id": str(other.id)}).json() == {"viewed": 1, "new_total": 2}
    assert client.put(f"{API}/viewed/evidence", headers=headers, json={"project_id": str(other.id)}).json() == {"viewed": 1, "new_total": 2}
    assert client.get(f"{API}/summary", headers=headers).json()["by_type"]["evidence"] == 0


def test_marking_a_group_seen_is_scoped_to_what_the_caller_can_read(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    _, headers = actor(db_session, role="member")
    outsider, _ = actor(db_session, role="member")
    private = Project(name="Private", owner_id=outsider.id)
    db_session.add(private)
    db_session.flush()
    run = mission(db_session, "completed", project_id=private.id, owner_id=outsider.id, completed_at=datetime.utcnow())
    evidence(db_session, private, run)
    db_session.commit()
    response = client.put(f"{API}/viewed/evidence", headers=headers, json={"project_id": str(private.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"viewed": 0, "new_total": 0}
    assert db_session.query(UserItemView).count() == 0
