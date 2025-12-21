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


def test_pedr_search_passes_graph_params(client: TestClient, auth_headers, monkeypatch):
    """Graph parameters are forwarded to the orchestrator."""
    fake = _FakeOrchestrator(graph_enabled=True, graph_candidates=4)
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "create_pedr_orchestrator", lambda: fake)

    payload = {
        "query": "graph query",
        "enable_graph": True,
        "graph_depth": 3,
        "graph_decay": 0.5,
        "graph_edge_types": ["contains", "references"],
        "graph_weight": 0.2,
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


def test_pedr_search_returns_graph_metadata(client: TestClient, auth_headers, monkeypatch):
    """Graph metadata is included in the response when enabled."""
    fake = _FakeOrchestrator(graph_enabled=True, graph_candidates=8)
    import app.api.v1.pedr_search as pedr_search_api

    monkeypatch.setattr(pedr_search_api, "create_pedr_orchestrator", lambda: fake)

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

    monkeypatch.setattr(pedr_search_api, "create_pedr_orchestrator", lambda: fake)

    payload = {"query": "invalid graph", "enable_graph": True, "graph_depth": 6}
    response = client.post("/api/v1/pedr/search", json=payload, headers=auth_headers)

    assert response.status_code == 422
    assert fake.calls == []
