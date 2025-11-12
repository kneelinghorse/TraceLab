"""Tests for Qdrant admin endpoints."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.admin import get_admin_qdrant_service
from app.core.config import settings
from app.main import app


class _FakeQdrantClient:
    """Minimal stub that behaves like the qdrant-client for tests."""

    def __init__(self, *, collection_name: str, exists: bool, raise_errors: bool = False):
        self._collection_name = collection_name
        self.collection_exists = exists
        self.raise_errors = raise_errors

    def get_collections(self):
        if self.raise_errors:
            raise RuntimeError("Qdrant unavailable")
        collections = []
        if self.collection_exists:
            collections.append(SimpleNamespace(name=self._collection_name))
        return SimpleNamespace(collections=collections)

    def get_collection(self, collection_name: str):
        if self.raise_errors:
            raise RuntimeError("Qdrant unavailable")
        if not self.collection_exists or collection_name != self._collection_name:
            raise RuntimeError("Collection missing")
        return SimpleNamespace(
            vectors_count=128,
            status="green",
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(
                        size=settings.openai_embedding_dimension,
                        distance="COSINE",
                    )
                )
            ),
        )


class _FakeQdrantService:
    """Service stub that records ensure_collection calls."""

    def __init__(self, *, exists: bool, fail_init: bool = False, fail_health: bool = False):
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = settings.openai_embedding_dimension
        self._fail_init = fail_init
        self.client = _FakeQdrantClient(
            collection_name=self.collection_name,
            exists=exists,
            raise_errors=fail_health,
        )
        self.ensure_calls = []

    def ensure_collection(self, write_optimized: bool = False):
        if self._fail_init:
            raise RuntimeError("Initialization failure")
        self.ensure_calls.append(write_optimized)
        self.client.collection_exists = True



def _configured_password() -> str:
    if settings.auth_password:
        return settings.auth_password
    pytest.skip("AUTH_PASSWORD must be configured for admin endpoint tests")


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": settings.auth_username, "password": _configured_password()},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _override_qdrant_service(service: _FakeQdrantService):
    app.dependency_overrides[get_admin_qdrant_service] = lambda: service


def _clear_override():
    app.dependency_overrides.pop(get_admin_qdrant_service, None)


def test_init_qdrant_invokes_service_and_returns_payload(client: TestClient):
    service = _FakeQdrantService(exists=False)
    _override_qdrant_service(service)
    try:
        response = client.post(
            "/api/v1/admin/init-qdrant",
            json={"write_optimized": True},
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["collection"] == settings.qdrant_collection_name
    assert payload["write_optimized"] is True
    assert payload["status"] == "initialized"
    assert service.ensure_calls == [True]


def test_init_qdrant_surfaces_runtime_failures(client: TestClient):
    service = _FakeQdrantService(exists=False, fail_init=True)
    _override_qdrant_service(service)
    try:
        response = client.post(
            "/api/v1/admin/init-qdrant",
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 503
    assert "Initialization failure" in response.json()["detail"]


def test_health_reports_collection_readiness(client: TestClient):
    service = _FakeQdrantService(exists=True)
    _override_qdrant_service(service)
    try:
        response = client.get(
            "/api/v1/admin/health",
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["collection_exists"] is True
    assert payload["actual"]["vector_size"] == settings.openai_embedding_dimension


def test_health_returns_service_unavailable_on_errors(client: TestClient):
    service = _FakeQdrantService(exists=False, fail_health=True)
    _override_qdrant_service(service)
    try:
        response = client.get(
            "/api/v1/admin/health",
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 503
    assert "Qdrant" in response.json()["detail"]
