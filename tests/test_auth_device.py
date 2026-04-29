"""Tests for the RFC 8628 device-authorization flow (T42.4).

Covers the full lifecycle: device/code → poll → approve in browser →
device/token returns the minted key. Plus the negative paths (slow_down,
expired, denied, unknown user_code, already approved, 10-key cap).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import auth_device as device_module
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from tests.conftest import get_seed_user_email


def _password() -> str:
    if not settings.auth_password:
        pytest.skip("AUTH_PASSWORD must be configured for device-auth tests")
    return settings.auth_password


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Log in as the seed user and return a JWT for the web /device flow."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": get_seed_user_email(), "password": _password()},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _request_device_code(
    client: TestClient, user_agent: str = "tracelab-mcp/1.0.0 (darwin; laptop.local)"
) -> dict:
    response = client.post(
        "/api/v1/auth/device/code", headers={"User-Agent": user_agent}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _set_grant_last_polled_to(user_code: str, dt: datetime) -> None:
    """Test helper — bypass the polling-interval throttle by ageing the grant."""
    session = SessionLocal()
    try:
        grant = (
            session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == user_code)
            .first()
        )
        assert grant is not None
        grant.last_polled_at = dt
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /device/code
# ---------------------------------------------------------------------------


def test_request_device_code_returns_envelope(client: TestClient):
    body = _request_device_code(client)
    assert "device_code" in body and len(body["device_code"]) >= 32
    assert body["user_code"].count("-") == 1
    assert body["verification_uri"].endswith("/device")
    assert body["expires_in"] == device_module.DEVICE_CODE_TTL_SECONDS
    assert body["interval"] == device_module.DEVICE_CODE_POLL_INTERVAL_SECONDS


def test_request_device_code_persists_user_agent_label(client: TestClient):
    body = _request_device_code(
        client, user_agent="tracelab-mcp/0.1.2 (linux; jenkins-agent-7)"
    )
    session = SessionLocal()
    try:
        grant = (
            session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == body["user_code"])
            .first()
        )
        assert grant is not None
        assert grant.client_label == "tracelab-mcp/0.1.2 (linux; jenkins-agent-7)"
        assert grant.status == "pending"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /device/token — pending / slow_down / expired
# ---------------------------------------------------------------------------


def test_poll_token_returns_authorization_pending_when_unapproved(
    client: TestClient,
):
    body = _request_device_code(client)
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "authorization_pending"


def test_poll_token_returns_slow_down_when_polled_too_fast(client: TestClient):
    body = _request_device_code(client)
    # First poll establishes last_polled_at
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.json()["detail"]["error"] == "authorization_pending"
    # Second poll right after the first — still pending but should slow_down
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "slow_down"


def test_poll_token_returns_expired_token_for_unknown_device_code(
    client: TestClient,
):
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": "definitely-not-real-xxxxx"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "expired_token"


def test_poll_token_expires_grant_past_ttl(client: TestClient):
    body = _request_device_code(client)
    # Force the grant past expires_at
    session = SessionLocal()
    try:
        grant = (
            session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == body["user_code"])
            .first()
        )
        grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "expired_token"


# ---------------------------------------------------------------------------
# /device/grants/{user_code} — preview before approve
# ---------------------------------------------------------------------------


def test_grant_preview_requires_authentication(client: TestClient):
    body = _request_device_code(client)
    response = client.get(f"/api/v1/auth/device/grants/{body['user_code']}")
    assert response.status_code == 401


def test_grant_preview_surfaces_client_label(
    client: TestClient, auth_token: str
):
    body = _request_device_code(
        client, user_agent="tracelab-mcp/0.9.9 (darwin; user-mac)"
    )
    response = client.get(
        f"/api/v1/auth/device/grants/{body['user_code']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["client_label"] == "tracelab-mcp/0.9.9 (darwin; user-mac)"
    assert payload["status"] == "pending"


def test_grant_preview_404_for_unknown_code(client: TestClient, auth_token: str):
    response = client.get(
        "/api/v1/auth/device/grants/AAAA-BBBB",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /device/approve — happy path + edge cases
# ---------------------------------------------------------------------------


def test_approve_unauthenticated_returns_401(client: TestClient):
    body = _request_device_code(client)
    response = client.post(
        "/api/v1/auth/device/approve",
        json={"user_code": body["user_code"]},
    )
    assert response.status_code == 401


def test_approve_mints_api_key_and_links_to_grant(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    response = client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"], "label": "MyLaptop"},
    )
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved["label"] == "MyLaptop"
    assert approved["user_code"] == body["user_code"]
    # Grant should be flagged + an api_keys row should exist for the user
    session = SessionLocal()
    try:
        grant = (
            session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == body["user_code"])
            .first()
        )
        assert grant.status == "approved"
        assert grant.api_key_id is not None
        api_key = session.query(APIKey).filter(APIKey.id == grant.api_key_id).first()
        assert api_key is not None
        assert api_key.name == "MyLaptop"
        assert api_key.key_prefix.startswith("tl_")
    finally:
        session.close()


def test_approve_uses_user_agent_as_default_label(
    client: TestClient, auth_token: str
):
    body = _request_device_code(
        client, user_agent="tracelab-mcp/2.3.4 (darwin; my-host)"
    )
    response = client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"]},
    )
    assert response.status_code == 200
    assert response.json()["label"] == "tracelab-mcp/2.3.4 (darwin; my-host)"


def test_approve_404_for_unknown_user_code(client: TestClient, auth_token: str):
    response = client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": "AAAA-BBBB"},
    )
    assert response.status_code == 404


def test_approve_already_approved_returns_409(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    headers = {"Authorization": f"Bearer {auth_token}"}
    first = client.post(
        "/api/v1/auth/device/approve",
        headers=headers,
        json={"user_code": body["user_code"]},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/device/approve",
        headers=headers,
        json={"user_code": body["user_code"]},
    )
    assert second.status_code == 409


def test_approve_expired_grant_returns_410(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    session = SessionLocal()
    try:
        grant = (
            session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == body["user_code"])
            .first()
        )
        grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
    response = client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"]},
    )
    assert response.status_code == 410


def test_approve_respects_10_key_cap(client: TestClient, auth_token: str):
    """Per-user 10-key cap mirrors the web /api-keys POST endpoint."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    # Mint 10 keys via the existing API-keys endpoint to reach the cap
    for i in range(10):
        client.post(
            "/api/v1/auth/api-keys",
            headers=headers,
            json={"name": f"existing-{i}"},
        )
    # 11th approval attempt should hit the rate limit
    body = _request_device_code(client)
    response = client.post(
        "/api/v1/auth/device/approve",
        headers=headers,
        json={"user_code": body["user_code"]},
    )
    assert response.status_code == 429


# ---------------------------------------------------------------------------
# /device/token — approved path delivers the plaintext exactly once
# ---------------------------------------------------------------------------


def test_poll_token_returns_minted_key_after_approval(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"], "label": "DevicePollKey"},
    )
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "api_key"
    assert payload["access_token"].startswith("tl_")
    assert payload["key"] == payload["access_token"]
    assert payload["label"] == "DevicePollKey"


def test_poll_token_after_approval_yields_plaintext_only_once(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"]},
    )
    first = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert first.status_code == 200
    # Age the grant so the second poll passes the polling-interval throttle
    _set_grant_last_polled_to(
        body["user_code"], datetime.utcnow() - timedelta(seconds=10)
    )
    second = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert second.status_code == 400
    assert second.json()["detail"]["error"] == "access_denied"


def test_minted_key_authenticates_against_protected_endpoint(
    client: TestClient, auth_token: str
):
    """End-to-end: the device-flow-minted key works as X-API-Key."""
    body = _request_device_code(client)
    client.post(
        "/api/v1/auth/device/approve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"]},
    )
    poll = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    plaintext = poll.json()["access_token"]
    assert plaintext.startswith("tl_")
    # Hit any protected endpoint with X-API-Key
    response = client.get("/api/v1/auth/me", headers={"X-API-Key": plaintext})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /device/deny
# ---------------------------------------------------------------------------


def test_deny_makes_subsequent_polls_fail_immediately(
    client: TestClient, auth_token: str
):
    body = _request_device_code(client)
    response = client.post(
        "/api/v1/auth/device/deny",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": body["user_code"]},
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1/auth/device/token", json={"device_code": body["device_code"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "access_denied"


def test_deny_unknown_user_code_returns_404(
    client: TestClient, auth_token: str
):
    response = client.post(
        "/api/v1/auth/device/deny",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"user_code": "AAAA-BBBB"},
    )
    assert response.status_code == 404
