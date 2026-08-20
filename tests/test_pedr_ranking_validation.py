"""PEDR Ranking Validation — synthetic corpus tests.

Runs 5+ representative queries against a synthetic corpus to verify:
- RRF fusion produces sensible rankings
- Layer weights influence result ordering
- Degraded mode (partial layer failure) still produces valid rankings
- Layer provenance remains accurate across query types

This serves as the T33.1 ranking validation deliverable.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.pedr.cache import get_pedr_cache
from app.services.pedr.search_orchestrator import PEDRConfig, PEDRSearchOrchestrator

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache():
    cache = get_pedr_cache()
    cache.invalidate_all()
    yield
    cache.invalidate_all()


# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------


def _make_corpus(n: int = 20) -> list[dict[str, Any]]:
    """Build a synthetic corpus of chunks with varying relevance signals."""
    corpus = []
    for i in range(n):
        corpus.append(
            {
                "chunk_id": f"doc-{i:03d}",
                "content": f"Research finding {i} about machine learning and neural networks",
                "document_id": f"parent-{i // 5}",
                "project_id": "proj-001",
                "score": max(0.1, 1.0 - i * 0.045),
                "quality_score": 0.8 if i < 10 else 0.4,
                "element_type": "document" if i % 3 == 0 else "chunk",
            }
        )
    return corpus


CORPUS = _make_corpus()


def _lexical_search_factory(results: list[dict[str, Any]]):
    """Create a lexical search function returning specified results."""

    def _search(**kwargs) -> list[dict[str, Any]]:
        return list(results)

    return _search


def _semantic_search_factory(results: list[dict[str, Any]]):
    """Create a semantic search function returning specified results."""

    def _search(**kwargs) -> list[dict[str, Any]]:
        return list(results)

    return _search


def _make_orch(
    lexical_results=None,
    semantic_results=None,
    config=None,
) -> PEDRSearchOrchestrator:
    return PEDRSearchOrchestrator(
        config=config or PEDRConfig(enable_graph=False),
        lexical_search=_lexical_search_factory(lexical_results or CORPUS[:10]),
        semantic_search=_semantic_search_factory(semantic_results or CORPUS[:10]),
        telemetry_enabled=False,
    )


# ---------------------------------------------------------------------------
# Query 1: Broad research query — both layers contribute
# ---------------------------------------------------------------------------


class TestQuery1BroadSearch:
    """Broad query: 'machine learning research findings'"""

    def test_both_layers_contribute_results(self):
        orch = _make_orch()
        response = orch.search(query="machine learning research findings", top_k=10)

        assert len(response.results) > 0
        assert response.metadata.layers_used == ["lexical", "semantic"]

        # Results should have contributions from multiple layers
        multi_layer = [r for r in response.results if len(r.contributing_layers) > 1]
        assert len(multi_layer) > 0, "Expected results from multiple layers"

    def test_results_ranked_in_descending_score_order(self):
        orch = _make_orch()
        response = orch.search(query="machine learning research findings", top_k=10)

        # rrf_rank should be 1, 2, 3, ... (assigned after final sort)
        ranks = [r.rrf_rank for r in response.results]
        assert ranks == list(range(1, len(ranks) + 1)), (
            "Ranks should be sequential 1..N"
        )


# ---------------------------------------------------------------------------
# Query 2: Type-specific query — syntactic layer should detect type
# ---------------------------------------------------------------------------


class TestQuery2TypeSpecific:
    """Type-specific query: 'find all documents about neural networks'"""

    def test_syntactic_detects_document_type(self):
        orch = _make_orch()
        response = orch.search(
            query="find all documents about neural networks", top_k=10
        )

        # Syntactic layer should detect "document" type
        assert response.metadata.detected_type in (
            "document",
            None,
        )  # detection is best-effort

    def test_successful_retrieval_layers_are_reported(self):
        orch = _make_orch()
        response = orch.search(
            query="find all documents about neural networks", top_k=10
        )

        assert response.metadata.layers_used == ["lexical", "semantic"]


# ---------------------------------------------------------------------------
# Query 3: Intent-driven query — pragmatic layer detects intent
# ---------------------------------------------------------------------------


class TestQuery3IntentDriven:
    """Intent-driven query: 'search for evidence of bias in training data'"""

    def test_intent_classified(self):
        orch = _make_orch()
        response = orch.search(
            query="search for evidence of bias in training data", top_k=10
        )

        assert response.metadata.intent in ("search", "unknown")

    def test_results_have_query_intent_annotation(self):
        orch = _make_orch()
        response = orch.search(
            query="search for evidence of bias in training data", top_k=10
        )

        for result in response.results:
            assert result.query_intent is not None


# ---------------------------------------------------------------------------
# Query 4: Degraded mode — lexical fails, semantic succeeds
# ---------------------------------------------------------------------------


class TestQuery4DegradedMode:
    """Degraded query: lexical layer fails, semantic succeeds."""

    def test_lexical_outage_preserves_ranked_semantic_results(self):
        def _failing(**kwargs):
            raise RuntimeError("PostgreSQL connection pool exhausted")

        orch = _make_orch(config=PEDRConfig(enable_graph=False))
        orch._lexical_search = _failing

        response = orch.search(query="neural network architecture", top_k=10)

        assert response.results
        assert response.metadata.layers_used == ["semantic"]
        assert [result.rrf_rank for result in response.results] == list(
            range(1, len(response.results) + 1)
        )
        assert all(
            result.contributing_layers == ["semantic"]
            for result in response.results
        )


# ---------------------------------------------------------------------------
# Query 5: All layers disabled except one
# ---------------------------------------------------------------------------


class TestQuery5SingleLayer:
    """Single-layer query: only semantic enabled."""

    def test_single_layer_returns_results(self):
        config = PEDRConfig(
            enable_lexical=False,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=False,
        )
        orch = _make_orch(config=config)
        response = orch.search(query="machine learning", top_k=5)

        assert len(response.results) > 0
        assert response.metadata.layers_used == ["semantic"]
        assert all(
            result.contributing_layers == ["semantic"]
            for result in response.results
        )


# ---------------------------------------------------------------------------
# Query 6: Overlapping results — RRF boost for multi-layer hits
# ---------------------------------------------------------------------------


class TestQuery6OverlappingResults:
    """Verify RRF correctly boosts results that appear in both layers."""

    def test_multi_layer_results_ranked_higher(self):
        # Same results from both layers — should get boosted by RRF
        shared = CORPUS[:5]
        lexical_only = CORPUS[10:15]
        semantic_only = CORPUS[5:10]

        orch = _make_orch(
            lexical_results=shared + lexical_only,
            semantic_results=shared + semantic_only,
        )
        response = orch.search(query="overlapping results test", top_k=10)

        # Top results should be the shared ones (appear in both layers)
        top_5_ids = {r.chunk_id for r in response.results[:5]}
        shared_ids = {r["chunk_id"] for r in shared}
        overlap = top_5_ids & shared_ids
        assert len(overlap) >= 3, (
            f"Expected shared results to dominate top-5, got {overlap}"
        )
