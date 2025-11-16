"""Tests covering the saved searches API + execution flow."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.api.v1 import saved_searches as saved_router
from app.main import app
from app.services import saved_search as saved_service_module
from app.services.saved_search import SavedSearchService


class _StubRagService:
    """Minimal fake RAG service returning deterministic payloads."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def run_query(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "answer": "Saved search results summarized.",
            "citations": [],
            "sources": [
                {
                    "chunk_id": "chunk-001",
                    "content": "Chunk content excerpt.",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.91,
                }
            ],
            "latency_ms": 33.5,
            "compression": {
                "original_chunks": 5,
                "filtered_chunks": 2,
                "original_tokens": 1400,
                "filtered_tokens": 500,
                "reduction_ratio": 0.64,
                "threshold": 0.7,
                "compression_ms": 4.5,
            },
            "cache": {"hit": False, "score": None, "age_seconds": None, "ttl_seconds": None},
            "quality": {
                "composite_score": 0.9,
                "threshold": 0.85,
                "pillar_scores": {
                    "linguistic_uncertainty": 0.92,
                    "answer_integrity": 0.88,
                    "source_provenance": 0.89,
                },
                "hard_failures": [],
                "reasons": [],
                "pre_escalation_score": None,
            },
            "routing": {
                "selected_model": "gpt-test",
                "escalated": False,
                "attempts": [
                    {
                        "model": "gpt-test",
                        "quality_score": 0.9,
                        "below_threshold": False,
                        "hard_failures": [],
                        "citation_count": 1,
                    }
                ],
                "estimated_cost_usd": 0.0002,
                "metrics": {"total_queries": 1, "escalations": 0},
            },
            "search_mode": kwargs.get("search_mode", "semantic"),
        }


class _StubRetrievalService:
    """Return deterministic semantic search results."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def search(self, **kwargs: Any) -> List[Dict[str, Any]]:
        self.calls.append(kwargs)
        return [
            {
                "chunk_id": "chunk-001",
                "content": "Chunk content excerpt.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.91,
            }
        ]


def test_saved_search_crud_flow(auth_headers):
    """Create, list, update, and delete saved searches through the API."""
    client = TestClient(app)

    create_resp = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Daily briefing",
            "description": "Monitor checkout errors",
            "query_text": "Checkout errors",
            "search_mode": "hybrid",
            "filters": {"project_id": "proj-1"},
            "top_k": 6,
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Daily briefing"
    assert created["use_count"] == 0

    list_resp = client.get("/api/v1/saved-searches", headers=auth_headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["items"][0]["id"] == created["id"]
    assert payload["limit_per_user"] == 50

    update_resp = client.put(
        f"/api/v1/saved-searches/{created['id']}",
        json={"name": "Checkout fallout", "top_k": 10},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Checkout fallout"
    assert updated["top_k"] == 10

    delete_resp = client.delete(f"/api/v1/saved-searches/{created['id']}", headers=auth_headers)
    assert delete_resp.status_code == 204

    after_delete = client.get("/api/v1/saved-searches", headers=auth_headers).json()
    assert after_delete["items"] == []


def test_execute_saved_search_runs_services(monkeypatch, auth_headers):
    """Executing a saved search calls rag + retrieval services and tracks usage."""
    client = TestClient(app)
    create = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Replay saved search",
            "description": "Quick access",
            "query_text": "Policy updates",
            "search_mode": "semantic",
            "filters": {"project_id": "proj-2", "source_type": "report"},
            "top_k": 4,
        },
        headers=auth_headers,
    )
    saved_id = create.json()["id"]

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(saved_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(saved_router, "get_retrieval_service", lambda: fake_retrieval)

    execute = client.post(f"/api/v1/saved-searches/{saved_id}/execute", headers=auth_headers)
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["saved_search"]["id"] == saved_id
    assert payload["saved_search"]["use_count"] == 1
    assert payload["rag"]["answer"] == "Saved search results summarized."
    assert payload["semantic"]["results"][0]["chunk_id"] == "chunk-001"

    list_after = client.get("/api/v1/saved-searches", headers=auth_headers).json()
    assert list_after["items"][0]["use_count"] == 1
    assert fake_rag.calls and fake_retrieval.calls


def test_saved_search_limit_enforced(monkeypatch, auth_headers):
    """Creating more than the configured limit returns HTTP 400."""
    limited_service = SavedSearchService(max_saved_per_user=1)
    monkeypatch.setattr(saved_service_module, "_saved_search_service", limited_service)
    monkeypatch.setattr(saved_router, "get_saved_search_service", lambda: limited_service)

    client = TestClient(app)
    first = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "First saved search",
            "query_text": "Query 1",
            "search_mode": "semantic",
            "filters": {},
            "top_k": 5,
        },
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Second saved search",
            "query_text": "Query 2",
            "search_mode": "semantic",
            "filters": {},
            "top_k": 5,
        },
        headers=auth_headers,
    )
    assert second.status_code == 400
    assert "limit" in second.text.lower()
