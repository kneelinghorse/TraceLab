"""RECOVER-1: restored routes authenticate and never leak another tenant's data."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.mission_events import MissionEvent, MissionEventBus
from app.core.security import (
    AuthenticatedUser,
    create_access_token,
    require_authenticated_user,
    require_authenticated_user_sse,
)
from app.main import app
from app.models.mission import Mission
from app.models.user import User


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def caller(monkeypatch):
    user = AuthenticatedUser(
        user_id=uuid4(),
        email="member@example.test",
        display_name="member",
        role="member",
    )
    monkeypatch.setitem(
        app.dependency_overrides, require_authenticated_user, lambda: user
    )
    monkeypatch.setitem(
        app.dependency_overrides, require_authenticated_user_sse, lambda: user
    )
    monkeypatch.setattr(settings, "rbac_enabled", True)
    return user


@pytest.fixture
def bus(monkeypatch):
    import app.core.mission_events as events

    bus = MissionEventBus()
    monkeypatch.setattr(events, "_event_bus", bus)
    return bus


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/missions/events/recent",
        "/api/v1/missions/events/stream",
        "/api/v1/decisions/linked",
        "/api/v1/decisions/linked/1",
    ],
)
def test_recovered_read_routes_require_auth(client, path):
    assert client.get(path).status_code == 401


def test_openapi_registers_restored_verbs_once():
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI < 0.141 eagerly flattens included routers.
        routes = app.routes
    else:
        routes = list(iter_route_contexts(app.routes))
    schema = app.openapi()
    expected = [
        ("/api/v1/missions/events/recent", "get"),
        ("/api/v1/missions/events/stream", "get"),
        ("/api/v1/missions/events/cmos", "post"),
        ("/api/v1/decisions/linked", "get"),
        ("/api/v1/decisions/linked/{decision_id}", "get"),
        ("/api/v1/decisions/linked/{decision_id}/evidence", "post"),
    ]
    for path, verb in expected:
        assert verb in schema["paths"][path]
        assert (
            sum(
                r.path == path and verb.upper() in getattr(r, "methods", ())
                for r in routes
            )
            == 1
        )


@pytest.mark.parametrize("role", ["member", "viewer", "service"])
def test_global_cmos_decisions_deny_non_admin_before_read_or_write(
    client, caller, monkeypatch, role
):
    import app.api.v1.decision_links as links

    user = AuthenticatedUser(
        user_id=caller.user_id,
        email=caller.email,
        display_name=caller.display_name,
        role=role,
    )
    monkeypatch.setitem(
        app.dependency_overrides, require_authenticated_user, lambda: user
    )
    monkeypatch.setattr(
        links, "_query_cmos", lambda *_: pytest.fail("unauthorized CMOS read")
    )
    monkeypatch.setattr(
        links, "_update_cmos", lambda *_: pytest.fail("unauthorized CMOS write")
    )
    assert client.get("/api/v1/decisions/linked").status_code == 403
    assert client.get("/api/v1/decisions/linked/1").status_code == 403
    assert (
        client.post(
            "/api/v1/decisions/linked/1/evidence",
            json={"evidence": [{"type": "document", "id": str(uuid4())}]},
        ).status_code
        == 403
    )


def test_recent_events_filter_before_limit_and_deny_global_events(
    client, caller, bus, db_session
):
    own = Mission(
        mission_id="own",
        title="Visible",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=caller.user_id,
    )
    foreign = Mission(
        mission_id="foreign",
        title="Private",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=uuid4(),
    )
    db_session.add_all([own, foreign])
    db_session.commit()
    bus.emit(
        MissionEvent(
            event_type="mission.started", timestamp="now", mission_id=str(own.id)
        )
    )
    bus.emit(
        MissionEvent(
            event_type="mission.started", timestamp="now", mission_id=str(foreign.id)
        )
    )
    bus.emit(
        MissionEvent(
            event_type="cmos.mission.started", timestamp="now", mission_id="own"
        )
    )
    bus.emit(
        MissionEvent(
            event_type="pedr.layer_completed",
            timestamp="now",
            details={"query": "private"},
        )
    )
    response = client.get("/api/v1/missions/events/recent?limit=1")
    assert response.status_code == 200
    assert [e["mission_id"] for e in response.json()] == [str(own.id)]


@pytest.mark.parametrize("role", ["owner", "admin", "member", "viewer"])
def test_cmos_bridge_denies_real_human_credentials(
    client, db_session, bus, monkeypatch, role
):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        email=f"bridge-{uuid4().hex}@example.test",
        display_name="Bridge human principal",
        password_hash="placeholder-not-a-real-hash",  # noqa: S106 - JWT fixture
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(subject=str(user.id))
    payload = {
        "mission_id": "RECOVER-1",
        "name": "Recovery",
        "new_status": "In Progress",
    }
    assert client.post("/api/v1/missions/events/cmos", json=payload).status_code == 401
    response = client.post(
        "/api/v1/missions/events/cmos",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 403
    assert bus.get_recent_events() == []


def test_human_mission_ids_are_scoped_without_uuid_alias_confusion(
    client, caller, bus, db_session
):
    own = Mission(
        mission_id="RECOVER-visible",
        title="Visible",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=caller.user_id,
    )
    foreign = Mission(
        mission_id="RECOVER-private",
        title="Private",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=uuid4(),
    )
    db_session.add_all([own, foreign])
    db_session.flush()
    alias = Mission(
        mission_id=str(foreign.id),
        title="Alias",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=caller.user_id,
    )
    db_session.add(alias)
    db_session.commit()
    for ref in [own.mission_id, foreign.mission_id, str(alias.id), str(foreign.id)]:
        bus.emit(
            MissionEvent(event_type="mission.started", timestamp="now", mission_id=ref)
        )
    response = client.get("/api/v1/missions/events/recent")
    assert response.status_code == 200
    assert [e["mission_id"] for e in response.json()] == [own.mission_id, str(alias.id)]


def test_eventsource_query_token_is_accepted_at_the_actual_mount(
    client, auth_headers, bus, monkeypatch
):
    async def finite_events(**_):
        yield MissionEvent(event_type="system.heartbeat", timestamp="now")

    monkeypatch.setattr(bus, "subscribe", finite_events)
    token = auth_headers["Authorization"].split()[1]
    response = client.get("/api/v1/missions/events/stream", params={"token": token})
    assert response.status_code == 200
    assert "event: system.heartbeat" in response.text


@pytest.mark.asyncio
async def test_sse_replay_and_live_events_recheck_mission_access(
    caller, bus, db_session
):
    from app.api.v1.mission_events import stream_mission_events

    own = Mission(
        mission_id="stream-own",
        title="Visible",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=caller.user_id,
    )
    foreign = Mission(
        mission_id="stream-foreign",
        title="Private",
        objective="Scope",
        success_criteria=["Scope"],
        owner_id=uuid4(),
    )
    db_session.add_all([own, foreign])
    db_session.commit()
    bus.emit(
        MissionEvent(
            event_type="mission.started", timestamp="now", mission_id=str(own.id)
        )
    )
    bus.emit(
        MissionEvent(
            event_type="mission.started", timestamp="now", mission_id=str(foreign.id)
        )
    )
    response = await stream_mission_events(limit=1, _user=caller)
    stream = response.body_iterator
    first = await anext(stream)
    assert str(own.id) in first and str(foreign.id) not in first
    assert (
        bus.subscriber_count == 1
    ), "Subscription must start before yielding replay to avoid losing live events"
    own.owner_id = uuid4()
    db_session.commit()
    bus.emit(
        MissionEvent(
            event_type="mission.completed", timestamp="now", mission_id=str(own.id)
        )
    )
    bus.emit(MissionEvent(event_type="system.heartbeat", timestamp="now"))
    assert "system.heartbeat" in await anext(stream)
    await stream.aclose()
    assert bus.subscriber_count == 0


def test_admin_decision_reads_and_evidence_write_use_protected_route(
    client, caller, monkeypatch
):
    from unittest.mock import MagicMock

    from app.api.v1 import decision_links

    admin = AuthenticatedUser(
        user_id=caller.user_id,
        email=caller.email,
        display_name=caller.display_name,
        role="admin",
    )
    monkeypatch.setitem(
        app.dependency_overrides, require_authenticated_user, lambda: admin
    )
    row = {
        "id": 1,
        "decision_text": "Recovery decision",
        "created_at": "2026-09-12",
        "evidence": "[]",
    }
    query = MagicMock(return_value=[row])
    update = MagicMock(return_value=1)
    monkeypatch.setattr(decision_links, "_query_cmos", query)
    monkeypatch.setattr(decision_links, "_update_cmos", update)
    assert client.get("/api/v1/decisions/linked").json()[0]["id"] == 1
    assert client.get("/api/v1/decisions/linked/1").json()["id"] == 1
    response = client.post(
        "/api/v1/decisions/linked/1/evidence",
        json={"evidence": [{"type": "document", "id": str(uuid4())}]},
    )
    assert response.status_code == 200
    update.assert_called_once()


def test_full_pedr_http_preserves_diagnostics_and_emits_layer_events(
    client, auth_headers, monkeypatch, bus
):
    from app.api.v1 import pedr_search
    from app.services.pedr.search_orchestrator import PEDRConfig, PEDRSearchOrchestrator

    def failing(**_):
        raise TimeoutError("provider unavailable")

    search = PEDRSearchOrchestrator(
        config=PEDRConfig(enable_graph=False),
        lexical_search=failing,
        semantic_search=lambda **_: [
            {"chunk_id": "healthy", "content": "Research", "score": 0.9}
        ],
        telemetry_enabled=False,
    )
    monkeypatch.setattr(pedr_search, "_get_pedr_orchestrator", lambda: search)
    response = client.post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={"query": "recovery events", "enable_graph": False, "rerank_mode": "full"},
    )
    assert response.status_code == 200
    assert response.json()["metadata"]["degraded"] is True
    assert len(response.json()["metadata"]["layer_diagnostics"]) == 6
    events = bus.get_recent_events()
    assert any(
        e.event_type == "pedr.layer_failed" and e.layer == "lexical" for e in events
    )
    assert any(
        e.event_type == "pedr.layer_completed" and e.layer == "semantic" for e in events
    )
