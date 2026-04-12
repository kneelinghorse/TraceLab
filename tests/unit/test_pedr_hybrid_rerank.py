"""Unit tests for PEDR hybrid reranker behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.pedr.hybrid_rerank import HybridReranker

pytestmark = pytest.mark.unit


class _EmbeddingStub:
    def generate_embedding(self, _query: str) -> list[float]:
        return [1.0, 0.0]


class _QdrantClientStub:
    def __init__(self, points: list[SimpleNamespace]) -> None:
        self._points = points

    def retrieve(self, **_kwargs: Any) -> list[SimpleNamespace]:
        return self._points


class _QdrantServiceStub:
    def __init__(self, points: list[SimpleNamespace]) -> None:
        self.collection_name = "chunks"
        self.client = _QdrantClientStub(points)

    def search_chunks(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


def test_semantic_rerank_includes_embeddings_when_requested():
    """Hybrid rerank should attach embeddings when include_embeddings=True."""
    points = [
        SimpleNamespace(id="c1", vector=[1.0, 0.0]),
        SimpleNamespace(id="c2", vector=[0.0, 1.0]),
    ]
    reranker = HybridReranker(
        embedding_service=_EmbeddingStub(),
        qdrant_service=_QdrantServiceStub(points),
    )

    results = reranker._semantic_rerank(
        query_embedding=[1.0, 0.0],
        candidates=[
            {"chunk_id": "c1", "content": "best", "fts_score": 0.8},
            {"chunk_id": "c2", "content": "worse", "fts_score": 0.9},
        ],
        top_k=1,
        include_embeddings=True,
    )

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["embedding"] == [1.0, 0.0]


def test_search_forwards_source_origin_to_filters(monkeypatch):
    """search() should forward source_origin to both FTS and fallback semantic paths."""
    reranker = HybridReranker(
        embedding_service=_EmbeddingStub(),
        qdrant_service=_QdrantServiceStub([]),
    )
    captured: dict[str, Any] = {}

    def _fake_fts_candidates(**kwargs: Any):
        captured["fts_source_origin"] = kwargs.get("source_origin")
        return []

    def _fake_full_semantic_search(**kwargs: Any):
        captured["semantic_source_origin"] = kwargs.get("source_origin")
        return []

    monkeypatch.setattr(reranker, "_fts_candidates", _fake_fts_candidates)
    monkeypatch.setattr(reranker, "_full_semantic_search", _fake_full_semantic_search)

    reranker.search(
        query="source origin",
        mode="hybrid",
        source_origin="synthesized",
        top_k=5,
        candidate_pool=20,
    )

    assert captured["fts_source_origin"] == "synthesized"
    assert captured["semantic_source_origin"] == "synthesized"
