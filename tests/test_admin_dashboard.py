"""Tests for the admin dashboard metrics endpoints and aggregator."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import admin as admin_router
from app.core.config import settings
from app.core.database import engine
from app.main import app
from app.services.metrics_aggregator import MetricsAggregator, get_metrics_aggregator


class _FakeCostMonitor:
    def summary(self) -> dict:
        return {
            "currency": "USD",
            "retention_days": 30,
            "totals": {
                "queries": 4,
                "cost_usd": 1.2,
                "cache_hit_rate": 0.25,
            },
        }


class _FakeCacheManager:
    def snapshot(self) -> dict:
        return {
            "rag_query_results": {
                "name": "rag_query_results",
                "ttl_seconds": 300,
                "maxsize": 128,
                "size": 4,
                "hits": 10,
                "misses": 3,
                "sets": 6,
                "invalidations": 1,
                "hit_rate": 0.76,
                "last_event_ts": None,
            },
            "project_metadata": {
                "name": "project_metadata",
                "ttl_seconds": 300,
                "maxsize": 256,
                "size": 2,
                "hits": 5,
                "misses": 1,
                "sets": 2,
                "invalidations": 0,
                "hit_rate": 0.83,
                "last_event_ts": None,
            },
        }


class _FakeSemanticMetrics:
    def snapshot(self) -> dict:
        return {
            "hit_rate": 0.91,
            "hits": 42,
            "misses": 4,
            "evictions": 1,
            "avg_lookup_seconds": 0.12,
        }


class _FakeQdrantClient:
    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name="research_chunks")])

    def get_collection(self, name: str):
        return SimpleNamespace(vectors_count=128, payload_schema={"project_id": {}, "document_id": {}, "source_type": {}})


class _FakeQdrantService:
    def __init__(self) -> None:
        self.collection_name = "research_chunks"
        self.vector_size = 3072
        self.client = _FakeQdrantClient()


def _write_events(path: Path) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        {
            "ts": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": "gpt-5.2",
            "route": "primary",
            "cost_usd": 0.4,
            "latency_ms": 3200,
            "cache_hit": False,
            "project_id": "demo",
        },
        {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": "text-embedding-3-large",
            "route": "embedding",
            "cost_usd": 0.05,
            "latency_ms": 600,
            "cache_hit": True,
            "project_id": "demo",
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_metrics_aggregator_generates_sections(tmp_path):
    telemetry_path = tmp_path / "telemetry.jsonl"
    _write_events(telemetry_path)
    aggregator = MetricsAggregator(
        telemetry_path=telemetry_path,
        cost_monitor=_FakeCostMonitor(),
        cache_manager=_FakeCacheManager(),
        semantic_cache_metrics=_FakeSemanticMetrics(),
        engine=engine,
        qdrant_service_factory=_FakeQdrantService,
        max_events=50,
    )

    payload = aggregator.collect()

    assert payload["cost_overview"]["periods"]["today"] == pytest.approx(0.45)
    assert payload["cache_performance"]["aggregate"]["ttl_cache_count"] == 2
    assert payload["query_performance"]["p50_latency_ms"] > 0
    assert payload["system_health"]["qdrant"]["status"] in {"healthy", "collection_missing"}
    assert payload["export_rows"]


class _StubAggregator:
    def __init__(self) -> None:
        self.payload = {
            "generated_at": "2025-11-15T12:00:00Z",
            "cost_overview": {
                "currency": "USD",
                "periods": {"today": 1.0, "week": 5.0, "month": 15.0},
                "average_cost_per_query": 0.5,
                "embedding_cost_usd": 0.2,
                "generation_cost_usd": 0.8,
                "daily_trend": [],
                "recent_events": [],
            },
            "cache_performance": {
                "semantic_cache": {"hit_rate": 0.5},
                "aggregate": {"ttl_average_hit_rate": 0.5, "ttl_cache_count": 1},
                "ttl_caches": [],
            },
            "query_performance": {
                "p50_latency_ms": 120.0,
                "p95_latency_ms": 180.0,
                "p99_latency_ms": 200.0,
                "requests_last_hour": 3,
                "slow_queries": [],
                "trend": [],
            },
            "system_health": {
                "database": {"status": "healthy", "tables": 1, "indexes": 0},
                "qdrant": {"status": "healthy", "vectors_count": 10},
                "telemetry": {"events_available": 2, "last_event": "2025-11-15T12:00:00Z"},
                "cache": {"semantic_cache_hit_rate": 0.5, "ttl_cache_count": 1},
            },
            "export_rows": [
                {"category": "costs", "metric": "today_cost_usd", "value": 1.0, "unit": "USD", "notes": None}
            ],
        }

    def collect(self) -> dict:
        return self.payload


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def override_dashboard():
    stub = _StubAggregator()
    app.dependency_overrides[admin_router.get_dashboard_aggregator] = lambda: stub
    app.dependency_overrides[get_metrics_aggregator] = lambda: stub
    yield stub
    app.dependency_overrides.pop(admin_router.get_dashboard_aggregator, None)
    app.dependency_overrides.pop(get_metrics_aggregator, None)


def _auth_headers(client: TestClient) -> dict:
    from tests.conftest import get_seed_user_email
    response = client.post(
        "/api/v1/auth/login",
        json={"email": get_seed_user_email(), "password": settings.auth_password or "changeme"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_data_endpoint_returns_stub_payload(client: TestClient, override_dashboard):
    headers = _auth_headers(client)
    response = client.get("/api/v1/admin/dashboard/data", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["cost_overview"]["periods"]["today"] == 1.0


def test_dashboard_export_csv(client: TestClient, override_dashboard):
    headers = _auth_headers(client)
    response = client.get("/api/v1/admin/dashboard/export?format=csv", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "today_cost_usd" in response.text


def test_html_dashboard_route_renders_template(client: TestClient, override_dashboard):
    headers = _auth_headers(client)
    response = client.get("/admin/dashboard", headers=headers)
    assert response.status_code == 200
    assert "Cost Monitoring Dashboard" in response.text
