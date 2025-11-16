"""Unit tests for the hybrid search service."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services import hybrid_search as hybrid_module


class _FakeRetrievalService:
    def __init__(self, results: List[Dict[str, Any]] | None = None):
        self.calls: List[Dict[str, Any]] = []
        self._results = results or [
            {
                "chunk_id": "chunk-1",
                "content": "Semantic governance insight.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.81,
                "embedding": [0.1, 0.2, 0.3],
            }
        ]

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [dict(item) for item in self._results]


class _StubFacetedService:
    def apply_sql_filters(self, stmt, _filters):
        return stmt

    def filter_chunks(self, chunks, _filters):
        return list(chunks)


def _keyword_payload(chunk_id: str, score: float) -> Dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "content": f"Keyword result {chunk_id}",
        "document_id": f"doc-{chunk_id}",
        "project_id": f"proj-{chunk_id}",
        "chunk_index": 0,
        "source_type": "report",
        "score": score,
    }


def test_semantic_mode_delegates_to_retriever(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    service = hybrid_module.HybridSearchService(
        retrieval_service=fake_retrieval,
        session_factory=lambda: None,
        faceted_service=_StubFacetedService(),
    )

    results = service.search(query="climate goals", top_k=2, search_mode="semantic", include_embeddings=True)

    assert fake_retrieval.calls[0]["top_k"] == 2
    assert fake_retrieval.calls[0]["include_embeddings"] is True
    assert results[0]["chunk_id"] == "chunk-1"
    assert results[0]["search_mode"] == "semantic"


def test_keyword_mode_normalizes_scores(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    keyword_results = [
        _keyword_payload("chunk-a", 0.9),
        _keyword_payload("chunk-b", 0.3),
    ]
    monkeypatch.setattr(
        hybrid_module.HybridSearchService,
        "_keyword_search",
        lambda self, **kwargs: [dict(item) for item in keyword_results],
    )
    service = hybrid_module.HybridSearchService(
        retrieval_service=fake_retrieval,
        session_factory=lambda: None,
        faceted_service=_StubFacetedService(),
    )

    results = service.search(query="policy priorities", top_k=1, search_mode="keyword")

    assert results[0]["chunk_id"] == "chunk-a"
    assert results[0]["search_mode"] == "keyword"
    assert 0.0 <= results[0]["keyword_score"] <= 1.0


def test_hybrid_mode_merges_weighted_scores(monkeypatch):
    semantic_results = [
        {
            "chunk_id": "chunk-a",
            "content": "Semantic only hit.",
            "document_id": "doc-a",
            "project_id": "proj-a",
            "chunk_index": 0,
            "source_type": "report",
            "score": 0.1,
            "embedding": [0.1, 0.1, 0.1],
        },
        {
            "chunk_id": "chunk-b",
            "content": "Appears in both lists.",
            "document_id": "doc-b",
            "project_id": "proj-b",
            "chunk_index": 1,
            "source_type": "report",
            "score": 0.9,
            "embedding": [0.9, 0.1, 0.1],
        },
    ]
    fake_retrieval = _FakeRetrievalService(results=semantic_results)
    keyword_results = [
        _keyword_payload("chunk-b", 0.6),
        _keyword_payload("chunk-c", 0.2),
    ]
    monkeypatch.setattr(
        hybrid_module.HybridSearchService,
        "_keyword_search",
        lambda self, **kwargs: [dict(item) for item in keyword_results],
    )
    service = hybrid_module.HybridSearchService(
        retrieval_service=fake_retrieval,
        session_factory=lambda: None,
        faceted_service=_StubFacetedService(),
    )

    results = service.search(query="hybrid scoring", top_k=2, search_mode="hybrid")

    assert results[0]["chunk_id"] == "chunk-b"
    assert results[0]["search_mode"] == "hybrid"
    assert results[1]["chunk_id"] in {"chunk-a", "chunk-c"}
    assert results[0]["score"] >= results[1]["score"]


def test_invalid_mode_raises_value_error():
    fake_retrieval = _FakeRetrievalService()
    service = hybrid_module.HybridSearchService(
        retrieval_service=fake_retrieval,
        session_factory=lambda: None,
        faceted_service=_StubFacetedService(),
    )

    with pytest.raises(ValueError):
        service.search(query="unsupported", search_mode="vector")
