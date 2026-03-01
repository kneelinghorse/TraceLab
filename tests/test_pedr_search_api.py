"""API tests for PEDR search graph parameters."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.pedr.search_orchestrator import (
    LayerTimings,
    PEDRMetadata,
    PEDRSearchResponse,
    PEDRSearchResult,
)


@pytest.fixture
def client() -> TestClient:
    """Provide a FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


class _FakeOrchestrator:
    def __init__(self, *, graph_enabled: bool = False, graph_candidates: int | None = None) -> None:
        self.calls: list[dict] = []
        self._graph_enabled = graph_enabled
        self._graph_candidates = graph_candidates

    def search(self, **kwargs) -> PEDRSearchResponse:
        self.calls.append(kwargs)
        results = [
            PEDRSearchResult(
                chunk_id="chunk-1",
                content="Graph response sample",
                rrf_score=0.42,
                rrf_rank=1,
            )
        ]
        metadata = PEDRMetadata(
            query=kwargs.get("query", ""),
            intent="search",
            intent_confidence=0.9,
            detected_type=None,
            type_confidence=0.0,
            layers_used=["lexical", "semantic"],
            layer_weights={"lexical": 0.25, "semantic": 0.35},
            timings=LayerTimings(graph_ms=12.5, total_ms=15.0),
            graph_enabled=self._graph_enabled,
            graph_candidates_expanded=self._graph_candidates,
            total_candidates=len(results),
            result_count=len(results),
            cache_hit=False,
        )
        return PEDRSearchResponse(results=results, metadata=metadata)


class _FailingOrchestrator:
    def search(self, **_kwargs):  # pragma: no cover - validated through endpoint response
        raise RuntimeError("internal stack trace details")


class _FakeHybridReranker:
    def search(self, **_kwargs):
        from app.services.pedr.hybrid_rerank import HybridRerankResult, HybridRerankTimings

        return HybridRerankResult(
            results=[
                {
                    "chunk_id": "chunk-1",
                    "content": "kept by governance",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "semantic_score": 0.91,
                    "score": 0.91,
                    "combined_score": 0.91,
                    "source_type": "report",
                    "source_origin": "upload",
                },
                {
                    "chunk_id": "chunk-2",
                    "content": "filtered by governance",
                    "document_id": "doc-2",
                    "project_id": "proj-1",
                    "semantic_score": 0.89,
                    "score": 0.89,
                    "combined_score": 0.89,
                    "source_type": "report",
                    "source_origin": "synthesized",
                },
            ],
            timings=HybridRerankTimings(fts_ms=5.0, embedding_ms=2.0, rerank_ms=3.0, total_ms=10.0),
            mode_used="hybrid",
            fts_candidates_count=2,
            fallback_used=False,
        )


class _GovernanceFilter:
    def apply(self, results, *, filters=None):
        kept = [dict(results[0])]
        kept[0]["quality_score"] = 1.0
        kept[0]["quality_status"] = "review"
        kept[0]["quality_gates_passed"] = 4
        return kept


def test_pedr_search_passes_graph_params(client: TestClient, auth_headers, monkeypatch):
    """Graph parameters are forwarded to the orchestrator."""
    fake = _FakeOrchestrator(graph_enabled=True, graph_candidates=4)
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)

    payload = {
        "query": "graph query",
        "enable_graph": True,
        "graph_depth": 3,
        "graph_decay": 0.5,
        "graph_edge_types": ["contains", "references"],
        "graph_weight": 0.2,
        "source_origin": "synthesized",
        "include_embeddings": True,
    }
    response = client.post("/api/v1/pedr/search", json=payload, headers=auth_headers)

    assert response.status_code == 200
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["enable_graph"] is True
    assert call["graph_depth"] == 3
    assert call["graph_decay"] == 0.5
    assert call["graph_edge_types"] == ["contains", "references"]
    assert call["graph_weight"] == 0.2
    assert call["source_origin"] == "synthesized"
    assert call["include_embeddings"] is True


def test_pedr_search_returns_graph_metadata(client: TestClient, auth_headers, monkeypatch):
    """Graph metadata is included in the response when enabled."""
    fake = _FakeOrchestrator(graph_enabled=True, graph_candidates=8)
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)

    payload = {"query": "graph metadata", "enable_graph": True}
    response = client.post("/api/v1/pedr/search", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    metadata = data["metadata"]
    assert metadata["graph_enabled"] is True
    assert metadata["graph_candidates_expanded"] == 8
    assert metadata["timings"]["graph_ms"] == pytest.approx(12.5, rel=1e-3)


def test_pedr_search_rejects_invalid_graph_params(client: TestClient, auth_headers, monkeypatch):
    """Graph parameter validation rejects out-of-range values."""
    fake = _FakeOrchestrator(graph_enabled=True, graph_candidates=0)
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)

    payload = {"query": "invalid graph", "enable_graph": True, "graph_depth": 6}
    response = client.post("/api/v1/pedr/search", json=payload, headers=auth_headers)

    assert response.status_code == 422
    assert fake.calls == []


def test_pedr_search_uses_to_thread_for_full_mode(client: TestClient, auth_headers, monkeypatch):
    """Endpoint delegates sync orchestrator work through asyncio.to_thread."""
    fake = _FakeOrchestrator(graph_enabled=False, graph_candidates=None)
    import app.api.v1.pedr_search as pedr_search_api

    called = {"to_thread": 0}

    async def _fake_to_thread(func, *args, **kwargs):
        called["to_thread"] += 1
        return func(*args, **kwargs)

    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)
    monkeypatch.setattr(pedr_search_api.asyncio, "to_thread", _fake_to_thread)

    response = client.post("/api/v1/pedr/search", json={"query": "threaded search"}, headers=auth_headers)

    assert response.status_code == 200
    assert called["to_thread"] >= 1


def test_pedr_search_sanitizes_internal_errors(client: TestClient, auth_headers, monkeypatch):
    """500 responses should not leak internal exception details."""
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: _FailingOrchestrator())

    response = client.post("/api/v1/pedr/search", json={"query": "boom"}, headers=auth_headers)
    assert response.status_code == 500
    assert response.json()["detail"] == pedr_search_api.INTERNAL_ERROR_DETAIL
    assert "stack trace" not in response.json()["detail"]


def test_hybrid_search_applies_governance_post_processing(client: TestClient, auth_headers, monkeypatch):
    """Hybrid mode runs governance filters as post-processing."""
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "get_hybrid_reranker", lambda: _FakeHybridReranker())
    monkeypatch.setattr(pedr_search_api, "get_quality_scoring_service", lambda: _GovernanceFilter())

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(pedr_search_api.asyncio, "to_thread", _fake_to_thread)

    payload = {
        "query": "hybrid governance",
        "rerank_mode": "hybrid",
        "candidate_pool": 20,
        "top_k": 5,
        "enable_governance": True,
    }
    response = client.post("/api/v1/pedr/search", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["quality_status"] == "review"
    assert data["results"][0]["source_origin"] == "upload"
    assert "governance" in data["metadata"]["layers_used"]
