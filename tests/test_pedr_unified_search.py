"""Tests for PEDR unified search API.

Tests cover:
- RRF fusion algorithm correctness
- Search orchestrator layer coordination
- Schema validation
- Endpoint integration

Note: These tests use pytest.mark.unit to avoid database fixture setup.
"""
import pytest
from datetime import date
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# Mark all tests in this module as unit tests to skip DB fixture
pytestmark = pytest.mark.unit

from app.services.pedr.fusion import (
    RRFFusion,
    RRFConfig,
    LayerResult,
    FusedResult,
    FusionOutput,
    rrf_score,
    RRF_K,
)
from app.services.pedr.search_orchestrator import (
    PEDRConfig,
    PEDRSearchOrchestrator,
    PEDRSearchResult,
    PEDRSearchResponse,
    DEFAULT_LAYER_WEIGHTS,
)
from app.schemas.pedr_search import (
    PEDRSearchRequest,
    PEDRSearchResponse as PEDRSearchResponseSchema,
    PEDRLayerWeights,
)


class _GraphRecorder:
    def __init__(self, layer_result: Optional[LayerResult] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.layer_result = layer_result or LayerResult(layer_name="graph", results=[])

    def expand_from_results(
        self,
        results: List[Dict[str, Any]],
        top_k: int,
        config: Any,
    ) -> LayerResult:
        self.calls.append({"results": results, "top_k": top_k, "config": config})
        return self.layer_result


# -----------------------------------------------------------------------------
# RRF Fusion Tests
# -----------------------------------------------------------------------------

class TestRRFScore:
    """Test the standalone rrf_score function."""

    def test_single_rank(self):
        """Single rank produces correct score."""
        score = rrf_score([1], k=60)
        assert score == pytest.approx(1 / 61, rel=1e-5)

    def test_multiple_ranks(self):
        """Multiple ranks sum correctly."""
        score = rrf_score([1, 1], k=60)
        assert score == pytest.approx(2 / 61, rel=1e-5)

    def test_zero_rank_ignored(self):
        """Zero ranks (not present) are ignored."""
        score = rrf_score([1, 0, 2], k=60)
        expected = (1 / 61) + (1 / 62)
        assert score == pytest.approx(expected, rel=1e-5)

    def test_empty_ranks(self):
        """Empty ranks return zero."""
        score = rrf_score([])
        assert score == 0.0

    def test_custom_k(self):
        """Custom k value is respected."""
        score = rrf_score([1], k=30)
        assert score == pytest.approx(1 / 31, rel=1e-5)


class TestRRFFusion:
    """Test the RRFFusion class."""

    def test_empty_layers(self):
        """No layers returns empty results."""
        fusion = RRFFusion()
        output = fusion.fuse([])
        assert output.results == []
        assert output.total_unique == 0

    def test_single_layer(self):
        """Single layer preserves ranking."""
        fusion = RRFFusion()
        layer = LayerResult(
            layer_name="test",
            results=[
                {"chunk_id": "c1", "score": 0.9, "content": "first"},
                {"chunk_id": "c2", "score": 0.8, "content": "second"},
            ],
        )
        output = fusion.fuse([layer])

        assert len(output.results) == 2
        assert output.results[0].id == "c1"
        assert output.results[1].id == "c2"
        assert output.results[0].rrf_score > output.results[1].rrf_score

    def test_multi_layer_fusion(self):
        """Multi-layer fusion combines results correctly."""
        fusion = RRFFusion()
        layer1 = LayerResult(
            layer_name="lexical",
            results=[
                {"chunk_id": "c1", "score": 0.9},
                {"chunk_id": "c2", "score": 0.8},
            ],
        )
        layer2 = LayerResult(
            layer_name="semantic",
            results=[
                {"chunk_id": "c2", "score": 0.95},  # c2 also in lexical
                {"chunk_id": "c3", "score": 0.7},
            ],
        )
        output = fusion.fuse([layer1, layer2])

        # c2 should rank highest (appears in both)
        assert output.results[0].id == "c2"
        assert "lexical" in output.results[0].contributing_layers
        assert "semantic" in output.results[0].contributing_layers

        # c1 and c3 only in one layer each
        other_ids = {r.id for r in output.results[1:]}
        assert "c1" in other_ids
        assert "c3" in other_ids

    def test_weighted_fusion(self):
        """Layer weights affect final scores."""
        fusion = RRFFusion(layer_weights={"heavy": 2.0, "light": 0.5})
        layer_heavy = LayerResult(
            layer_name="heavy",
            results=[{"chunk_id": "c1", "score": 0.5}],
            weight=2.0,
        )
        layer_light = LayerResult(
            layer_name="light",
            results=[{"chunk_id": "c2", "score": 0.9}],
            weight=0.5,
        )
        output = fusion.fuse([layer_heavy, layer_light])

        # c1 should score higher due to higher weight despite lower original score
        assert output.results[0].id == "c1"

    def test_limit_applied(self):
        """Limit caps number of results."""
        fusion = RRFFusion()
        layer = LayerResult(
            layer_name="test",
            results=[{"chunk_id": f"c{i}"} for i in range(10)],
        )
        output = fusion.fuse([layer], limit=3)
        assert len(output.results) == 3

    def test_min_score_filter(self):
        """Results below min_score are excluded."""
        fusion = RRFFusion(min_score=0.02)
        layer = LayerResult(
            layer_name="test",
            results=[
                {"chunk_id": "c1"},  # rank 1 -> score ~0.0164
            ],
        )
        output = fusion.fuse([layer])
        # With k=60, rank 1 gives 1/61 ≈ 0.0164 < 0.02
        assert len(output.results) == 0

    def test_layer_scores_included(self):
        """Layer scores are tracked when include_layer_scores=True."""
        fusion = RRFFusion(include_layer_scores=True)
        layer = LayerResult(
            layer_name="test",
            results=[{"chunk_id": "c1", "score": 0.85}],
        )
        output = fusion.fuse([layer])
        assert output.results[0].layer_scores == {"test": 0.85}

    def test_fuse_simple(self):
        """fuse_simple returns enriched dicts."""
        fusion = RRFFusion()
        results1 = [{"chunk_id": "c1", "content": "a"}]
        results2 = [{"chunk_id": "c1", "content": "a"}]

        merged = fusion.fuse_simple(
            results1,
            results2,
            layer_names=["l1", "l2"],
        )

        assert len(merged) == 1
        assert merged[0]["rrf_score"] > 0
        assert merged[0]["contributing_layers"] == ["l1", "l2"]


# -----------------------------------------------------------------------------
# Search Orchestrator Tests
# -----------------------------------------------------------------------------

class TestPEDRSearchOrchestrator:
    """Test the search orchestrator."""

    @pytest.fixture
    def mock_lexical(self):
        """Mock lexical search returning sample results."""
        return MagicMock(return_value=[
            {"chunk_id": "lex1", "content": "lexical match 1", "score": 0.8},
            {"chunk_id": "lex2", "content": "lexical match 2", "score": 0.6},
        ])

    @pytest.fixture
    def mock_semantic(self):
        """Mock semantic search returning sample results."""
        return MagicMock(return_value=[
            {"chunk_id": "sem1", "content": "semantic match 1", "score": 0.9},
            {"chunk_id": "lex1", "content": "lexical match 1", "score": 0.7},  # overlap
        ])

    def test_search_fuses_layers(self, mock_lexical, mock_semantic):
        """Search fuses lexical and semantic results."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(query="test query", top_k=5)

        assert len(response.results) <= 5
        # lex1 should rank high (in both layers)
        chunk_ids = [r.chunk_id for r in response.results]
        assert "lex1" in chunk_ids

        mock_lexical.assert_called_once()
        mock_semantic.assert_called_once()

    def test_search_with_disabled_layers(self, mock_lexical, mock_semantic):
        """Disabled layers are not called."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(
            query="test",
            top_k=5,
            enable_lexical=False,
        )

        mock_lexical.assert_not_called()
        mock_semantic.assert_called_once()

    def test_search_metadata(self, mock_lexical, mock_semantic):
        """Search returns proper metadata."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(query="find documents about testing")

        assert response.metadata.query == "find documents about testing"
        assert response.metadata.intent in ("search", "create", "update", "delete", "execute")
        assert 0 <= response.metadata.intent_confidence <= 1
        assert response.metadata.timings.total_ms > 0

    def test_search_applies_syntactic_type(self, mock_lexical, mock_semantic):
        """Syntactic layer detects and applies element type."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(query="find missions about user research")

        # Should detect "mission" type
        assert response.metadata.detected_type == "mission" or response.metadata.type_confidence > 0

    def test_search_applies_pragmatic_intent(self, mock_lexical, mock_semantic):
        """Pragmatic layer classifies intent."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(query="show all documents")

        assert response.metadata.intent == "search"
        assert response.metadata.intent_confidence >= 0.5

    def test_config_override(self, mock_lexical, mock_semantic):
        """Runtime config overrides base config."""
        base_config = PEDRConfig(
            enable_governance=True,
            min_quality_gates=3,
        )
        orchestrator = PEDRSearchOrchestrator(
            config=base_config,
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
        )

        response = orchestrator.search(
            query="test",
            enable_governance=False,  # Override
        )

        # Governance should be disabled
        assert response.metadata.timings.governance_ms == 0.0

    def test_empty_results(self):
        """Handles no results gracefully."""
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=MagicMock(return_value=[]),
            semantic_search=MagicMock(return_value=[]),
        )

        response = orchestrator.search(query="nonexistent query")

        assert response.results == []
        assert response.metadata.result_count == 0

    def test_graph_layer_disabled_by_default(self, mock_lexical, mock_semantic):
        """Graph layer is not executed unless enabled."""
        graph_service = MagicMock()
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
            graph_service=graph_service,
        )

        response = orchestrator.search(query="graph disabled query")

        graph_service.expand_from_results.assert_not_called()
        assert "graph" not in response.metadata.layers_used

    def test_graph_layer_enabled_includes_results(self, mock_lexical, mock_semantic):
        """Graph layer results are fused when enabled."""
        graph_layer = LayerResult(
            layer_name="graph",
            results=[{"chunk_id": "graph1", "content": "graph hit", "score": 0.42}],
            latency_ms=12.5,
        )
        graph_service = MagicMock()
        graph_service.expand_from_results.return_value = graph_layer
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
            graph_service=graph_service,
        )

        response = orchestrator.search(query="graph enabled query", enable_graph=True, top_k=10)

        graph_service.expand_from_results.assert_called_once()
        assert "graph" in response.metadata.layers_used
        assert "graph1" in [r.chunk_id for r in response.results]

    def test_graph_layer_config_passed_through(self, mock_lexical, mock_semantic):
        """Graph layer receives the configured traversal settings."""
        recorder = _GraphRecorder()
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
            graph_service=recorder,
        )

        orchestrator.search(
            query="graph config query",
            enable_graph=True,
            graph_depth=3,
            graph_decay=0.5,
            graph_edge_types=["contains"],
            graph_top_k_seeds=7,
        )

        assert recorder.calls
        call = recorder.calls[0]
        assert call["top_k"] == 7
        config = call["config"]
        assert config.max_depth == 3
        assert config.decay_factor == 0.5
        assert config.allowed_edge_types == ("contains",)

    def test_graph_layer_timing_recorded(self, mock_lexical, mock_semantic):
        """Graph layer latency is reported in timings."""
        graph_layer = LayerResult(
            layer_name="graph",
            results=[],
            latency_ms=18.0,
        )
        recorder = _GraphRecorder(layer_result=graph_layer)
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
            graph_service=recorder,
        )

        response = orchestrator.search(query="graph timing query", enable_graph=True)

        assert response.metadata.timings.graph_ms == pytest.approx(18.0, rel=1e-3)

    def test_graph_weights_normalized_and_back_compat(self, mock_lexical, mock_semantic):
        """Graph weights normalize and defaults remain stable when disabled."""
        recorder = _GraphRecorder()
        orchestrator = PEDRSearchOrchestrator(
            lexical_search=mock_lexical,
            semantic_search=mock_semantic,
            graph_service=recorder,
        )

        response_no_graph = orchestrator.search(query="graph weights baseline")
        weights_no_graph = response_no_graph.metadata.layer_weights
        assert weights_no_graph["lexical"] == pytest.approx(0.25, rel=1e-3)

        response_graph = orchestrator.search(query="graph weights enabled", enable_graph=True)
        weights_graph = response_graph.metadata.layer_weights
        assert weights_graph["graph"] == pytest.approx(0.12, rel=1e-3)
        assert sum(weights_graph.values()) == pytest.approx(1.0, rel=1e-3)


# -----------------------------------------------------------------------------
# Schema Tests
# -----------------------------------------------------------------------------

class TestPEDRSchemas:
    """Test Pydantic schema validation."""

    def test_request_basic(self):
        """Basic request validates."""
        request = PEDRSearchRequest(query="test query")
        assert request.query == "test query"
        assert request.top_k == 10  # default

    def test_request_all_fields(self):
        """Request with all fields validates."""
        request = PEDRSearchRequest(
            query="test",
            top_k=20,
            project_id="12345678-1234-5678-1234-567812345678",
            element_type="document",
            element_types=["mission", "document"],
            auto_detect_type=False,
            enable_lexical=True,
            enable_semantic=False,
            layer_weights=PEDRLayerWeights(lexical=0.5, semantic=0.5),
        )
        assert request.top_k == 20
        assert request.element_type == "document"
        assert request.enable_semantic is False

    def test_request_validation(self):
        """Invalid requests raise validation errors."""
        with pytest.raises(ValueError):
            PEDRSearchRequest(query="")  # Empty query

        with pytest.raises(ValueError):
            PEDRSearchRequest(query="test", top_k=0)  # top_k < 1

    def test_layer_weights_validation(self):
        """Layer weights validate ranges."""
        weights = PEDRLayerWeights(lexical=0.3, semantic=0.7)
        assert weights.lexical == 0.3

        with pytest.raises(ValueError):
            PEDRLayerWeights(lexical=1.5)  # > 1.0


# -----------------------------------------------------------------------------
# Integration Tests (require database)
# -----------------------------------------------------------------------------

class TestPEDRIntegration:
    """Integration tests requiring full service stack."""

    @pytest.mark.skip(reason="Requires database connection")
    def test_create_orchestrator_factory(self):
        """Factory creates fully wired orchestrator."""
        from app.services.pedr.search_orchestrator import create_pedr_orchestrator

        orchestrator = create_pedr_orchestrator()
        assert orchestrator._lexical_search is not None
        assert orchestrator._semantic_search is not None

    @pytest.mark.skip(reason="Requires database connection")
    def test_full_search_pipeline(self):
        """Full search pipeline executes."""
        from app.services.pedr.search_orchestrator import create_pedr_orchestrator

        orchestrator = create_pedr_orchestrator()
        response = orchestrator.search(query="user research methodology", top_k=5)

        assert response.metadata.result_count >= 0
        assert response.metadata.timings.total_ms > 0


# -----------------------------------------------------------------------------
# RRF Algorithm Correctness Tests
# -----------------------------------------------------------------------------

class TestRRFAlgorithmCorrectness:
    """Verify RRF algorithm produces expected mathematical results."""

    def test_identical_rankings_same_score(self):
        """Results in same position across layers get equal contribution."""
        fusion = RRFFusion()
        layer1 = LayerResult("l1", results=[{"chunk_id": "c1"}])
        layer2 = LayerResult("l2", results=[{"chunk_id": "c2"}])

        output = fusion.fuse([layer1, layer2])

        # Both at rank 1 in their respective layers -> same score
        scores = {r.id: r.rrf_score for r in output.results}
        assert scores["c1"] == pytest.approx(scores["c2"], rel=1e-5)

    def test_overlap_beats_single_layer(self):
        """Document in multiple layers beats single-layer results."""
        fusion = RRFFusion()
        layer1 = LayerResult("l1", results=[{"chunk_id": "overlap"}, {"chunk_id": "only1"}])
        layer2 = LayerResult("l2", results=[{"chunk_id": "overlap"}, {"chunk_id": "only2"}])

        output = fusion.fuse([layer1, layer2])

        # overlap should be first
        assert output.results[0].id == "overlap"

        # overlap score should be higher than others
        overlap_score = output.results[0].rrf_score
        for r in output.results[1:]:
            assert r.rrf_score < overlap_score

    def test_k_constant_effect(self):
        """Lower k constant gives more weight to top ranks."""
        # With k=1, rank 1 gets 1/2 = 0.5, rank 2 gets 1/3 = 0.33
        # With k=60, rank 1 gets 1/61 ≈ 0.016, rank 2 gets 1/62 ≈ 0.016
        # Lower k = bigger spread between ranks

        fusion_low_k = RRFFusion(k=1)
        fusion_high_k = RRFFusion(k=100)

        layer = LayerResult("test", results=[
            {"chunk_id": "c1"},
            {"chunk_id": "c2"},
        ])

        out_low = fusion_low_k.fuse([layer])
        out_high = fusion_high_k.fuse([layer])

        # Calculate ratio of rank1 to rank2 score
        ratio_low = out_low.results[0].rrf_score / out_low.results[1].rrf_score
        ratio_high = out_high.results[0].rrf_score / out_high.results[1].rrf_score

        # Low k should have higher ratio (bigger spread)
        assert ratio_low > ratio_high
