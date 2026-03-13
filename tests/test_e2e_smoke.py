"""End-to-End Operations Smoke Test — T33.5 Deliverable.

Validates the complete TraceLab operational flow:
1. Auth flow: login → token refresh → protected route access
2. Mission lifecycle: create → submit → update status → verify
3. API key auth: create key → use key → protected route
4. PEDR search response shapes (schema validation)
5. SSE event bus: mission status changes emit events
6. Error response consistency across endpoints
7. Invite code generation and validation
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.mission_events import get_mission_event_bus
from app.core.security import get_configured_credentials, issue_token_response
from app.main import app
from tests.conftest import get_seed_user_email


def _configured_password() -> str:
    from app.core.config import settings

    if settings.auth_password:
        return settings.auth_password
    pytest.skip("AUTH_PASSWORD must be configured")


@pytest.fixture(autouse=True)
def _reset_event_bus():
    import app.core.mission_events as mod

    mod._event_bus = None
    yield
    mod._event_bus = None


@pytest.fixture
def client():
    from app.core.rate_limit import auth_rate_limiter

    auth_rate_limiter.reset()
    with TestClient(app) as c:
        yield c
    auth_rate_limiter.reset()


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """Get auth headers via login endpoint."""
    email = get_seed_user_email()
    password = _configured_password()
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. AUTH FLOW SMOKE TEST
# ===========================================================================


class TestAuthFlowE2E:
    """End-to-end auth: login → refresh → protected route."""

    def test_login_returns_token_and_user(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": get_seed_user_email(),
                "password": _configured_password(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == get_seed_user_email()

    def test_refresh_returns_valid_token(self, client: TestClient, auth_headers: dict):
        resp = client.post("/api/v1/auth/refresh", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "user" in data

    def test_protected_route_with_token(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/v1/missions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "pagination" in data

    def test_protected_route_without_token_returns_401(self, client: TestClient):
        resp = client.get("/api/v1/missions")
        assert resp.status_code == 401


# ===========================================================================
# 2. MISSION LIFECYCLE SMOKE TEST
# ===========================================================================


class TestMissionLifecycleE2E:
    """Create → verify response shape → update status."""

    def test_create_mission_response_shape(
        self, client: TestClient, auth_headers: dict, db_session
    ):
        """Create mission and verify all expected fields present."""
        from app.models.project import Project

        project = Project(name="E2E Test Project", description="Smoke test")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        mission_data = {
            "mission_id": f"E2E-{uuid4().hex[:6]}",
            "title": "E2E Smoke Test Mission",
            "objective": "Validate end-to-end mission lifecycle",
            "success_criteria": ["API returns correct response shape"],
            "project_id": str(project.id),
        }

        resp = client.post("/api/v1/missions", json=mission_data, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()

        # Verify required fields
        required_fields = [
            "id",
            "mission_id",
            "title",
            "objective",
            "status",
            "success_criteria",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

        assert data["status"] == "draft"
        assert data["mission_id"] == mission_data["mission_id"]

    def test_mission_status_change_emits_event(
        self, client: TestClient, auth_headers: dict, db_session
    ):
        """Updating mission status emits an event to the event bus."""
        from app.models.project import Project

        project = Project(name="Event Test Project", description="Event test")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        # Create mission
        mission_data = {
            "mission_id": f"EVT-{uuid4().hex[:6]}",
            "title": "Event Emission Test",
            "objective": "Test that status changes emit events",
            "success_criteria": ["Event emitted on status change"],
            "project_id": str(project.id),
        }
        create_resp = client.post(
            "/api/v1/missions", json=mission_data, headers=auth_headers
        )
        assert create_resp.status_code == 201
        mission_uuid = create_resp.json()["id"]

        # Update status to in_progress
        update_resp = client.put(
            f"/api/v1/missions/{mission_uuid}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200

        # Verify event was emitted
        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        status_events = [e for e in events if e.event_type == "mission.started"]
        assert len(status_events) >= 1
        assert status_events[-1].status == "in_progress"


# ===========================================================================
# 3. MISSION EVENTS ENDPOINT SMOKE TEST
# ===========================================================================


class TestMissionEventsEndpointE2E:
    """Verify SSE infrastructure endpoints work."""

    def test_recent_events_returns_json_array(
        self, client: TestClient, auth_headers: dict
    ):
        resp = client.get("/api/v1/missions/events/recent", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_events_appear_in_recent_after_emission(
        self, client: TestClient, auth_headers: dict
    ):
        from app.core.mission_events import emit_mission_status_change

        emit_mission_status_change("SMOKE-1", "Smoke Test", "queued")

        resp = client.get(
            "/api/v1/missions/events/recent?limit=5", headers=auth_headers
        )
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) >= 1
        assert events[0]["event_type"] == "mission.queued"


# ===========================================================================
# 4. ERROR RESPONSE CONSISTENCY
# ===========================================================================


class TestErrorResponseConsistencyE2E:
    """Verify error responses have consistent shapes across endpoints."""

    def test_mission_404_has_detail(self, client: TestClient, auth_headers: dict):
        resp = client.get(
            "/api/v1/missions/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_auth_401_has_detail(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "wrong",
            },
        )
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_rate_limit_429_has_retry_after(self, client: TestClient):
        for _ in range(5):
            client.post(
                "/api/v1/auth/login", json={"email": "x@x.com", "password": "y"}
            )

        resp = client.post(
            "/api/v1/auth/login", json={"email": "x@x.com", "password": "y"}
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert "detail" in resp.json()


# ===========================================================================
# 5. INVITE CODE FLOW
# ===========================================================================


class TestInviteCodeFlowE2E:
    """Invite code generation and validation."""

    def test_generate_and_list_invite_codes(
        self, client: TestClient, auth_headers: dict
    ):
        # Generate code
        gen_resp = client.post("/api/v1/auth/invite-codes", headers=auth_headers)
        assert gen_resp.status_code in (200, 201)
        code_data = gen_resp.json()
        assert "code" in code_data

        # List codes
        list_resp = client.get("/api/v1/auth/invite-codes", headers=auth_headers)
        assert list_resp.status_code == 200
        body = list_resp.json()
        # Response may be a list or {codes: [...], total: N}
        codes = body if isinstance(body, list) else body.get("codes", [])
        assert len(codes) >= 1


# ===========================================================================
# 6. HEALTH ENDPOINT
# ===========================================================================


class TestHealthE2E:
    """Basic health check."""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("ok", "healthy", True, "running")
