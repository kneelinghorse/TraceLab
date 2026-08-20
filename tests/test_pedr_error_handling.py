"""Unit tests for PEDR search orchestrator graceful degradation.

Retrieval outages must not discard usable results from healthy layers or make
search unavailable. Metadata identifies only layers that actually contributed,
so callers can accurately assess the provenance of a partial response.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.pedr.cache import get_pedr_cache
from app.services.pedr.search_orchestrator import (
    PEDRConfig,
    PEDRSearchOrchestrator,
    PEDRSearchResponse,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pedr_cache():
    """Clear the PEDR cache before each test to avoid cross-test pollution."""
    cache = get_pedr_cache()
    cache.invalidate_all()
    yield
    cache.invalidate_all()


SAMPLE_RESULTS = [
    {
        "chunk_id": f"chunk-{i}",
        "content": f"Sample content {i}",
        "score": 0.9 - i * 0.1,
    }
    for i in range(5)
]


def _make_orchestrator(
    *,
    lexical_fn=None,
    semantic_fn=None,
    config: PEDRConfig | None = None,
) -> PEDRSearchOrchestrator:
    """Create a test orchestrator with injectable search functions."""
    return PEDRSearchOrchestrator(
        config=config or PEDRConfig(enable_graph=False),
        lexical_search=lexical_fn,
        semantic_search=semantic_fn,
        telemetry_enabled=False,
    )


def _ok_search(**kwargs: Any) -> list[dict[str, Any]]:
    return list(SAMPLE_RESULTS)


def _failing_search(**kwargs: Any) -> list[dict[str, Any]]:
    raise ConnectionError("Database connection lost")


def _timeout_search(**kwargs: Any) -> list[dict[str, Any]]:
    raise TimeoutError("Search timed out after 30s")


class TestGracefulDegradation:
    """Keep search useful when an independent retrieval layer is unavailable."""

    def test_lexical_failure_preserves_semantic_results(self):
        orchestrator = _make_orchestrator(
            lexical_fn=_failing_search,
            semantic_fn=_ok_search,
        )

        response = orchestrator.search(query="test query", top_k=5)

        assert isinstance(response, PEDRSearchResponse)
        assert response.results
        assert response.metadata.layers_used == ["semantic"]
        assert all(
            result.contributing_layers == ["semantic"]
            for result in response.results
        )

    def test_semantic_failure_preserves_lexical_results(self):
        orchestrator = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_timeout_search,
        )

        response = orchestrator.search(query="test query", top_k=5)

        assert response.results
        assert response.metadata.layers_used == ["lexical"]
        assert all(
            result.contributing_layers == ["lexical"] for result in response.results
        )

    def test_both_retrieval_failures_return_empty_response(self):
        orchestrator = _make_orchestrator(
            lexical_fn=_failing_search,
            semantic_fn=_timeout_search,
        )

        response = orchestrator.search(query="test query", top_k=5)

        assert response.results == []
        assert response.metadata.layers_used == []
        assert response.metadata.total_candidates == 0
        assert response.metadata.result_count == 0

    def test_graph_failure_preserves_retrieval_results(self):
        orchestrator = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
            config=PEDRConfig(enable_graph=True),
        )
        orchestrator.graph_service = MagicMock()
        orchestrator.graph_service.expand_from_results.side_effect = RuntimeError(
            "Graph DB unavailable"
        )

        response = orchestrator.search(query="test query", top_k=5)

        orchestrator.graph_service.expand_from_results.assert_called_once()
        assert response.results
        assert response.metadata.layers_used == ["lexical", "semantic"]
        assert "graph" not in {
            layer
            for result in response.results
            for layer in result.contributing_layers
        }
