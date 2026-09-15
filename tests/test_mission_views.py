"""Mission listing is recency-sorted and scoped; status never floats a row."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.mission_events import MissionEvent, get_mission_event_bus
from app.core.security import create_access_token
from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User

API = f"{settings.api_v1_prefix}/missions"
HOME = f"{settings.api_v1_prefix}/home"
_TEST_HASH = "test-only"


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def actor(db, role="admin"):
    user = User(email=f"{uuid4()}@example.test", display_name="Researcher", password_hash=_TEST_HASH, role=role)
    db.add(user)
    db.flush()
    return user, {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def mission(db, status="draft", **kwargs):
    row = Mission(mission_id=f"VIEW-{uuid4().hex}", title="Audit research", objective="Keep evidence inspectable",
                  success_criteria=["Every finding cites evidence"], status=status, **kwargs)
    db.add(row)
    db.flush()
    return row


def test_list_sorts_by_recency_only_and_counts_before_paging(client, db_session):
    _, headers = actor(db_session)
    now = datetime.utcnow()
    oldest = mission(db_session, "validation_failed", created_at=now - timedelta(days=9), updated_at=now)
    middle = mission(db_session, "completed", created_at=now - timedelta(days=5), updated_at=now - timedelta(days=5))
    newest = mission(db_session, "draft", created_at=now, updated_at=now - timedelta(days=1))
    for index in range(137):
        mission(db_session, created_at=now - timedelta(days=30 + index))
    db_session.commit()
    home = client.get(HOME, headers=headers).json()
    first = client.get(API, params={"page_size": 2}, headers=headers).json()
    second = client.get(API, params={"page_size": 2, "page": 2}, headers=headers).json()
    assert first["pagination"]["total"] == home["missions"]["total"] == 140
    assert [r["id"] for r in first["data"] + second["data"]][:3] == [str(newest.id), str(middle.id), str(oldest.id)]
    updated = client.get(API, params={"sort": "updated_desc", "page_size": 2}, headers=headers).json()
    assert [r["id"] for r in updated["data"]] == [str(oldest.id), str(newest.id)]
    ascending = client.get(API, params={"sort": "created_asc", "page_size": 1}, headers=headers).json()
    assert ascending["data"][0]["id"] != str(newest.id)
    failed = client.get(API, params={"status": "validation_failed"}, headers=headers).json()
    assert [r["id"] for r in failed["data"]] == [str(oldest.id)]
    assert client.get(API, params={"sort": "invented"}, headers=headers).status_code == 422
    assert client.get(API, params={"view": "attention"}, headers=headers).status_code == 200


def test_filters_do_not_leak_hidden_projects_or_statuses(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session, "member")
    other, _ = actor(db_session, "member")
    visible = Project(name="My project", owner_id=user.id)
    hidden = Project(name="Private project", owner_id=other.id)
    db_session.add_all([visible, hidden])
    db_session.flush()
    for project, owner in ((visible, user), (hidden, other)):
        mission(db_session, "blocked", project_id=project.id, owner_id=owner.id)
        mission(db_session, "queued", project_id=project.id, owner_id=owner.id)
    db_session.commit()
    body = client.get(API, params={"status": "blocked", "project_id": str(visible.id)}, headers=headers).json()
    assert body["pagination"]["total"] == 1
    assert str(hidden.id) not in str(body)
    assert client.get(API, params={"project_id": str(hidden.id)}, headers=headers).json()["pagination"]["total"] == 0


def test_recent_activity_is_mission_scoped_before_limit_and_authorized(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session, "member")
    other, admin = actor(db_session)
    owned = mission(db_session, owner_id=user.id)
    hidden = mission(db_session, owner_id=other.id)
    # A human name that looks like another row's UUID must not grant its events.
    owned.mission_id = str(hidden.id)
    db_session.commit()
    bus = get_mission_event_bus()
    for reference, kind in ((str(owned.id), "mission.started"), (str(hidden.id), "mission.completed"),
                            (str(owned.id), "cmos.mission.completed")):
        bus.emit(MissionEvent(event_type=kind, timestamp="2026-09-13T00:00:00Z", mission_id=reference))
    response = client.get(f"{API}/events/recent", params={"mission_id": str(owned.id), "limit": 1}, headers=headers)
    assert response.status_code == 200
    assert [r["event_type"] for r in response.json()] == ["mission.started"]
    assert client.get(f"{API}/events/recent", params={"mission_id": str(hidden.id)}, headers=headers).status_code == 404
    assert client.get(f"{API}/events/recent", params={"mission_id": str(uuid4())}, headers=admin).status_code == 404


def test_recent_activity_accepts_canonical_human_ids(client, db_session):
    user, headers = actor(db_session)
    row = mission(db_session, owner_id=user.id)
    db_session.commit()
    bus = get_mission_event_bus()
    bus.emit(MissionEvent(event_type="mission.queued", timestamp="2026-09-13T00:00:00Z", mission_id=row.mission_id))
    body = client.get(f"{API}/events/recent", params={"mission_id": str(row.id)}, headers=headers).json()
    assert [event["mission_id"] for event in body] == [row.mission_id]
