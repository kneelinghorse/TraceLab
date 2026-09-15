"""The inbox must show only scoped work, count nothing twice, and forget nothing on revocation."""

import time
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, get_key_prefix, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.user_inbox_state import UserInboxState
from app.models.workspace import Workspace

API = f"{settings.api_v1_prefix}/inbox"
HOME = f"{settings.api_v1_prefix}/home"
_HASH = "test-only"


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


def actor(db, kind="jwt", role="member", created_at=None):
    user = User(email=f"{uuid4()}@example.test", display_name="Inbox reader", password_hash=_HASH, role=role,
                **({"created_at": created_at} if created_at else {}))
    db.add(user)
    db.flush()
    if kind == "jwt":
        headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    else:
        key = generate_api_key()
        db.add(APIKey(user_id=user.id, name="Inbox test", key_hash=hash_api_key(key), key_prefix=get_key_prefix(key)))
        db.flush()
        headers = {"X-API-Key": key}
    return user, headers


def mission(db, status, **kwargs):
    row = Mission(mission_id=uuid4().hex, title="Auditable research", objective="Surface only readable work",
                  success_criteria=["Unread counts match the sections"], status=status, **kwargs)
    db.add(row)
    db.flush()
    return row


def evidence(db, project, mission_id=None, *, count=1, session_key="worker-run", origin="deepsearch-worker",
             created_at=None):
    source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash=uuid4().hex * 2)
    db.add(source)
    db.flush()
    for index in range(count):
        db.add(LedgerEntry(project_id=project.id, mission_id=mission_id, session_key=session_key, source_id=source.id,
                           claim=f"Finding {index}", source_url=source.source_url, disposition="supporting", origin=origin,
                           **({"created_at": created_at} if created_at else {})))
    db.flush()


def summary(client, headers):
    response = client.get(f"{API}/summary", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def section(client, headers, name, **params):
    response = client.get(API, headers=headers, params={"section": name, **params})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


@pytest.mark.parametrize("rbac", [False, True])
@pytest.mark.parametrize("kind", ["jwt", "key"])
def test_sections_are_scoped_counted_before_paging_and_drop_on_revocation(client, db_session, monkeypatch, rbac, kind):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    now = datetime.utcnow()
    user, headers = actor(db_session, kind, created_at=now - timedelta(days=1))
    other, _ = actor(db_session, kind)
    space = Workspace(name="Research Space")
    db_session.add(space)
    db_session.flush()
    membership = SpaceMember(workspace_id=space.id, user_id=user.id)
    db_session.add(membership)
    project = Project(name="Never echo this project name", owner_id=other.id, workspace_id=space.id)
    private = Project(name="Private project", owner_id=other.id)
    db_session.add_all([project, private])
    db_session.flush()
    failed = mission(db_session, "validation_failed", project_id=project.id, owner_id=other.id,
                     completed_at=now - timedelta(minutes=5))
    blocked = mission(db_session, "blocked", project_id=project.id, owner_id=other.id)  # no completed_at: updated_at
    done = mission(db_session, "completed", project_id=project.id, owner_id=other.id, completed_at=now - timedelta(minutes=1))
    older = mission(db_session, "completed", project_id=project.id, owner_id=other.id, completed_at=now - timedelta(minutes=10))
    mission(db_session, "in_progress", project_id=project.id, owner_id=other.id)
    hidden = mission(db_session, "blocked", project_id=private.id, owner_id=other.id)
    evidence(db_session, project, done.id, count=3)
    evidence(db_session, project, None, count=2, session_key="agent-session", origin="mcp-agent")
    evidence(db_session, private, hidden.id, count=4, session_key="private-run")
    db_session.commit()

    hidden_count = 0 if rbac else 1
    body = summary(client, headers)
    assert body["unread"] == {"failures": 2 + hidden_count, "completions": 2, "evidence": 2 + hidden_count,
                              "total": 6 + 2 * hidden_count}
    assert body["refresh_seconds"] == 30 and body["default_lookback_seconds"] == 7 * 24 * 3600
    assert body["seen_through"] == user.created_at.isoformat()

    failures = section(client, headers, "failures")
    assert failures["total"] == 2 + hidden_count
    ids = [item["id"] for item in failures["items"]]
    assert ids[-1] == str(failed.id) and str(blocked.id) in ids  # updated_at fallback orders the blocked run first
    assert all(item["unread"] and item["reviewed"] is None and item["href"] == f"/missions/{item['id']}"
               for item in failures["items"])

    first_page = section(client, headers, "completions", page_size=1)
    assert first_page["total"] == 2  # counted after scoping, before paging
    assert [item["id"] for item in first_page["items"]] == [str(done.id)]
    item = first_page["items"][0]
    assert item["reviewed"] is False and item["unread"] is True and item["label"] == done.mission_id
    assert item["occurred_at"] == done.completed_at.isoformat() and item["updated_at"] == done.updated_at.isoformat()
    assert [i["id"] for i in section(client, headers, "completions", page_size=1, page=2)["items"]] == [str(older.id)]

    groups = {item["session_key"]: item for item in section(client, headers, "evidence")["items"]}
    assert len(groups) == 2 + hidden_count
    assert groups["worker-run"]["entry_count"] == 3 and groups["worker-run"]["unread"] is True
    assert groups["worker-run"]["href"] == f"/evidence?project_id={project.id}&mission_id={done.id}&session_key=worker-run"
    assert groups["agent-session"]["href"] == f"/evidence?project_id={project.id}&session_key=agent-session"
    assert groups["agent-session"]["label"] == "mcp-agent"
    if rbac:
        everything = "".join(client.get(API, headers=headers, params={"section": s}).text for s in ("failures", "completions", "evidence"))
        assert str(hidden.id) not in everything and str(private.id) not in everything
    assert project.name not in client.get(API, headers=headers, params={"section": "evidence"}).text

    # Reviewing a completion (decision #395) removes it from unread but keeps it listed as reviewed.
    review = client.put(f"{HOME}/missions/{done.id}/review", headers=headers, json={"updated_at": item["updated_at"]})
    assert review.status_code == 204, review.text
    assert summary(client, headers)["unread"]["completions"] == 1
    listed = section(client, headers, "completions")
    by_id = {entry["id"]: entry for entry in listed["items"]}
    assert listed["total"] == 2 and by_id[str(done.id)]["reviewed"] is True and by_id[str(done.id)]["unread"] is False
    unread_only = section(client, headers, "completions", unread_only="true")
    assert unread_only["total"] == 1 and unread_only["items"][0]["id"] == str(older.id)
    before = summary(client, headers)["unread"]["total"]

    # Membership loss takes effect on the very next request; no per-item rows survive to leak.
    db_session.delete(membership)
    db_session.commit()
    after = summary(client, headers)["unread"]
    if rbac:
        assert after == {"failures": 0, "completions": 0, "evidence": 0, "total": 0}
        for name in ("failures", "completions", "evidence"):
            page = section(client, headers, name)
            assert page["total"] == 0 and page["items"] == []
    else:
        assert after["total"] == before


def test_first_visit_window_is_bounded_by_account_age_and_seven_days(client, db_session):
    now = datetime.utcnow()
    _, veteran = actor(db_session, role="admin", created_at=now - timedelta(days=30))
    newcomer, fresh = actor(db_session, role="admin", created_at=now - timedelta(days=1))
    mission(db_session, "blocked", completed_at=now - timedelta(days=10))
    mission(db_session, "blocked", completed_at=now - timedelta(days=3))
    mission(db_session, "blocked", completed_at=now - timedelta(hours=1))
    db_session.commit()
    body = summary(client, veteran)
    assert abs(datetime.fromisoformat(body["seen_through"]) - (now - timedelta(days=7))) < timedelta(seconds=5)
    assert body["unread"]["failures"] == 2
    body = summary(client, fresh)
    assert body["seen_through"] == newcomer.created_at.isoformat()
    assert body["unread"]["failures"] == 1
    assert db_session.query(UserInboxState).count() == 0  # reading never writes


def test_mark_seen_is_explicit_monotonic_utc_and_never_hides_later_items(client, db_session):
    now = datetime.utcnow()
    user, headers = actor(db_session, role="admin", created_at=now - timedelta(days=1))
    earlier = mission(db_session, "blocked", completed_at=now - timedelta(minutes=2))
    db_session.commit()
    snapshot = summary(client, headers)
    assert snapshot["unread"]["total"] == 1
    generated_at = datetime.fromisoformat(snapshot["generated_at"])
    # A failure that lands after the snapshot must survive marking with that snapshot's generated_at.
    late = mission(db_session, "validation_failed", completed_at=generated_at + timedelta(milliseconds=1))
    db_session.commit()

    marked = client.put(f"{API}/seen", headers=headers, json={"seen_through": snapshot["generated_at"]})
    assert marked.status_code == 200, marked.text
    assert marked.json()["seen_through"] == snapshot["generated_at"]
    after = summary(client, headers)
    assert after["seen_through"] == snapshot["generated_at"] and after["unread"]["total"] == 1
    items = section(client, headers, "failures")["items"]
    assert [(item["id"], item["unread"]) for item in items] == [(str(late.id), True), (str(earlier.id), False)]
    assert [item["id"] for item in section(client, headers, "failures", unread_only="true")["items"]] == [str(late.id)]

    # An older value is a no-op; the watermark only advances.
    older = client.put(f"{API}/seen", headers=headers, json={"seen_through": (generated_at - timedelta(hours=1)).isoformat()})
    assert older.status_code == 200 and older.json()["seen_through"] == snapshot["generated_at"]
    assert db_session.query(UserInboxState).filter(UserInboxState.user_id == user.id).one().seen_through == generated_at

    # A value later than the server clock is rejected.
    future = client.put(f"{API}/seen", headers=headers, json={"seen_through": (datetime.utcnow() + timedelta(minutes=5)).isoformat()})
    assert future.status_code == 422
    assert client.put(f"{API}/seen", headers=headers, json={}).status_code == 422

    # A timezone-aware value is normalized to naive UTC before it is stored or compared.
    target = generated_at + timedelta(milliseconds=1)
    aware = target.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=2)))
    assert aware.isoformat().endswith("+02:00")
    time.sleep(0.01)  # the server clock must have passed the target, or the request is a future value
    normalized = client.put(f"{API}/seen", headers=headers, json={"seen_through": aware.isoformat()})
    assert normalized.status_code == 200 and normalized.json()["seen_through"] == target.isoformat()
    db_session.expire_all()
    assert db_session.get(UserInboxState, user.id).seen_through == target
    assert summary(client, headers)["unread"]["total"] == 0


def test_direct_terminal_writes_surface_without_service_calls_or_events(client, db_session, monkeypatch):
    emitted = []
    monkeypatch.setattr("app.services.mission_service.emit_mission_status_change", lambda **kwargs: emitted.append(kwargs))
    now = datetime.utcnow()
    _, headers = actor(db_session, role="admin", created_at=now - timedelta(days=1))
    running = mission(db_session, "in_progress", started_at=now)
    stuck = mission(db_session, "in_progress", started_at=now)
    db_session.commit()
    assert summary(client, headers)["unread"]["total"] == 0

    # DeepSearch's fenced writer sets terminal state by direct SQL: status, completed_at and updated_at only.
    terminal = datetime.utcnow()
    db_session.execute(update(Mission).where(Mission.id == running.id).values(status="completed", completed_at=terminal, updated_at=terminal))
    db_session.execute(update(Mission).where(Mission.id == stuck.id).values(status="validation_failed", completed_at=terminal, updated_at=terminal))
    db_session.commit()
    assert summary(client, headers)["unread"] == {"failures": 1, "completions": 1, "evidence": 0, "total": 2}
    assert [item["id"] for item in section(client, headers, "completions")["items"]] == [str(running.id)]
    assert [item["id"] for item in section(client, headers, "failures")["items"]] == [str(stuck.id)]
    assert emitted == []


def test_evidence_section_shares_home_scope_including_the_project_owner_path(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    now = datetime.utcnow()
    owner, headers = actor(db_session, created_at=now - timedelta(days=1))
    other, _ = actor(db_session)
    space = Workspace(name="Someone else's Space")
    db_session.add(space)
    db_session.flush()
    db_session.add(SpaceMember(workspace_id=space.id, user_id=other.id))
    owned = Project(name="Owned from outside the Space", owner_id=owner.id, workspace_id=space.id)
    foreign = Project(name="Foreign project", owner_id=other.id, workspace_id=space.id)
    db_session.add_all([owned, foreign])
    db_session.flush()
    unreadable = mission(db_session, "completed", project_id=owned.id, owner_id=other.id, completed_at=now)
    evidence(db_session, owned, None, count=2, session_key="owner-scope")
    evidence(db_session, owned, unreadable.id, count=5, session_key="hidden-mission")
    evidence(db_session, foreign, None, count=3, session_key="foreign-scope")
    db_session.commit()

    home = client.get(HOME, headers=headers).json()["evidence_activity"]
    inbox = section(client, headers, "evidence")
    key = lambda g: (g["project_id"], g["mission_id"], g["session_key"], g["origin"], g["entry_count"])  # noqa: E731
    assert home["total"] == inbox["total"] == 1
    assert {key(g) for g in home["items"]} == {key(g) for g in inbox["items"]} == {(str(owned.id), None, "owner-scope", "deepsearch-worker", 2)}
    assert summary(client, headers)["unread"]["evidence"] == 1
    assert str(unreadable.id) not in inbox_text(client, headers) and str(foreign.id) not in inbox_text(client, headers)


def inbox_text(client, headers):
    return client.get(API, headers=headers, params={"section": "evidence"}).text + summary(client, headers).__repr__()


@pytest.mark.parametrize("params", [{}, {"section": "invented"}, {"section": "failures", "page": 0}, {"section": "failures", "page_size": 101}])
def test_list_validates_its_query(client, db_session, params):
    _, headers = actor(db_session)
    db_session.commit()
    assert client.get(API, headers=headers, params=params).status_code == 422


@pytest.mark.parametrize("rbac", [False, True])
@pytest.mark.parametrize("kind", ["jwt", "key"])
def test_every_inbox_route_rejects_service_and_anonymous_callers(client, db_session, monkeypatch, rbac, kind):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    _, headers = actor(db_session, kind, "service")
    db_session.commit()
    for method, path, body in [("get", f"{API}/summary", None), ("get", f"{API}?section=failures", None),
                               ("put", f"{API}/seen", {"seen_through": datetime.utcnow().isoformat()})]:
        assert client.request(method, path, headers=headers, json=body).status_code == 403
        assert client.request(method, path, json=body).status_code == 401
