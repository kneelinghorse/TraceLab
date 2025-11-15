"""Tests for Qdrant admin endpoints."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import qdrant_admin as qdrant_admin_router
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
            payload_schema={
                "project_id": {"data_type": "keyword"},
                "document_id": {"data_type": "keyword"},
                "source_type": {"data_type": "keyword"},
            },
        )


class _FakeQdrantService:
    """Service stub that records ensure_collection calls."""

    def __init__(
        self,
        *,
        exists: bool,
        fail_init: bool = False,
        fail_health: bool = False,
        quantized: bool = True,
    ):
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = settings.openai_embedding_dimension
        self._fail_init = fail_init
        self._quantized = quantized
        self.client = _FakeQdrantClient(
            collection_name=self.collection_name,
            exists=exists,
            raise_errors=fail_health,
        )
        self.ensure_calls = []
        self.hnsw_updates = []

    def ensure_collection(self, write_optimized: bool = False):
        if self._fail_init:
            raise RuntimeError("Initialization failure")
        self.ensure_calls.append(write_optimized)
        self.client.collection_exists = True

    def get_collection_diagnostics(self) -> dict:
        return {
            "collection": self.collection_name,
            "collection_exists": self.client.collection_exists,
            "points_count": 500_000,
            "vectors_count": 500_000,
            "payload_indexes": [
                {"field": "project_id", "present": True},
                {"field": "document_id", "present": True},
                {"field": "source_type", "present": True},
            ],
            "hnsw": {
                "m": 16,
                "ef_construct": 100,
                "full_scan_threshold": 20_000,
                "on_disk": False,
            },
            "quantization": {
                "enabled": self._quantized,
                "type": "ScalarType.INT8",
                "always_ram": True,
                "quantile": 0.99,
            },
            "optimizer": {"indexing_threshold": 20_000},
            "vector_size": self.vector_size,
            "memory_estimate_bytes": 500_000 * self.vector_size,
            "memory_estimate_gb": 0.75,
            "error": None,
        }

    def apply_hnsw_settings(self, **kwargs):
        self.hnsw_updates.append(kwargs)



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
    app.dependency_overrides[qdrant_admin_router.get_qdrant_admin_service] = lambda: service


def _clear_override():
    app.dependency_overrides.pop(get_admin_qdrant_service, None)
    app.dependency_overrides.pop(qdrant_admin_router.get_qdrant_admin_service, None)


def _seed_benchmark(monkeypatch, tmp_path):
    bench_file = tmp_path / "benchmark.json"
    bench_file.write_text(
        json.dumps(
            {
                "generated_at": "2025-11-15T15:45:00Z",
                "target_latency_ms": 10.0,
                "recall_threshold": 0.99,
                "trials": 12,
                "top_k": 10,
                "ef_values": [64, 96, 128],
                "recommendation": {"hnsw_ef": 96, "p99_latency_ms": 9.1, "recall": 0.992},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(qdrant_admin_router, "_BENCHMARK_PATH", bench_file)


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
    assert payload["payload_indexes"] == [
        {"field": "project_id", "present": True},
        {"field": "document_id", "present": True},
        {"field": "source_type", "present": True},
    ]


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


def test_qdrant_stats_endpoint_returns_memory_profile(client: TestClient):
    service = _FakeQdrantService(exists=True)
    _override_qdrant_service(service)
    try:
        response = client.get(
            "/api/v1/qdrant-admin/stats",
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["collection_exists"] is True
    assert payload["memory"]["estimate_gb"] == pytest.approx(0.75)
    assert payload["quantization"]["enabled"] is True


def test_qdrant_health_reports_degraded_when_quantization_missing(client: TestClient, monkeypatch, tmp_path):
    service = _FakeQdrantService(exists=True, quantized=False)
    _seed_benchmark(monkeypatch, tmp_path)
    _override_qdrant_service(service)
    try:
        response = client.get(
            "/api/v1/qdrant-admin/health",
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["benchmark"]["recommendation"]["hnsw_ef"] == 96


def test_qdrant_config_endpoint_applies_settings(client: TestClient):
    service = _FakeQdrantService(exists=True)
    _override_qdrant_service(service)
    try:
        response = client.post(
            "/api/v1/qdrant-admin/config/hnsw",
            json={
                "m": 32,
                "ef_construct": 128,
                "full_scan_threshold": 40_000,
                "on_disk": True,
                "optimizer_threshold": 50_000,
                "enable_quantization": True,
                "quantile": 0.98,
                "always_ram": False,
            },
            headers=_auth_headers(client),
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
    assert service.hnsw_updates[0]["m"] == 32
    assert service.hnsw_updates[0]["on_disk"] is True
