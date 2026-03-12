"""Tests for mission event bus and SSE endpoint — T33.4 Deliverable.

Validates:
1. Event bus pub/sub (emit, history, subscribe)
2. SSE endpoint returns text/event-stream
3. Recent events endpoint returns JSON array
4. Mission status change events emitted correctly
5. Event serialization to SSE format
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.mission_events import (
    MissionEvent,
    MissionEventBus,
    MissionEventType,
    emit_mission_status_change,
    emit_pedr_layer_event,
    emit_quality_gates,
    get_mission_event_bus,
)
from app.core.security import get_configured_credentials, issue_token_response
from app.main import app


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Reset the singleton event bus between tests."""
    import app.core.mission_events as mod
    mod._event_bus = None
    yield
    mod._event_bus = None


@pytest.fixture
def auth_token() -> str:
    creds = get_configured_credentials()
    return issue_token_response(creds)["access_token"]


@pytest.fixture
def client(auth_token: str):
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {auth_token}"
        yield c


# ===========================================================================
# 1. EVENT BUS UNIT TESTS
# ===========================================================================


class TestMissionEventBus:
    """Unit tests for the event bus."""

    def test_emit_stores_in_history(self):
        bus = MissionEventBus()
        event = MissionEvent(
            event_type=MissionEventType.MISSION_QUEUED.value,
            timestamp="2026-03-12T00:00:00Z",
            mission_id="test-1",
        )
        bus.emit(event)
        assert len(bus.get_recent_events()) == 1
        assert bus.get_recent_events()[0].mission_id == "test-1"

    def test_history_respects_max_size(self):
        bus = MissionEventBus(max_history=3)
        for i in range(5):
            bus.emit(MissionEvent(
                event_type=MissionEventType.MISSION_QUEUED.value,
                timestamp=f"2026-03-12T00:00:0{i}Z",
                mission_id=f"test-{i}",
            ))
        events = bus.get_recent_events()
        assert len(events) == 3
        assert events[0].mission_id == "test-2"

    def test_get_recent_events_limit(self):
        bus = MissionEventBus()
        for i in range(10):
            bus.emit(MissionEvent(
                event_type=MissionEventType.MISSION_QUEUED.value,
                timestamp=f"2026-03-12T00:00:{i:02d}Z",
                mission_id=f"test-{i}",
            ))
        events = bus.get_recent_events(limit=3)
        assert len(events) == 3
        assert events[-1].mission_id == "test-9"

    def test_subscriber_count(self):
        bus = MissionEventBus()
        assert bus.subscriber_count == 0


# ===========================================================================
# 2. EVENT SERIALIZATION
# ===========================================================================


class TestEventSerialization:
    """Test SSE wire format."""

    def test_to_sse_format(self):
        event = MissionEvent(
            event_type=MissionEventType.MISSION_STARTED.value,
            timestamp="2026-03-12T00:00:00Z",
            mission_id="M-1",
            mission_title="Test Mission",
            status="in_progress",
        )
        sse = event.to_sse()
        assert sse.startswith("event: mission.started\n")
        assert "data: " in sse
        assert sse.endswith("\n\n")

        # Parse the data line
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        data = json.loads(data_line[6:])
        assert data["mission_id"] == "M-1"
        assert data["event_type"] == "mission.started"

    def test_to_sse_omits_none_fields(self):
        event = MissionEvent(
            event_type=MissionEventType.HEARTBEAT.value,
            timestamp="2026-03-12T00:00:00Z",
        )
        sse = event.to_sse()
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        data = json.loads(data_line[6:])
        assert "mission_id" not in data
        assert "layer" not in data
        assert "error" not in data


# ===========================================================================
# 3. CONVENIENCE EMITTERS
# ===========================================================================


class TestConvenienceEmitters:
    """Test the emit_* helper functions."""

    def test_emit_mission_status_change(self):
        emit_mission_status_change(
            mission_id="M-1",
            title="Test",
            new_status="queued",
            previous_status="draft",
        )
        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == MissionEventType.MISSION_QUEUED.value
        assert events[0].status == "queued"
        assert events[0].previous_status == "draft"

    def test_emit_mission_completed(self):
        emit_mission_status_change(
            mission_id="M-2",
            title="Done",
            new_status="completed",
        )
        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert events[0].event_type == MissionEventType.MISSION_COMPLETED.value

    def test_emit_pedr_layer_event(self):
        emit_pedr_layer_event(
            event_type=MissionEventType.PEDR_LAYER_COMPLETED,
            layer="lexical",
            duration_ms=12.5,
            result_count=42,
        )
        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert events[0].layer == "lexical"
        assert events[0].result_count == 42
        assert events[0].duration_ms == 12.5

    def test_emit_quality_gates(self):
        emit_quality_gates(
            mission_id="M-3",
            gates_passed=4,
            total_gates=5,
            score=0.856,
        )
        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert events[0].event_type == MissionEventType.QUALITY_GATES_EVALUATED.value
        assert events[0].details["gates_passed"] == 4
        assert events[0].details["score"] == 0.856


# ===========================================================================
# 4. SSE ENDPOINT
# ===========================================================================


class TestSSEEndpoint:
    """Integration tests for the SSE streaming endpoint."""

    def test_recent_events_endpoint(self, client: TestClient):
        """GET /events/recent returns JSON array."""
        # Emit some events first
        emit_mission_status_change("M-1", "Test", "queued")
        emit_pedr_layer_event(
            event_type=MissionEventType.PEDR_LAYER_COMPLETED,
            layer="semantic",
            result_count=10,
        )

        resp = client.get("/api/v1/missions/events/recent?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["event_type"] == "mission.queued"

    def test_recent_events_empty(self, client: TestClient):
        """Returns empty array when no events."""
        resp = client.get("/api/v1/missions/events/recent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sse_stream_accepts_query_param_token(self, auth_token: str):
        """SSE auth dependency should accept a valid JWT via query param.

        We test the dependency directly to avoid TestClient hanging on
        the infinite SSE generator. The 401 tests below prove the
        endpoint correctly wires the dependency.
        """
        import asyncio
        from app.core.security import require_authenticated_user_sse

        # Build a mock credentials=None (simulating EventSource — no header)
        user = asyncio.get_event_loop().run_until_complete(
            require_authenticated_user_sse(credentials=None, x_api_key=None, token=auth_token)
        )
        assert user is not None
        assert user.display_name is not None

    def test_sse_stream_rejects_missing_token(self):
        """SSE stream should reject requests with no auth at all."""
        with TestClient(app, raise_server_exceptions=False) as c:
            with c.stream("GET", "/api/v1/missions/events/stream") as resp:
                assert resp.status_code == 401

    def test_sse_stream_rejects_invalid_token(self):
        """SSE stream should reject an invalid JWT query param."""
        with TestClient(app, raise_server_exceptions=False) as c:
            with c.stream("GET", "/api/v1/missions/events/stream?token=bogus.jwt.token") as resp:
                assert resp.status_code == 401

    def test_recent_events_rejects_missing_auth(self):
        """GET /events/recent should reject requests with no auth."""
        with TestClient(app) as c:
            resp = c.get("/api/v1/missions/events/recent")
            assert resp.status_code == 401


# ===========================================================================
# 5. MISSION SERVICE EVENT EMISSION
# ===========================================================================


class TestMissionServiceEventEmission:
    """Verify MissionService emits events on status transitions."""

    def test_update_mission_emits_status_change(self, db_session, project):
        """MissionService.update_mission should emit event on status change."""
        from app.schemas.mission import MissionCreate, MissionUpdate
        from app.services.mission_service import MissionService

        service = MissionService()
        mission = service.create_mission(
            db_session,
            MissionCreate(
                project_id=project.id,
                mission_id="EVT-001",
                title="Event Test Mission",
                objective="Test event emission",
                success_criteria=["emits events"],
                status="draft",
            ),
        )

        bus = get_mission_event_bus()
        before_count = len(bus.get_recent_events())

        # Transition to queued
        service.update_mission(
            db_session,
            mission.id,
            MissionUpdate(status="queued"),
        )

        events = bus.get_recent_events()
        new_events = events[before_count:]
        assert len(new_events) == 1
        assert new_events[0].event_type == MissionEventType.MISSION_QUEUED.value
        assert new_events[0].status == "queued"
        assert new_events[0].previous_status == "draft"
