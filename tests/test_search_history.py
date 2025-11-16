"""Tests for search history logging, listing, and replay APIs."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.api.v1 import search as search_router
from app.api.v1 import search_history as history_router
from app.main import app
from app.services.search_history import SearchHistoryService


class _StubRagService:
    """Minimal fake RAG service returning deterministic payloads."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def run_query(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "answer": "Search results summarized.",
            "citations": [
                {
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.94,
                    "snippet": "Chunk content excerpt.",
                }
            ],
            "sources": [
                {
                    "chunk_id": "chunk-1",
                    "content": "Chunk content excerpt.",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.94,
                }
            ],
            "latency_ms": 42.0,
            "compression": {
                "original_chunks": 3,
                "filtered_chunks": 1,
                "original_tokens": 1200,
                "filtered_tokens": 400,
                "reduction_ratio": 0.666,
                "threshold": 0.7,
                "compression_ms": 5.2,
            },
            "cache": {"hit": False, "score": None, "age_seconds": None, "ttl_seconds": None},
            "quality": {
                "composite_score": 0.92,
                "threshold": 0.85,
                "pillar_scores": {
                    "linguistic_uncertainty": 0.93,
                    "answer_integrity": 0.91,
                    "source_provenance": 0.9,
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
                        "quality_score": 0.92,
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
                "chunk_id": "chunk-1",
                "content": "Chunk content excerpt.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.94,
            }
        ]


def test_search_history_logged_and_listed(monkeypatch, auth_headers):
    """Posting to /search logs a row retrievable via the history endpoint."""
    fake_service = _StubRagService()
    monkeypatch.setattr(search_router, "get_rag_service", lambda: fake_service)

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"query": "What is the policy?", "top_k": 3, "search_mode": "hybrid"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    history_response = client.get("/api/v1/search/history?limit=5", headers=auth_headers)
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["entries"], "Expected at least one history entry."
    first = payload["entries"][0]
    assert first["query_text"] == "What is the policy?"
    assert first["search_mode"] == "hybrid"
    assert first["top_k"] == 3
    assert first["result_count"] == 1


def test_replay_endpoint_runs_query_and_logs(monkeypatch, auth_headers):
    """Replay endpoint re-executes the query and records a new history row."""
    service = SearchHistoryService()
    entry = service.record_search(
        query="Replay me",
        search_mode="semantic",
        filters={"project_id": "proj-1", "source_type": "report"},
        top_k=4,
        result_count=1,
        duration_ms=25.0,
        cache_hit=False,
        executed_by="tester",
        top_chunks=["chunk-legacy"],
    )

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(history_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(history_router, "get_retrieval_service", lambda: fake_retrieval)

    client = TestClient(app)
    replay = client.post(f"/api/v1/search/replay/{entry.id}", headers=auth_headers)
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["entry"]["id"] == str(entry.id)
    assert payload["rag"]["answer"] == "Search results summarized."
    assert payload["semantic"]["results"][0]["chunk_id"] == "chunk-1"

    history = client.get("/api/v1/search/history", headers=auth_headers).json()["entries"]
    assert len(history) >= 2, "Expected replay to insert a new entry."


def test_clear_history_endpoint(auth_headers):
    """Deleting history empties the table and returns deleted count."""
    service = SearchHistoryService()
    service.record_search(
        query="First query",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=10,
        cache_hit=False,
        executed_by="tester",
        top_chunks=[],
    )
    service.record_search(
        query="Second query",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=10,
        cache_hit=False,
        executed_by="tester",
        top_chunks=[],
    )

    client = TestClient(app)
    delete_resp = client.delete("/api/v1/search/history", headers=auth_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] >= 2

    history = client.get("/api/v1/search/history", headers=auth_headers).json()
    assert history["entries"] == []
