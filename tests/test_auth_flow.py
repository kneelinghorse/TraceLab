"""Comprehensive auth flow coverage for login, refresh, and protected routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.conftest import get_seed_user_email


def _configured_password() -> str:
    if settings.auth_password:
        return settings.auth_password
    pytest.skip("AUTH_PASSWORD must be configured for auth flow tests")


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": get_seed_user_email(), "password": _configured_password()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_returns_full_payload(client: TestClient):
    payload = _login(client)
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == settings.access_token_expire_minutes * 60
    assert payload["user"]["display_name"] == settings.auth_username
    assert (
        isinstance(payload["access_token"], str) and len(payload["access_token"]) > 20
    )


def test_login_rejects_unknown_email(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": _configured_password()},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_refresh_requires_authorization_header(client: TestClient):
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert "Missing Authorization" in response.json()["detail"]


def test_refresh_rejects_tampered_token(client: TestClient):
    payload = _login(client)
    tampered = payload["access_token"][:-2] + "zz"
    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert response.status_code == 401


def test_refresh_issues_new_token_and_preserves_identity(client: TestClient):
    payload = _login(client)
    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["user"]["display_name"] == settings.auth_username
    assert isinstance(refreshed["access_token"], str) and refreshed["access_token"]
    follow_up = client.get(
        "/api/v1/missions/",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
    )
    assert follow_up.status_code == 200


def test_protected_route_allows_valid_token(client: TestClient):
    payload = _login(client)
    response = client.get(
        "/api/v1/missions/",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code == 200
