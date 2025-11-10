"""Tests covering JWT authentication and CORS behavior."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _configured_password() -> str:
    if settings.auth_password:
        return settings.auth_password
    pytest.skip("AUTH_PASSWORD must be configured for auth endpoint tests")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_login_issues_bearer_token(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": settings.auth_username, "password": _configured_password()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["username"] == settings.auth_username
    assert payload["access_token"]
    assert payload["expires_in"] == settings.access_token_expire_minutes * 60


def test_login_rejects_invalid_password(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": settings.auth_username, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_refresh_requires_valid_token(client: TestClient):
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": settings.auth_username, "password": _configured_password()},
    )
    token = login_response.json()["access_token"]

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["access_token"]
    assert refreshed["user"]["username"] == settings.auth_username


def test_protected_route_blocks_anonymous_request(client: TestClient):
    response = client.get("/api/v1/missions/")
    assert response.status_code == 401


def test_cors_headers_reflect_allowed_origin(client: TestClient):
    allowed_origin = settings.cors_origins[0]
    response = client.get("/api/v1/health", headers={"Origin": allowed_origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin


def test_disallowed_origin_does_not_receive_cors_headers(client: TestClient):
    response = client.get("/api/v1/health", headers={"Origin": "https://malicious.example.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
