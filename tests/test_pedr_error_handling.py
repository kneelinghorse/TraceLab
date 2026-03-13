"""Unit tests for PEDR search orchestrator error handling.

Validates:
- Per-layer exception types in the exception hierarchy
- Graceful degradation when individual layers fail
- Structured diagnostics in search response metadata
- Layer failure isolation (other layers still return results)
- Disabled/skipped layer diagnostic reporting
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional

from app.services.pedr.cache import get_pedr_cache
from app.services.pedr.exceptions import (
    PEDRError,
    LexicalSearchError,
    SemanticSearchError,
    GraphLayerError,
    SyntacticLayerError,
    PragmaticLayerError,
    GovernanceLayerError,
    FusionError,
)
from app.services.pedr.search_orchestrator import (
    PEDRConfig,
    PEDRSearchOrchestrator,
    PEDRSearchResponse,
    LayerDiagnostic,
)
from app.services.pedr.fusion import RRFFusion
from app.services.pedr.syntactic import SyntacticService, SyntacticFilters
from app.services.pedr.pragmatic import PragmaticService, PragmaticFilters, QueryIntent


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pedr_cache():
    """Clear the PEDR cache before each test to avoid cross-test pollution."""
    cache = get_pedr_cache()
    cache.invalidate_all()
    yield
    cache.invalidate_all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RESULTS = [
    {"chunk_id": f"chunk-{i}", "content": f"Sample content {i}", "score": 0.9 - i * 0.1}
    for i in range(5)
]


def _make_orchestrator(
    *,
    lexical_fn=None,
    semantic_fn=None,
    config: Optional[PEDRConfig] = None,
) -> PEDRSearchOrchestrator:
    """Create a test orchestrator with injectable search functions."""
    cfg = config or PEDRConfig(enable_graph=False)
    return PEDRSearchOrchestrator(
        config=cfg,
        lexical_search=lexical_fn,
        semantic_search=semantic_fn,
        telemetry_enabled=False,
    )


def _ok_search(**kwargs) -> List[Dict[str, Any]]:
    return list(SAMPLE_RESULTS)


def _failing_search(**kwargs) -> List[Dict[str, Any]]:
    raise ConnectionError("Database connection lost")


def _timeout_search(**kwargs) -> List[Dict[str, Any]]:
    raise TimeoutError("Search timed out after 30s")


def _value_error_search(**kwargs) -> List[Dict[str, Any]]:
    raise ValueError("Invalid query embedding dimension")


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Verify PEDR exception types and inheritance."""

    def test_all_exceptions_inherit_from_pedr_error(self):
        for exc_cls in (
            LexicalSearchError,
            SemanticSearchError,
            GraphLayerError,
            SyntacticLayerError,
            PragmaticLayerError,
            GovernanceLayerError,
            FusionError,
        ):
            exc = exc_cls("test error")
            assert isinstance(exc, PEDRError)
            assert isinstance(exc, Exception)

    def test_layer_attribute_set_correctly(self):
        assert LexicalSearchError("x").layer == "lexical"
        assert SemanticSearchError("x").layer == "semantic"
        assert GraphLayerError("x").layer == "graph"
        assert SyntacticLayerError("x").layer == "syntactic"
        assert PragmaticLayerError("x").layer == "pragmatic"
        assert GovernanceLayerError("x").layer == "governance"
        assert FusionError("x").layer == "fusion"

    def test_pedr_error_base_layer_optional(self):
        exc = PEDRError("generic")
        assert exc.layer is None
        assert str(exc) == "generic"

    def test_exception_message_preserved(self):
        msg = "Qdrant connection refused on port 6333"
        exc = SemanticSearchError(msg)
        assert str(exc) == msg


# ---------------------------------------------------------------------------
# Graceful degradation tests
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify the orchestrator continues with available layers when one fails."""

    def test_lexical_failure_returns_semantic_results(self):
        orch = _make_orchestrator(
            lexical_fn=_failing_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)

        assert isinstance(response, PEDRSearchResponse)
        assert len(response.results) > 0
        assert response.metadata.degraded is True

        # Find lexical diagnostic
        lex_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "lexical"
        )
        assert lex_diag.status == "error"
        assert "Database connection lost" in lex_diag.error
        assert lex_diag.error_type == "ConnectionError"

        # Semantic should be ok
        sem_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "semantic"
        )
        assert sem_diag.status == "ok"
        assert sem_diag.result_count == 5

    def test_semantic_failure_returns_lexical_results(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_timeout_search,
        )
        response = orch.search(query="test query", top_k=5)

        assert len(response.results) > 0
        assert response.metadata.degraded is True

        sem_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "semantic"
        )
        assert sem_diag.status == "error"
        assert sem_diag.error_type == "TimeoutError"

        lex_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "lexical"
        )
        assert lex_diag.status == "ok"

    def test_both_retrieval_layers_fail_returns_empty(self):
        orch = _make_orchestrator(
            lexical_fn=_failing_search,
            semantic_fn=_timeout_search,
        )
        response = orch.search(query="test query", top_k=5)

        assert len(response.results) == 0
        assert response.metadata.degraded is True
        assert response.metadata.result_count == 0

        error_layers = [
            d for d in response.metadata.layer_diagnostics if d.status == "error"
        ]
        assert len(error_layers) >= 2

    def test_graph_failure_still_returns_lexical_semantic(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
            config=PEDRConfig(enable_graph=True),
        )
        # Mock graph service to fail
        orch.graph_service = MagicMock()
        orch.graph_service.expand_from_results.side_effect = RuntimeError(
            "Graph DB unavailable"
        )

        response = orch.search(query="test query", top_k=5)

        assert len(response.results) > 0
        assert response.metadata.degraded is True

        graph_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "graph"
        )
        assert graph_diag.status == "error"
        assert "Graph DB unavailable" in graph_diag.error


# ---------------------------------------------------------------------------
# Diagnostic reporting tests
# ---------------------------------------------------------------------------


class TestLayerDiagnostics:
    """Verify per-layer diagnostic metadata is correctly populated."""

    def test_all_ok_diagnostics_when_no_errors(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)

        assert response.metadata.degraded is False

        ok_diagnostics = [
            d for d in response.metadata.layer_diagnostics if d.status == "ok"
        ]
        assert len(ok_diagnostics) >= 2  # At least lexical + semantic

        for diag in ok_diagnostics:
            assert diag.duration_ms >= 0
            assert diag.error is None
            assert diag.error_type is None

    def test_disabled_layers_reported(self):
        config = PEDRConfig(
            enable_lexical=True,
            enable_semantic=True,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=False,
        )
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
            config=config,
        )
        response = orch.search(query="test query", top_k=5)

        disabled_layers = {
            d.layer
            for d in response.metadata.layer_diagnostics
            if d.status == "disabled"
        }
        assert "syntactic" in disabled_layers
        assert "pragmatic" in disabled_layers
        assert "governance" in disabled_layers
        assert "graph" in disabled_layers

    def test_error_diagnostic_contains_error_type(self):
        orch = _make_orchestrator(
            lexical_fn=_value_error_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)

        lex_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "lexical"
        )
        assert lex_diag.status == "error"
        assert lex_diag.error_type == "ValueError"
        assert "Invalid query embedding dimension" in lex_diag.error

    def test_diagnostics_include_timing(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)

        for diag in response.metadata.layer_diagnostics:
            assert diag.duration_ms >= 0.0

    def test_diagnostic_to_dict_format(self):
        diag = LayerDiagnostic(
            layer="lexical",
            status="error",
            duration_ms=45.23,
            result_count=0,
            error="Connection refused",
            error_type="ConnectionError",
        )
        d = diag.to_dict()
        assert d["layer"] == "lexical"
        assert d["status"] == "error"
        assert d["duration_ms"] == 45.23
        assert d["result_count"] == 0
        assert d["error"] == "Connection refused"
        assert d["error_type"] == "ConnectionError"

    def test_ok_diagnostic_omits_error_fields(self):
        diag = LayerDiagnostic(
            layer="semantic",
            status="ok",
            duration_ms=12.5,
            result_count=10,
        )
        d = diag.to_dict()
        assert "error" not in d
        assert "error_type" not in d


# ---------------------------------------------------------------------------
# Response schema tests
# ---------------------------------------------------------------------------


class TestResponseSchema:
    """Verify the response to_dict includes new diagnostic fields."""

    def test_response_to_dict_includes_diagnostics(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)
        response_dict = response.to_dict()

        assert "layer_diagnostics" in response_dict["metadata"]
        assert "degraded" in response_dict["metadata"]
        assert isinstance(response_dict["metadata"]["layer_diagnostics"], list)

    def test_degraded_response_to_dict(self):
        orch = _make_orchestrator(
            lexical_fn=_failing_search,
            semantic_fn=_ok_search,
        )
        response = orch.search(query="test query", top_k=5)
        response_dict = response.to_dict()

        assert response_dict["metadata"]["degraded"] is True
        error_diags = [
            d
            for d in response_dict["metadata"]["layer_diagnostics"]
            if d["status"] == "error"
        ]
        assert len(error_diags) >= 1


# ---------------------------------------------------------------------------
# Governance layer failure test
# ---------------------------------------------------------------------------


class TestGovernanceLayerFailure:
    """Verify governance layer failure is handled gracefully."""

    def test_governance_failure_still_returns_results(self):
        orch = _make_orchestrator(
            lexical_fn=_ok_search,
            semantic_fn=_ok_search,
        )
        # Mock quality service to fail
        orch.quality_service = MagicMock()
        orch.quality_service.apply.side_effect = RuntimeError("DB session expired")

        response = orch.search(query="test query", top_k=5)

        # Should still have results (governance is post-processing)
        assert len(response.results) > 0
        assert response.metadata.degraded is True

        gov_diag = next(
            d for d in response.metadata.layer_diagnostics if d.layer == "governance"
        )
        assert gov_diag.status == "error"
        assert "DB session expired" in gov_diag.error
