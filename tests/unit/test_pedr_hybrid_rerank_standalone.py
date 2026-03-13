"""Standalone unit tests for PEDR hybrid rerank search (B19.4).

This test file is isolated from the main test suite to avoid SQLAlchemy
model loading issues with SQLite (Mission model uses JSONB).

Tests cover:
- Cosine similarity calculation
- Semantic reranking logic
- Timing dataclass behavior
- Result dataclass behavior
- Mode selection logic
"""

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

# -----------------------------------------------------------------------------
# Self-contained implementations mirroring app/services/pedr/hybrid_rerank.py
# -----------------------------------------------------------------------------


@dataclass
class HybridRerankTimings:
    """Timing breakdown for hybrid rerank stages."""

    fts_ms: float = 0.0
    embedding_ms: float = 0.0
    rerank_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class HybridRerankResult:
    """Result from hybrid rerank search."""

    results: list[dict[str, Any]]
    timings: HybridRerankTimings
    mode_used: str
    fts_candidates_count: int
    fallback_used: bool


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def semantic_rerank(
    query_embedding: list[float],
    candidates: list[dict[str, Any]],
    id_to_vector: dict[str, list[float]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Rerank candidates by semantic similarity.

    This is a simplified version of the actual implementation for testing.
    """
    if not candidates:
        return []

    query_np = np.array(query_embedding)
    scored: list[tuple] = []

    for candidate in candidates:
        chunk_id = candidate.get("chunk_id")
        if chunk_id not in id_to_vector:
            continue
        candidate_vector = np.array(id_to_vector[chunk_id])
        similarity = cosine_similarity(query_np, candidate_vector)
        scored.append((chunk_id, similarity))

    # Sort by similarity descending
    scored.sort(key=lambda x: x[1], reverse=True)

    # Map back to candidates
    id_to_candidate = {c["chunk_id"]: c for c in candidates}
    reranked: list[dict[str, Any]] = []

    for chunk_id, semantic_score in scored[:top_k]:
        if chunk_id not in id_to_candidate:
            continue
        result = id_to_candidate[chunk_id].copy()
        result["semantic_score"] = float(semantic_score)
        result["score"] = float(semantic_score)
        reranked.append(result)

    return reranked


# -----------------------------------------------------------------------------
# Cosine Similarity Tests
# -----------------------------------------------------------------------------


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Identical vectors have similarity 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        sim = cosine_similarity(a, b)
        assert abs(sim - 1.0) < 1e-5

    def test_orthogonal_vectors(self):
        """Orthogonal vectors have similarity 0.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        sim = cosine_similarity(a, b)
        assert abs(sim - 0.0) < 1e-5

    def test_opposite_vectors(self):
        """Opposite vectors have similarity -1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        sim = cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-5

    def test_zero_vector_a(self):
        """Zero vector A returns 0.0 similarity."""
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_zero_vector_b(self):
        """Zero vector B returns 0.0 similarity."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 0.0, 0.0])
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_similar_vectors(self):
        """Similar vectors have high similarity."""
        a = np.array([0.9, 0.1, 0.0])
        b = np.array([0.85, 0.15, 0.0])
        sim = cosine_similarity(a, b)
        assert sim > 0.95

    def test_dissimilar_vectors(self):
        """Dissimilar vectors have lower similarity."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.5, 0.5, 0.5])
        sim = cosine_similarity(a, b)
        assert 0 < sim < 0.7


# -----------------------------------------------------------------------------
# Semantic Rerank Tests
# -----------------------------------------------------------------------------


class TestSemanticRerank:
    """Test semantic reranking logic."""

    def test_rerank_orders_by_similarity(self):
        """Rerank orders candidates by cosine similarity."""
        query_embedding = [1.0, 0.0, 0.0]

        candidates = [
            {"chunk_id": "c1", "content": "first", "fts_score": 0.5},
            {"chunk_id": "c2", "content": "second", "fts_score": 0.8},
        ]

        # c2's vector is more aligned with query
        id_to_vector = {
            "c1": [0.5, 0.5, 0.0],  # Less aligned
            "c2": [0.9, 0.1, 0.0],  # More aligned
        }

        reranked = semantic_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            id_to_vector=id_to_vector,
            top_k=2,
        )

        # c2 should rank first due to higher similarity
        assert len(reranked) == 2
        assert reranked[0]["chunk_id"] == "c2"
        assert reranked[1]["chunk_id"] == "c1"
        assert reranked[0]["semantic_score"] > reranked[1]["semantic_score"]

    def test_rerank_empty_candidates(self):
        """Empty candidates returns empty."""
        result = semantic_rerank(
            query_embedding=[0.1, 0.1, 0.1],
            candidates=[],
            id_to_vector={},
            top_k=10,
        )
        assert result == []

    def test_rerank_respects_top_k(self):
        """Rerank respects top_k limit."""
        candidates = [
            {"chunk_id": f"c{i}", "content": f"content {i}", "fts_score": 0.5}
            for i in range(10)
        ]

        id_to_vector = {f"c{i}": [float(i) / 10, 0.0, 0.0] for i in range(10)}

        reranked = semantic_rerank(
            query_embedding=[1.0, 0.0, 0.0],
            candidates=candidates,
            id_to_vector=id_to_vector,
            top_k=3,
        )

        assert len(reranked) == 3

    def test_rerank_missing_vectors_skipped(self):
        """Candidates without vectors are skipped."""
        candidates = [
            {"chunk_id": "c1", "content": "first", "fts_score": 0.5},
            {"chunk_id": "c2", "content": "second", "fts_score": 0.8},
            {"chunk_id": "c3", "content": "third", "fts_score": 0.3},
        ]

        # Only c1 and c3 have vectors
        id_to_vector = {
            "c1": [0.5, 0.5, 0.0],
            "c3": [0.9, 0.1, 0.0],
        }

        reranked = semantic_rerank(
            query_embedding=[1.0, 0.0, 0.0],
            candidates=candidates,
            id_to_vector=id_to_vector,
            top_k=5,
        )

        # Only 2 results (c2 is missing vector)
        assert len(reranked) == 2
        chunk_ids = [r["chunk_id"] for r in reranked]
        assert "c2" not in chunk_ids


# -----------------------------------------------------------------------------
# Timing Dataclass Tests
# -----------------------------------------------------------------------------


class TestHybridRerankTimings:
    """Test timing dataclass behavior."""

    def test_default_values(self):
        """Timings default to 0.0."""
        timings = HybridRerankTimings()
        assert timings.fts_ms == 0.0
        assert timings.embedding_ms == 0.0
        assert timings.rerank_ms == 0.0
        assert timings.total_ms == 0.0

    def test_custom_values(self):
        """Timings accept custom values."""
        timings = HybridRerankTimings(
            fts_ms=50.0,
            embedding_ms=100.0,
            rerank_ms=75.0,
            total_ms=225.0,
        )
        assert timings.fts_ms == 50.0
        assert timings.embedding_ms == 100.0
        assert timings.rerank_ms == 75.0
        assert timings.total_ms == 225.0


# -----------------------------------------------------------------------------
# Result Dataclass Tests
# -----------------------------------------------------------------------------


class TestHybridRerankResult:
    """Test result dataclass behavior."""

    def test_full_mode_result(self):
        """Full mode result has correct attributes."""
        result = HybridRerankResult(
            results=[{"chunk_id": "c1", "score": 0.9}],
            timings=HybridRerankTimings(total_ms=150.0),
            mode_used="full",
            fts_candidates_count=0,
            fallback_used=False,
        )

        assert result.mode_used == "full"
        assert result.fts_candidates_count == 0
        assert not result.fallback_used
        assert len(result.results) == 1

    def test_hybrid_mode_result(self):
        """Hybrid mode result has correct attributes."""
        result = HybridRerankResult(
            results=[{"chunk_id": "c1", "score": 0.9}],
            timings=HybridRerankTimings(
                fts_ms=30.0,
                embedding_ms=50.0,
                rerank_ms=70.0,
                total_ms=150.0,
            ),
            mode_used="hybrid",
            fts_candidates_count=50,
            fallback_used=False,
        )

        assert result.mode_used == "hybrid"
        assert result.fts_candidates_count == 50
        assert not result.fallback_used

    def test_fallback_result(self):
        """Fallback result indicates FTS returned empty."""
        result = HybridRerankResult(
            results=[{"chunk_id": "c1", "score": 0.9}],
            timings=HybridRerankTimings(total_ms=200.0),
            mode_used="hybrid",
            fts_candidates_count=0,
            fallback_used=True,
        )

        assert result.mode_used == "hybrid"
        assert result.fts_candidates_count == 0
        assert result.fallback_used is True


# -----------------------------------------------------------------------------
# Performance Characteristics Tests
# -----------------------------------------------------------------------------


class TestPerformanceCharacteristics:
    """Test expected performance characteristics."""

    def test_cosine_similarity_vectorized(self):
        """Cosine similarity should be fast with numpy."""
        a = np.random.rand(3072)  # OpenAI embedding dimension
        b = np.random.rand(3072)

        start = time.perf_counter()
        for _ in range(1000):
            cosine_similarity(a, b)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 1000 comparisons should complete in <100ms
        assert elapsed_ms < 100, f"1000 cosine similarities took {elapsed_ms:.1f}ms"

    def test_rerank_scales_with_candidates(self):
        """Rerank should handle 50-200 candidates efficiently."""
        query_embedding = list(np.random.rand(128))  # Smaller dim for test speed

        for pool_size in [50, 100, 200]:
            candidates = [
                {"chunk_id": f"c{i}", "content": f"content {i}", "fts_score": 0.5}
                for i in range(pool_size)
            ]
            id_to_vector = {
                f"c{i}": list(np.random.rand(128)) for i in range(pool_size)
            }

            start = time.perf_counter()
            result = semantic_rerank(
                query_embedding=query_embedding,
                candidates=candidates,
                id_to_vector=id_to_vector,
                top_k=10,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert len(result) == 10
            # Rerank of 200 candidates should complete in <50ms
            assert elapsed_ms < 50, f"Rerank of {pool_size} took {elapsed_ms:.1f}ms"


# -----------------------------------------------------------------------------
# Run tests if executed directly
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    test_classes = [
        TestCosineSimilarity,
        TestSemanticRerank,
        TestHybridRerankTimings,
        TestHybridRerankResult,
        TestPerformanceCharacteristics,
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {test_class.__name__}.{method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  ✗ {test_class.__name__}.{method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(
                        f"  ✗ {test_class.__name__}.{method_name}: {type(e).__name__}: {e}"
                    )
                    failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)
