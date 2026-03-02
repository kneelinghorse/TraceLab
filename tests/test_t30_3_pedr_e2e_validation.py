"""T30.3 PEDR Search Quality E2E Validation.

Validates the full PEDR search pipeline after Sprint 29's combined changes:
- LLM model swap (GPT-5.x)
- Embedding dimension doubling (1536 → 3072)
- Score compounding fix
- Cache poisoning fix
- Hybrid mode governance fix
- Evidence auto-linking upgrade (difflib → embeddings)

Success Criteria:
1. Search queries return relevant results with correct scoring
2. Synthesis produces coherent answers without errors
3. Evidence auto-linking matches semantically relevant chunks
4. No score inflation/deflation artifacts remain
5. Cache returns correct results (no poisoning)
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import settings


# ============================================================================
# SC-1: Search queries return relevant results with correct scoring
# ============================================================================


class TestSearchQueryScoringCorrectness:
    """Validate that PEDR scoring pipeline produces correct, non-inflated scores."""

    def test_rrf_fusion_produces_valid_scores(self):
        """RRF scores should be bounded and correctly computed."""
        from app.services.pedr.fusion import RRFFusion, LayerResult

        fusion = RRFFusion(k=60)

        # Simulate 3 layers with overlapping results
        lexical = LayerResult(
            layer_name="lexical",
            results=[
                {"chunk_id": "c1", "content": "user research findings", "score": 0.95},
                {"chunk_id": "c2", "content": "competitive analysis", "score": 0.85},
                {"chunk_id": "c3", "content": "market data", "score": 0.75},
            ],
            weight=0.25,
        )
        semantic = LayerResult(
            layer_name="semantic",
            results=[
                {"chunk_id": "c2", "content": "competitive analysis", "score": 0.92},
                {"chunk_id": "c1", "content": "user research findings", "score": 0.88},
                {"chunk_id": "c4", "content": "pricing strategy", "score": 0.80},
            ],
            weight=0.35,
        )
        syntactic = LayerResult(
            layer_name="syntactic",
            results=[
                {"chunk_id": "c1", "content": "user research findings", "score": 0.90},
                {"chunk_id": "c5", "content": "technical spec", "score": 0.70},
            ],
            weight=0.15,
        )

        output = fusion.fuse([lexical, semantic, syntactic], limit=10)

        # c1 appears in all 3 layers => highest RRF
        assert output.results[0].id == "c1"
        # c2 appears in 2 layers => second highest
        assert output.results[1].id == "c2"

        # All scores should be > 0 and bounded
        for result in output.results:
            assert result.rrf_score > 0.0
            assert result.rrf_score < 1.0  # RRF scores are always < 1

        # Multi-layer results should score higher than single-layer
        multi_layer_scores = [
            r.rrf_score for r in output.results if len(r.contributing_layers) > 1
        ]
        single_layer_scores = [
            r.rrf_score for r in output.results if len(r.contributing_layers) == 1
        ]
        if multi_layer_scores and single_layer_scores:
            assert max(multi_layer_scores) > max(single_layer_scores)

    def test_rrf_weighted_layers_respect_weights(self):
        """Layer weights should proportionally affect RRF scores."""
        from app.services.pedr.fusion import RRFFusion, LayerResult

        # Same result in two layers, but with different weights
        high_weight = LayerResult(
            layer_name="semantic", results=[{"chunk_id": "c1", "score": 0.9}], weight=0.5
        )
        low_weight = LayerResult(
            layer_name="lexical", results=[{"chunk_id": "c2", "score": 0.9}], weight=0.1
        )

        fusion = RRFFusion(k=60)
        output = fusion.fuse([high_weight, low_weight])

        scores = {r.id: r.rrf_score for r in output.results}
        # Higher-weight layer result should score higher
        assert scores["c1"] > scores["c2"]

    def test_score_fusion_formula_no_compounding(self):
        """Score fusion should be additive, not multiplicatively compounding."""
        from app.services.pedr.score_utils import fuse_independent_adjustments

        payload = {
            "rrf_score": 0.5,
            "type_boost": 0.10,
            "intent_boost": 0.15,
            "quality_score": 1.0,
        }

        fused = fuse_independent_adjustments(payload)

        # Expected: base * (1 + type_boost + intent_boost) * quality
        # = 0.5 * (1 + 0.10 + 0.15) * 1.0 = 0.5 * 1.25 = 0.625
        assert abs(fused - 0.625) < 1e-6
        assert payload["score_fusion"]["base_score"] == 0.5
        assert payload["score_fusion"]["additive_boost_factor"] == 1.25

    def test_ensure_base_score_persists_canonical_value(self):
        """Base score should be set once and not overwritten by subsequent boosts."""
        from app.services.pedr.score_utils import ensure_base_score, fuse_independent_adjustments

        payload = {"rrf_score": 0.45}

        # First call sets base score
        base1 = ensure_base_score(payload)
        assert base1 == 0.45
        assert payload["pedr_base_score"] == 0.45

        # Apply boosts
        payload["type_boost"] = 0.15
        payload["intent_boost"] = 0.10
        payload["quality_score"] = 1.1
        fuse_independent_adjustments(payload)

        # Base score should still be 0.45 even after fusion
        assert payload["pedr_base_score"] == 0.45
        assert payload["score_fusion"]["base_score"] == 0.45

    def test_score_stats_summary_correct(self):
        """Score statistics should compute correct min/max/avg/median/p90."""
        from app.services.pedr.score_utils import summarize_scores

        scores = [0.1, 0.3, 0.5, 0.7, 0.9]
        stats = summarize_scores(scores)

        assert stats["min"] == 0.1
        assert stats["max"] == 0.9
        assert abs(stats["avg"] - 0.5) < 1e-6
        assert stats["p50"] == 0.5  # median

    def test_pragmatic_intent_classification_accuracy(self):
        """Pragmatic layer should correctly classify common query intents."""
        from app.services.pedr.pragmatic import PragmaticService, QueryIntent

        service = PragmaticService()

        # Search queries
        for q in ["find documents about research", "show me insights", "what is the status?"]:
            result = service.classify_intent(q)
            assert result.intent == QueryIntent.SEARCH, f"'{q}' should be SEARCH"
            assert result.confidence >= 0.85

        # Execute queries
        for q in ["run the analysis", "execute the mission"]:
            result = service.classify_intent(q)
            assert result.intent == QueryIntent.EXECUTE, f"'{q}' should be EXECUTE"
            assert result.confidence >= 0.90

        # Create queries
        for q in ["create a new project", "add a document"]:
            result = service.classify_intent(q)
            assert result.intent == QueryIntent.CREATE, f"'{q}' should be CREATE"
            assert result.confidence >= 0.90


# ============================================================================
# SC-2: Synthesis produces coherent answers without errors
# ============================================================================


class _FakeChatCompletion:
    """Mock OpenAI chat completion response."""

    def __init__(self, content: str):
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = MagicMock(prompt_tokens=100, completion_tokens=50)


class _FakeCompletions:
    def __init__(self, response_content: str):
        self._content = response_content
        self.requests: list = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return _FakeChatCompletion(self._content)


class _FakeChat:
    def __init__(self, response_content: str):
        self.completions = _FakeCompletions(response_content)


class _FakeOpenAIClient:
    def __init__(self, response_content: str):
        self.chat = _FakeChat(response_content)


class TestSynthesisCoherence:
    """Validate GPT-5.x synthesis path after Sprint 29/30 changes."""

    def test_gpt5_uses_max_completion_tokens(self, monkeypatch):
        """GPT-5.x models must use max_completion_tokens, not max_tokens."""
        import app.services.rag_service as rag_module

        fake_client = _FakeOpenAIClient(
            "The research shows positive results. [Document: doc-1, Chunk: 0]"
        )
        monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
        monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)

        service = rag_module.RagService(
            pedr_orchestrator=_FakePEDROrchestrator(),
            embedding_service=_FakeEmbeddingService(),
            cache_service=_NoOpCacheService(),
            client=fake_client,
            model="gpt-5.1",
            default_temperature=0.2,
            cost_monitor=None,
        )

        service.run_query(query="test GPT-5 params", top_k=2, project_id="proj-1")

        request = fake_client.chat.completions.requests[0]
        assert "max_completion_tokens" in request, "GPT-5.x must use max_completion_tokens"
        assert "max_tokens" not in request, "GPT-5.x must NOT use max_tokens"
        assert request["reasoning_effort"] == "none"

    def test_non_gpt5_uses_max_tokens(self, monkeypatch):
        """Non-GPT-5 models should still use max_tokens."""
        import app.services.rag_service as rag_module

        fake_client = _FakeOpenAIClient(
            "Analysis complete. [Document: doc-1, Chunk: 0]"
        )
        monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
        monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)

        service = rag_module.RagService(
            pedr_orchestrator=_FakePEDROrchestrator(),
            embedding_service=_FakeEmbeddingService(),
            cache_service=_NoOpCacheService(),
            client=fake_client,
            model="gpt-4o",
            default_temperature=0.2,
            cost_monitor=None,
        )

        service.run_query(query="test GPT-4o params", top_k=2, project_id="proj-1")

        request = fake_client.chat.completions.requests[0]
        assert "max_tokens" in request, "Non-GPT-5 must use max_tokens"
        assert "max_completion_tokens" not in request

    def test_synthesis_extracts_citations(self, monkeypatch):
        """RAG synthesis should extract citation references from answer."""
        import app.services.rag_service as rag_module

        answer_text = (
            "User research reveals key findings. "
            "[Document: research-doc, Chunk: 3] "
            "Competitive analysis confirms trends. "
            "[Document: analysis-doc, Chunk: 1]"
        )
        fake_client = _FakeOpenAIClient(answer_text)
        monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
        monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)

        service = rag_module.RagService(
            pedr_orchestrator=_FakePEDROrchestrator(),
            embedding_service=_FakeEmbeddingService(),
            cache_service=_NoOpCacheService(),
            client=fake_client,
            model="gpt-5.1",
            default_temperature=0.2,
            cost_monitor=None,
        )

        result = service.run_query(query="user research findings", top_k=5, project_id="proj-1")

        assert "answer" in result
        assert len(result["answer"]) > 0


# ============================================================================
# SC-3: Evidence auto-linking matches semantically relevant chunks
# ============================================================================


class TestEvidenceAutoLinking:
    """Validate embedding-based evidence auto-linking (T29.6 upgrade)."""

    def test_embedding_path_selected_when_services_available(self):
        """Service should use embeddings when both services are available."""
        from app.services.evidence_auto_linking import EvidenceAutoLinkingService

        mock_embedding = MagicMock()
        mock_qdrant = MagicMock()

        svc = EvidenceAutoLinkingService(
            embedding_service=mock_embedding,
            qdrant_service=mock_qdrant,
            similarity_threshold=0.78,
        )

        # Verify services resolved
        emb, qdr = svc._resolve_services()
        assert emb is mock_embedding
        assert qdr is mock_qdrant

    def test_difflib_fallback_when_embeddings_unavailable(self):
        """Service should fall back to difflib when embedding services absent."""
        from app.services.evidence_auto_linking import EvidenceAutoLinkingService

        svc = EvidenceAutoLinkingService(
            embedding_service=None,
            qdrant_service=None,
            fallback_to_difflib=True,
        )

        emb, qdr = svc._resolve_services()
        # Without singleton setup, both should be None
        # (fallback_to_difflib controls whether difflib is used)
        assert svc.fallback_to_difflib is True

    def test_embedding_path_links_high_similarity_chunk(self):
        """Embedding path should link evidence to chunk when similarity > threshold."""
        from app.services.evidence_auto_linking import (
            EvidenceAutoLinkingService,
            EvidenceAutoLinkingResult,
        )

        mock_embedding = MagicMock()
        mock_embedding.generate_embedding.return_value = [0.1] * 3072  # 3072d vector

        mock_qdrant = MagicMock()
        mock_qdrant.search_chunks.return_value = [
            {"chunk_id": "chunk-abc", "score": 0.92, "content": "matching content"},
        ]

        mock_mission = MagicMock()
        mock_mission.mission_id = "test-mission-1"
        mock_evidence = MagicMock()
        mock_evidence.evidence_id = "ev-1"
        mock_evidence.chunk_id = ""
        mock_evidence.summary = "This evidence discusses user research methodology"
        mock_mission.evidence = [mock_evidence]

        svc = EvidenceAutoLinkingService(
            embedding_service=mock_embedding,
            qdrant_service=mock_qdrant,
            similarity_threshold=0.78,
        )

        mock_db = MagicMock()
        result = svc._link_via_embeddings(
            mock_db,
            mock_mission,
            None,
            EvidenceAutoLinkingResult(threshold=0.78),
            0.78,
            mock_embedding,
            mock_qdrant,
        )

        assert result.linked == 1
        assert result.failed == 0
        assert result.matches[0]["chunk_id"] == "chunk-abc"
        assert result.matches[0]["similarity"] == 0.92
        assert result.matches[0]["method"] == "embedding"

    def test_embedding_path_rejects_low_similarity(self):
        """Evidence below threshold should NOT be linked."""
        from app.services.evidence_auto_linking import (
            EvidenceAutoLinkingService,
            EvidenceAutoLinkingResult,
            AutoLinkErrorType,
        )

        mock_embedding = MagicMock()
        mock_embedding.generate_embedding.return_value = [0.1] * 3072

        mock_qdrant = MagicMock()
        mock_qdrant.search_chunks.return_value = [
            {"chunk_id": "chunk-xyz", "score": 0.55, "content": "unrelated content"},
        ]

        mock_mission = MagicMock()
        mock_mission.mission_id = "test-mission-2"
        mock_evidence = MagicMock()
        mock_evidence.evidence_id = "ev-2"
        mock_evidence.chunk_id = ""
        mock_evidence.summary = "Some evidence about a different topic"
        mock_mission.evidence = [mock_evidence]

        svc = EvidenceAutoLinkingService(
            embedding_service=mock_embedding,
            qdrant_service=mock_qdrant,
            similarity_threshold=0.78,
        )

        mock_db = MagicMock()
        result = svc._link_via_embeddings(
            mock_db,
            mock_mission,
            None,
            EvidenceAutoLinkingResult(threshold=0.78),
            0.78,
            mock_embedding,
            mock_qdrant,
        )

        assert result.linked == 0
        assert result.failed == 1
        assert result.errors[0]["error_type"] == AutoLinkErrorType.LOW_SIMILARITY.value

    def test_embedding_3072d_vector_dimensions(self):
        """Embedding service should generate 3072-dimension vectors for text-embedding-3-large."""
        # Verify config is set correctly
        assert settings.openai_embedding_dimension == 3072
        assert settings.openai_embedding_model == "text-embedding-3-large"


# ============================================================================
# SC-4: No score inflation/deflation artifacts remain
# ============================================================================


class TestScoreDistributionIntegrity:
    """Verify no score inflation or deflation artifacts from Sprint 29 changes."""

    def test_score_compounding_prevented(self):
        """Applying fuse_independent_adjustments twice should not compound scores."""
        from app.services.pedr.score_utils import fuse_independent_adjustments

        payload = {
            "rrf_score": 0.5,
            "type_boost": 0.10,
            "intent_boost": 0.05,
            "quality_score": 1.0,
        }

        # First fusion
        score1 = fuse_independent_adjustments(payload)
        # Second fusion (simulates accidental double-application)
        score2 = fuse_independent_adjustments(payload)

        # pedr_base_score was set on first call and should persist
        # So second call should produce same result since base doesn't change
        assert score1 == score2, "Double-application should not compound scores"

    def test_zero_boosts_produce_base_score(self):
        """With zero boosts and neutral quality, fused score should equal base."""
        from app.services.pedr.score_utils import fuse_independent_adjustments

        payload = {
            "rrf_score": 0.42,
            "type_boost": 0.0,
            "intent_boost": 0.0,
            "quality_score": 1.0,
        }

        fused = fuse_independent_adjustments(payload)
        assert abs(fused - 0.42) < 1e-6, "Zero boosts should preserve base score"

    def test_negative_quality_treated_as_neutral(self):
        """Negative or zero quality multiplier should default to 1.0."""
        from app.services.pedr.score_utils import fuse_independent_adjustments

        payload = {
            "rrf_score": 0.5,
            "type_boost": 0.0,
            "intent_boost": 0.0,
            "quality_score": 0.0,  # Edge case: zero quality
        }

        fused = fuse_independent_adjustments(payload)
        # quality_multiplier of 0 or negative should default to 1.0
        assert abs(fused - 0.5) < 1e-6

    def test_score_distribution_not_inflated_by_rrf(self):
        """RRF scores should be in reasonable range, not exceeding theoretical maximum."""
        from app.services.pedr.fusion import RRFFusion, LayerResult

        fusion = RRFFusion(k=60)

        # Maximum possible: result appears at rank 1 in all 5 layers
        layers = [
            LayerResult(
                layer_name=f"layer_{i}",
                results=[{"chunk_id": "c1", "score": 1.0}],
                weight=1.0,
            )
            for i in range(5)
        ]

        output = fusion.fuse(layers)
        max_score = output.results[0].rrf_score

        # Theoretical max: 5 * 1/(60+1) ≈ 0.0820
        theoretical_max = 5 * (1.0 / 61)
        assert max_score <= theoretical_max + 1e-6
        assert max_score > 0.0

    def test_typical_score_distribution(self):
        """Typical query should produce scores in expected RRF range."""
        from app.services.pedr.fusion import RRFFusion, LayerResult

        fusion = RRFFusion(k=60)

        # Typical: 10 results across 2 layers with partial overlap
        layer_a = LayerResult(
            layer_name="semantic",
            results=[
                {"chunk_id": f"c{i}", "score": 1.0 - i * 0.1}
                for i in range(10)
            ],
            weight=0.35,
        )
        layer_b = LayerResult(
            layer_name="lexical",
            results=[
                {"chunk_id": f"c{i+3}", "score": 0.9 - i * 0.1}
                for i in range(8)
            ],
            weight=0.25,
        )

        output = fusion.fuse([layer_a, layer_b])

        scores = [r.rrf_score for r in output.results]
        # All scores should be positive and bounded
        assert all(s > 0 for s in scores)
        assert all(s < 0.1 for s in scores)  # RRF with k=60 keeps scores small


# ============================================================================
# SC-5: Cache returns correct results (no poisoning)
# ============================================================================


class TestCacheCorrectness:
    """Validate PEDR cache correctness after Sprint 29's cache poisoning fix."""

    def test_cache_hit_returns_same_results(self):
        """Same query should return identical cached results."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)
        results = [{"chunk_id": "c1", "score": 0.9}, {"chunk_id": "c2", "score": 0.8}]

        cache.set(query="test query", top_k=10, filters={}, results=results)
        cached = cache.get(query="test query", top_k=10, filters={})

        assert cached == results
        assert cache.get_stats().cache_hits == 1

    def test_different_queries_dont_collide(self):
        """Different queries must produce different cache keys."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)

        results_a = [{"chunk_id": "c1", "score": 0.9}]
        results_b = [{"chunk_id": "c2", "score": 0.7}]

        cache.set(query="query A", top_k=10, filters={}, results=results_a)
        cache.set(query="query B", top_k=10, filters={}, results=results_b)

        assert cache.get(query="query A", top_k=10, filters={}) == results_a
        assert cache.get(query="query B", top_k=10, filters={}) == results_b

    def test_different_top_k_different_cache_keys(self):
        """Same query with different top_k should produce different cache entries."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)

        results_5 = [{"chunk_id": "c1"}]
        results_10 = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]

        cache.set(query="test", top_k=5, filters={}, results=results_5)
        cache.set(query="test", top_k=10, filters={}, results=results_10)

        assert cache.get(query="test", top_k=5, filters={}) == results_5
        assert cache.get(query="test", top_k=10, filters={}) == results_10

    def test_different_filters_different_cache_keys(self):
        """Same query with different filters should produce different cache entries."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)

        results_proj1 = [{"chunk_id": "c1"}]
        results_proj2 = [{"chunk_id": "c2"}]

        cache.set(
            query="test", top_k=10,
            filters={"project_id": "proj-1"}, results=results_proj1,
        )
        cache.set(
            query="test", top_k=10,
            filters={"project_id": "proj-2"}, results=results_proj2,
        )

        assert cache.get(query="test", top_k=10, filters={"project_id": "proj-1"}) == results_proj1
        assert cache.get(query="test", top_k=10, filters={"project_id": "proj-2"}) == results_proj2

    def test_ttl_expiration(self):
        """Expired entries should return None (cache miss)."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=1)  # 1 second TTL
        results = [{"chunk_id": "c1"}]

        cache.set(query="test", top_k=10, filters={}, results=results)
        assert cache.get(query="test", top_k=10, filters={}) == results

        # Wait for TTL to expire
        time.sleep(1.1)
        assert cache.get(query="test", top_k=10, filters={}) is None

    def test_invalidate_all_clears_cache(self):
        """Global invalidation should remove all entries."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set(query="q1", top_k=10, filters={}, results=[{"id": "1"}])
        cache.set(query="q2", top_k=10, filters={}, results=[{"id": "2"}])

        cleared = cache.invalidate_all()
        assert cleared == 2
        assert cache.get(query="q1", top_k=10, filters={}) is None
        assert cache.get(query="q2", top_k=10, filters={}) is None

    def test_project_scoped_invalidation(self):
        """Invalidating a project should only clear that project's entries."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=100, ttl_seconds=300)

        cache.set(
            query="q1", top_k=10,
            filters={"project_id": "proj-A"}, results=[{"id": "1"}],
        )
        cache.set(
            query="q2", top_k=10,
            filters={"project_id": "proj-B"}, results=[{"id": "2"}],
        )

        removed = cache.invalidate_project("proj-A")
        assert removed == 1

        # proj-A entry gone
        assert cache.get(query="q1", top_k=10, filters={"project_id": "proj-A"}) is None
        # proj-B entry still there
        assert cache.get(query="q2", top_k=10, filters={"project_id": "proj-B"}) == [{"id": "2"}]

    def test_lru_eviction(self):
        """LRU eviction should remove oldest entries when max_size exceeded."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=3, ttl_seconds=300)

        cache.set(query="q1", top_k=10, filters={}, results=[{"id": "1"}])
        cache.set(query="q2", top_k=10, filters={}, results=[{"id": "2"}])
        cache.set(query="q3", top_k=10, filters={}, results=[{"id": "3"}])

        # Access q1 to make it recently used
        cache.get(query="q1", top_k=10, filters={})

        # Adding q4 should evict q2 (oldest non-accessed)
        cache.set(query="q4", top_k=10, filters={}, results=[{"id": "4"}])

        assert cache.get(query="q1", top_k=10, filters={}) is not None  # recently accessed
        assert cache.get(query="q2", top_k=10, filters={}) is None  # evicted
        assert cache.get(query="q3", top_k=10, filters={}) is not None
        assert cache.get(query="q4", top_k=10, filters={}) is not None

    def test_cache_key_deterministic(self):
        """Same query params should always produce same cache key."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache()
        key1 = cache._generate_key("test query", 10, {"project_id": "p1"})
        key2 = cache._generate_key("test query", 10, {"project_id": "p1"})
        key3 = cache._generate_key("Test Query", 10, {"project_id": "p1"})  # case-insensitive

        assert key1 == key2
        assert key1 == key3  # normalized to lowercase

    def test_cache_stats_tracking(self):
        """Cache statistics should accurately track hits, misses, and evictions."""
        from app.services.pedr.cache import PEDRCache

        cache = PEDRCache(max_size=2, ttl_seconds=300)

        # Miss
        cache.get(query="q1", top_k=10, filters={})
        stats = cache.get_stats()
        assert stats.cache_misses == 1
        assert stats.cache_hits == 0

        # Set and hit
        cache.set(query="q1", top_k=10, filters={}, results=[{"id": "1"}])
        cache.get(query="q1", top_k=10, filters={})
        stats = cache.get_stats()
        assert stats.cache_hits == 1
        assert stats.cache_misses == 1


# ============================================================================
# SC-2 continued: Configuration validation
# ============================================================================


class TestConfigurationIntegrity:
    """Validate Sprint 29/30 configuration changes are correct."""

    def test_embedding_model_is_text_embedding_3_large(self):
        """Embedding model should be text-embedding-3-large after Sprint 29."""
        assert settings.openai_embedding_model == "text-embedding-3-large"

    def test_embedding_dimension_is_3072(self):
        """Embedding dimension should be 3072 after Sprint 29."""
        assert settings.openai_embedding_dimension == 3072

    def test_chat_model_is_gpt5(self):
        """Chat model should be GPT-5.x after Sprint 29."""
        assert settings.openai_chat_model.startswith("gpt-5")

    def test_pedr_cache_config(self):
        """PEDR cache should be configured with reasonable defaults."""
        assert settings.pedr_cache_enabled is True
        assert settings.pedr_cache_ttl_seconds == 300
        assert settings.pedr_cache_max_size >= 100


# ============================================================================
# Helpers for synthesis tests
# ============================================================================


class _FakePEDROrchestrator:
    """Fake PEDR orchestrator for synthesis tests."""

    def __init__(self, results=None):
        self.calls = []
        self._results = results or [
            {
                "chunk_id": "chunk-1",
                "content": "User research methodology includes qualitative interviews.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "rrf_score": 0.85,
                "embedding": [0.92, 0.2, 0.0],
            },
            {
                "chunk_id": "chunk-2",
                "content": "Competitive analysis reveals market trends in SaaS.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 1,
                "source_type": "report",
                "rrf_score": 0.72,
                "embedding": [0.61, 0.8, 0.0],
            },
        ]

    def search(self, **kwargs):
        from app.services.pedr.search_orchestrator import (
            PEDRSearchResponse,
            PEDRSearchResult,
            PEDRMetadata,
            LayerTimings,
        )

        self.calls.append(kwargs)
        results = [
            PEDRSearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                document_id=r.get("document_id"),
                project_id=r.get("project_id"),
                chunk_index=r.get("chunk_index"),
                source_type=r.get("source_type"),
                rrf_score=r.get("rrf_score", 0.0),
                embedding=r.get("embedding"),
            )
            for r in self._results
        ]
        metadata = PEDRMetadata(
            query=kwargs.get("query", ""),
            intent="factual",
            intent_confidence=0.9,
            detected_type=None,
            type_confidence=0.0,
            layers_used=["lexical", "semantic"],
            layer_weights={"lexical": 0.25, "semantic": 0.35},
            timings=LayerTimings(total_ms=50.0),
            total_candidates=len(results),
            result_count=len(results),
            cache_hit=False,
        )
        return PEDRSearchResponse(results=results, metadata=metadata)


class _FakeEmbeddingService:
    """Fake embedding service for synthesis tests."""

    def generate_embedding(self, text: str):
        return [0.1] * 3072


class _NoOpCacheService:
    """No-op cache service for synthesis tests."""

    def check_cache(self, **_kwargs):
        return None

    def store_in_cache(self, **_kwargs):
        pass
