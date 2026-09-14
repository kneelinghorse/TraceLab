"""Personal dashboards must never retain permissions or stale result counts."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, get_key_prefix, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.mission import Mission
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

API = "/api/v1/mission-views"
ATTENTION = "/api/v1/home/attention"
MISSIONS = "/api/v1/missions"
_HASH = "test-only"


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


def actor(db, kind="jwt", role="member"):
    user = User(email=f"{uuid4()}@example.test", display_name="Dashboard reader", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    if kind == "jwt":
        headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    else:
        key = generate_api_key()
        db.add(APIKey(user_id=user.id, name="Dashboard test", key_hash=hash_api_key(key), key_prefix=get_key_prefix(key)))
        db.flush()
        headers = {"X-API-Key": key}
    return user, headers


def mission(db, status="blocked", **kwargs):
    row = Mission(mission_id=uuid4().hex, title="Auditable research", objective="Show only readable work",
                  success_criteria=["Counts match the list"], status=status, **kwargs)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("rbac", [False, True])
@pytest.mark.parametrize("kind", ["jwt", "key"])
def test_live_reason_counts_and_personal_crud_recheck_access(client, db_session, monkeypatch, rbac, kind):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    user, headers = actor(db_session, kind)
    other, outsider = actor(db_session, kind)
    space = Workspace(name="Research Space")
    db_session.add(space)
    db_session.flush()
    membership = SpaceMember(workspace_id=space.id, user_id=user.id)
    db_session.add(membership)
    project = Project(name="Never echo this project name", owner_id=other.id, workspace_id=space.id)
    db_session.add(project)
    db_session.flush()
    for status in ("validation_failed", "blocked", "queued", "completed", "in_progress"):
        mission(db_session, status, project_id=project.id, owner_id=other.id,
                queued_at=datetime.utcnow() - timedelta(hours=2))
    db_session.commit()
    response = client.get(ATTENTION, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    counts = response.json()
    assert counts["by_reason"] == dict.fromkeys(["validation_failed", "blocked", "stalled", "unreviewed"], 1)
    assert counts["total"] == sum(counts["by_reason"].values()) == client.get("/api/v1/home", headers=headers).json()["attention"]["total"] == 4
    assert counts["dashboards"] == [{"key": "at_risk", "total": 3}, {"key": "unreviewed", "total": 1}]
    original = client.get(MISSIONS, headers=headers, params={"view": "attention"})
    all_reasons = client.get(MISSIONS, headers=headers, params=[("view", "attention"), *(("reason", k) for k in counts["by_reason"])])
    assert original.content == all_reasons.content  # Adding reason support preserves the complete existing response.
    for reason in counts["by_reason"]:
        listed = client.get(MISSIONS, headers=headers, params={"view": "attention", "reason": reason, "page_size": 1}).json()
        assert listed["pagination"]["total"] == 1
    filters = {"view": "attention", "reason": ["validation_failed", "blocked", "stalled"], "project_id": str(project.id)}
    created = client.post(API, headers=headers, json={"name": "  At risk in my Space  ", "filters": filters})
    assert created.status_code == 201, created.text
    view = created.json()
    assert view["name"] == "At risk in my Space" and view["total"] == 3
    assert view["filters"] == filters and view["entity_type"] == "missions"
    view_url = f"{API}/{view['id']}"
    assert client.post(API, headers=headers, json={"name": view["name"], "filters": filters}).status_code == 409
    assert client.get(API, headers=outsider).json()["items"] == []
    assert client.put(view_url, headers=outsider, json={"name": "Stolen"}).status_code == 404
    assert client.delete(view_url, headers=outsider).status_code == 404
    assert client.put(view_url, headers=headers, json={"name": "Renamed"}).json()["name"] == "Renamed"
    # Membership loss affects the next request; a saved filter does not grant access.
    db_session.delete(membership)
    db_session.commit()
    expected = 0 if rbac else 3
    saved = client.get(API, headers=headers)
    assert saved.headers["cache-control"] == "private, no-store"
    assert saved.json()["items"][0]["total"] == expected
    assert project.name not in saved.text
    counts = client.get(ATTENTION, headers=headers, params={"project_id": str(project.id)}).json()
    assert counts["dashboards"][0]["total"] == expected
    assert client.delete(view_url, headers=headers).status_code == 204
    assert client.delete(view_url, headers=headers).status_code == 404
    assert client.get(API, headers=headers).json()["items"] == []


@pytest.mark.parametrize("params", [{"reason": "blocked"}, {"view": "queue", "reason": "blocked"}, {"view": "attention", "reason": "invented"}])
def test_reason_misuse_is_400(client, db_session, params):
    _, headers = actor(db_session)
    db_session.commit()
    assert client.get(MISSIONS, headers=headers, params=params).status_code == 400


@pytest.mark.parametrize("rbac", [False, True])
@pytest.mark.parametrize("kind", ["jwt", "key"])
def test_every_new_route_rejects_service_and_anonymous_callers(client, db_session, monkeypatch, rbac, kind):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    _, headers = actor(db_session, kind, "service")
    db_session.commit()
    for method, path, body in [("get", ATTENTION, None), ("get", API, None), ("post", API, {}),
                               ("put", f"{API}/{uuid4()}", {}), ("delete", f"{API}/{uuid4()}", None)]:
        assert client.request(method, path, headers=headers, json=body).status_code == 403
        assert client.request(method, path, json=body).status_code == 401


def test_saved_filter_allowlist_limits_and_review_versions(client, db_session):
    _, headers = actor(db_session, role="admin")
    done = mission(db_session, "completed")
    db_session.commit()
    for payload in [{"name": "   ", "filters": {}}, {"name": "x" * 121, "filters": {}},
                    {"name": "bad", "filters": {"owner_id": str(uuid4())}},
                    {"name": "bad", "filters": {"reason": ["blocked"]}},
                    {"name": "bad", "filters": {"view": "attention", "reason": ["invented"]}},
                    {"name": "bad", "filters": {"status": "invented"}}]:
        assert client.post(API, headers=headers, json=payload).status_code == 422
    filters = {"view": "attention", "reason": ["unreviewed"]}
    first = client.post(API, headers=headers, json={"name": "Completion", "filters": filters}).json()
    assert first["total"] == 1
    assert client.put(f"/api/v1/home/missions/{done.id}/review", headers=headers, json={"updated_at": done.updated_at.isoformat()}).status_code == 204
    assert client.get(API, headers=headers).json()["items"][0]["total"] == 0
    done.updated_at += timedelta(seconds=1)
    db_session.commit()
    assert client.get(API, headers=headers).json()["items"][0]["total"] == 1
    for index in range(49):
        assert client.post(API, headers=headers, json={"name": f"View {index}", "filters": {}}).status_code == 201
    assert client.post(API, headers=headers, json={"name": "View 51", "filters": {}}).status_code == 409
    assert len(client.get(API, headers=headers).json()["items"]) == 50
    assert client.put(f"{API}/{first['id']}", headers=headers, json={"name": "View 0"}).status_code == 409
