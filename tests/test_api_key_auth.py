"""Tests for API key authentication and management."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    API_KEY_PREFIX,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
    verify_api_key,
)
from app.main import app


def _configured_password() -> str:
    if settings.auth_password:
        return settings.auth_password
    pytest.skip("AUTH_PASSWORD must be configured for auth endpoint tests")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """Get JWT auth headers for creating/managing API keys."""
    # Login with email (seed user email is {auth_username}@tracelab.local)
    email = settings.auth_username if "@" in settings.auth_username else f"{settings.auth_username}@tracelab.local"
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _configured_password()},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAPIKeyGeneration:
    """Test the API key generation utilities."""

    def test_generate_api_key_has_correct_prefix(self):
        key = generate_api_key()
        assert key.startswith(API_KEY_PREFIX)

    def test_generate_api_key_has_correct_length(self):
        key = generate_api_key()
        # tl_ (3) + 32 chars = 35
        assert len(key) >= 35

    def test_generate_api_key_is_unique(self):
        keys = [generate_api_key() for _ in range(100)]
        assert len(set(keys)) == 100

    def test_hash_and_verify_api_key(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed)
        assert not verify_api_key("wrong_key", hashed)

    def test_get_key_prefix(self):
        key = generate_api_key()
        prefix = get_key_prefix(key)
        assert prefix.startswith(API_KEY_PREFIX)
        assert len(prefix) == len(API_KEY_PREFIX) + 8  # tl_ + 8 chars


class TestAPIKeyManagement:
    """Test API key CRUD endpoints."""

    def test_create_api_key(self, client: TestClient, auth_headers: dict):
        response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Test Key"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Key"
        assert data["key"].startswith(API_KEY_PREFIX)
        assert data["key_prefix"].startswith(API_KEY_PREFIX)
        assert data["id"]
        assert data["created_at"]
        assert data["expires_at"] is None

    def test_create_api_key_with_expiration(self, client: TestClient, auth_headers: dict):
        response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Expiring Key", "expires_in_days": 30},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None

    def test_create_api_key_requires_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Unauthorized Key"},
        )
        assert response.status_code == 401

    def test_list_api_keys(self, client: TestClient, auth_headers: dict):
        # Create a key first
        client.post(
            "/api/v1/auth/api-keys",
            json={"name": "List Test Key"},
            headers=auth_headers,
        )

        response = client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert "total" in data
        assert data["total"] >= 1
        # Key value should NOT be in list response
        for key_info in data["keys"]:
            assert "key" not in key_info
            assert "key_prefix" in key_info

    def test_delete_api_key(self, client: TestClient, auth_headers: dict):
        # Create a key
        create_response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Delete Test Key"},
            headers=auth_headers,
        )
        key_id = create_response.json()["id"]

        # Delete it
        delete_response = client.delete(
            f"/api/v1/auth/api-keys/{key_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True

        # Verify it's gone from list
        list_response = client.get("/api/v1/auth/api-keys", headers=auth_headers)
        key_ids = [k["id"] for k in list_response.json()["keys"]]
        assert key_id not in key_ids

    def test_delete_nonexistent_key(self, client: TestClient, auth_headers: dict):
        response = client.delete(
            "/api/v1/auth/api-keys/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestAPIKeyAuthentication:
    """Test using API keys to authenticate requests."""

    def test_api_key_authenticates_protected_endpoint(self, client: TestClient, auth_headers: dict):
        # Create an API key
        create_response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Auth Test Key"},
            headers=auth_headers,
        )
        api_key = create_response.json()["key"]

        # Use the API key to access a protected endpoint
        response = client.get(
            "/api/v1/projects/",
            headers={"X-API-Key": api_key},
        )
        # Should succeed (may return empty list but not 401)
        assert response.status_code == 200

    def test_invalid_api_key_rejected(self, client: TestClient):
        response = client.get(
            "/api/v1/projects/",
            headers={"X-API-Key": "tl_invalid_key_12345678901234567890"},
        )
        assert response.status_code == 401

    def test_malformed_api_key_rejected(self, client: TestClient):
        response = client.get(
            "/api/v1/projects/",
            headers={"X-API-Key": "not_a_valid_key"},
        )
        assert response.status_code == 401

    def test_api_key_takes_priority_over_jwt(self, client: TestClient, auth_headers: dict):
        # Create an API key
        create_response = client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Priority Test Key"},
            headers=auth_headers,
        )
        api_key = create_response.json()["key"]

        # Send both API key and JWT - API key should be used
        combined_headers = {
            **auth_headers,
            "X-API-Key": api_key,
        }
        response = client.get("/api/v1/projects/", headers=combined_headers)
        assert response.status_code == 200

    def test_jwt_still_works(self, client: TestClient, auth_headers: dict):
        # Ensure JWT auth still works without API key
        response = client.get("/api/v1/projects/", headers=auth_headers)
        assert response.status_code == 200
