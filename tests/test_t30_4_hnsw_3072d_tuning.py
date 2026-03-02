"""T30.4 HNSW Parameter Re-tuning for 3072d Vectors.

Validates that HNSW index parameters have been updated for the new
3072-dimension vectors from text-embedding-3-large.

Sprint 19 tuned for 1536d (ef_search=64 gave 45% P99 improvement, 100% recall).
Sprint 29 doubled dimensions to 3072. This mission re-tunes parameters.

Success Criteria:
1. HNSW parameters benchmarked for 3072d vectors
2. P99 latency remains under target threshold
3. Recall rate maintained at 100% for current corpus size
4. Updated parameters deployed to Qdrant collection
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings


# ============================================================================
# SC-1: HNSW parameters benchmarked for 3072d vectors
# ============================================================================


class TestHNSWConfigurationFor3072d:
    """Validate HNSW parameters are correctly set for 3072d vectors."""

    def test_hnsw_m_increased_for_3072d(self):
        """Graph degree m should be 24 for 3072d (was 16 for 1536d).

        Rationale: Higher dimensions benefit from higher m for graph connectivity.
        m=24 provides ~50% more edges per node, improving recall in 3072d space.
        """
        assert settings.qdrant_hnsw_m == 24

    def test_hnsw_ef_construct_increased_for_3072d(self):
        """ef_construct should be 128 for 3072d (was 100 for 1536d).

        Rationale: Higher ef_construct improves index quality at construction time.
        For 3072d vectors, the search space is larger, requiring more candidates
        during graph construction for optimal node connectivity.
        """
        assert settings.qdrant_hnsw_ef_construct == 128

    def test_hnsw_ef_search_default_maintained(self):
        """ef_search default should remain 64.

        Sprint 19 showed 100% recall at 7K corpus for all ef values (32-128).
        No reason to change the default — adaptive scaling handles larger top_k.
        """
        assert settings.qdrant_hnsw_ef_default == 64

    def test_embedding_dimension_is_3072(self):
        """Embedding dimension should be 3072 for text-embedding-3-large."""
        assert settings.openai_embedding_dimension == 3072


class TestCollectionCreationParameters:
    """Validate collection creation uses updated HNSW parameters."""

    def test_query_optimized_uses_config_m(self):
        """Query-optimized collection should use settings.qdrant_hnsw_m."""
        from app.services.qdrant_service import QdrantService

        mock_client = MagicMock()
        mock_client.collection_exists.return_value = False

        service = QdrantService(
            client=mock_client,
            collection_name="test_collection",
            vector_size=3072,
        )

        service._create_collection(write_optimized=False)

        call_args = mock_client.create_collection.call_args
        vectors_config = call_args.kwargs.get("vectors_config") or call_args[1].get("vectors_config")

        # Verify HNSW config uses settings-driven m and ef_construct
        hnsw = vectors_config.hnsw_config
        assert hnsw.m == settings.qdrant_hnsw_m  # 24
        assert hnsw.ef_construct == settings.qdrant_hnsw_ef_construct  # 128

    def test_write_optimized_uses_lower_m(self):
        """Write-optimized collection should use m=16 for faster bulk import."""
        from app.services.qdrant_service import QdrantService

        mock_client = MagicMock()
        mock_client.collection_exists.return_value = False

        service = QdrantService(
            client=mock_client,
            collection_name="test_collection",
            vector_size=3072,
        )

        service._create_collection(write_optimized=True)

        call_args = mock_client.create_collection.call_args
        vectors_config = call_args.kwargs.get("vectors_config") or call_args[1].get("vectors_config")

        hnsw = vectors_config.hnsw_config
        assert hnsw.m == 16  # Lower m for write speed
        assert hnsw.ef_construct == 64  # Lower ef_construct for write speed

    def test_vector_size_3072(self):
        """Collection should be created with vector_size=3072."""
        from app.services.qdrant_service import QdrantService

        mock_client = MagicMock()
        mock_client.collection_exists.return_value = False

        service = QdrantService(
            client=mock_client,
            collection_name="test_collection",
            vector_size=3072,
        )

        service._create_collection(write_optimized=False)

        call_args = mock_client.create_collection.call_args
        vectors_config = call_args.kwargs.get("vectors_config") or call_args[1].get("vectors_config")
        assert vectors_config.size == 3072


# ============================================================================
# SC-2: P99 latency remains under target threshold
# ============================================================================


class TestAdaptiveEfScaling:
    """Validate recommend_hnsw_ef is tuned for 3072d."""

    def test_small_top_k_uses_base_ef(self):
        """top_k <= 5 should use base ef (64)."""
        from app.services.retrieval_service import RetrievalService

        service = MagicMock(spec=RetrievalService)
        service.recommend_hnsw_ef = RetrievalService.recommend_hnsw_ef.__get__(service)

        assert service.recommend_hnsw_ef(1) == 64
        assert service.recommend_hnsw_ef(5) == 64

    def test_medium_top_k_scales_for_3072d(self):
        """top_k 6-10 should use ef=80 for 3072d recall margin."""
        from app.services.retrieval_service import RetrievalService

        service = MagicMock(spec=RetrievalService)
        service.recommend_hnsw_ef = RetrievalService.recommend_hnsw_ef.__get__(service)

        ef = service.recommend_hnsw_ef(10)
        assert ef == 80  # Increased from 72 for 3072d

    def test_large_top_k_scales_more_aggressively(self):
        """top_k 11-20 should use ef=112 for 3072d recall."""
        from app.services.retrieval_service import RetrievalService

        service = MagicMock(spec=RetrievalService)
        service.recommend_hnsw_ef = RetrievalService.recommend_hnsw_ef.__get__(service)

        ef = service.recommend_hnsw_ef(20)
        assert ef == 112  # Increased from 96 for 3072d

    def test_very_large_top_k_caps_at_160(self):
        """Very large top_k should cap at 160 for 3072d (was 128 for 1536d)."""
        from app.services.retrieval_service import RetrievalService

        service = MagicMock(spec=RetrievalService)
        service.recommend_hnsw_ef = RetrievalService.recommend_hnsw_ef.__get__(service)

        ef = service.recommend_hnsw_ef(50)
        assert ef == 160  # Cap at 160 for 3072d

    def test_ef_scaling_monotonic(self):
        """Higher top_k should always produce equal or higher ef."""
        from app.services.retrieval_service import RetrievalService

        service = MagicMock(spec=RetrievalService)
        service.recommend_hnsw_ef = RetrievalService.recommend_hnsw_ef.__get__(service)

        prev_ef = 0
        for k in [1, 3, 5, 8, 10, 15, 20, 30, 50]:
            ef = service.recommend_hnsw_ef(k)
            assert ef >= prev_ef, f"ef should not decrease: top_k={k}, ef={ef} < prev={prev_ef}"
            prev_ef = ef


# ============================================================================
# SC-3: Recall rate maintained at 100% for current corpus size
# ============================================================================


class TestBenchmarkScriptCompatibility:
    """Validate the benchmark script works with 3072d configuration."""

    def test_sweep_produces_valid_results(self, tmp_path):
        """Parameter sweep should produce valid benchmark results."""
        import scripts.qdrant_parameter_sweep as sweep

        class _StubService:
            collection_name = "research_chunks"
            vector_size = 3072

            def search_chunks(self, *, query_vector, top_k, hnsw_ef, **_kwargs):
                # Simulate consistent results regardless of ef (100% recall)
                time.sleep(0.001 + hnsw_ef / 100000.0)
                return [
                    {"chunk_id": f"chunk-{i}", "score": 1.0 - i * 0.01}
                    for i in range(top_k)
                ]

            def get_collection_diagnostics(self):
                return {
                    "collection": self.collection_name,
                    "collection_exists": True,
                    "points_count": 7_000,
                    "vectors_count": 7_000,
                    "payload_indexes": [],
                    "hnsw": {
                        "m": settings.qdrant_hnsw_m,
                        "ef_construct": settings.qdrant_hnsw_ef_construct,
                        "full_scan_threshold": 20_000,
                        "on_disk": False,
                    },
                    "quantization": {
                        "enabled": True,
                        "type": "ScalarType.INT8",
                        "always_ram": True,
                        "quantile": 0.99,
                    },
                    "optimizer": {"indexing_threshold": 20_000},
                    "vector_size": self.vector_size,
                    "memory_estimate_bytes": 150_000_000,
                    "memory_estimate_gb": 0.14,
                    "error": None,
                }

        vectors = [[0.01 * i for _ in range(3072)] for i in range(10)]
        output = tmp_path / "sweep.json"

        payload = sweep.run_sweep(
            top_k=5,
            trials=len(vectors),
            ef_values=[64, 96, 128],
            output_path=output,
            service=_StubService(),
            sample_vectors=vectors,
        )

        assert output.exists()
        # All ef values should show 100% recall (stub returns consistent results)
        for entry in payload["results"]:
            assert entry["recall"] == 1.0

    def test_sweep_reports_correct_hnsw_config(self, tmp_path):
        """Benchmark output should report m=24, ef_construct=128."""
        import json
        import scripts.qdrant_parameter_sweep as sweep

        class _StubService:
            collection_name = "research_chunks"
            vector_size = 3072

            def search_chunks(self, *, query_vector, top_k, hnsw_ef, **_kwargs):
                return [
                    {"chunk_id": f"chunk-{i}", "score": 1.0 - i * 0.01}
                    for i in range(top_k)
                ]

            def get_collection_diagnostics(self):
                return {
                    "collection": self.collection_name,
                    "collection_exists": True,
                    "points_count": 1_000,
                    "vectors_count": 1_000,
                    "payload_indexes": [],
                    "hnsw": {
                        "m": 24,
                        "ef_construct": 128,
                        "full_scan_threshold": 20_000,
                        "on_disk": False,
                    },
                    "quantization": {"enabled": True, "type": "INT8", "always_ram": True, "quantile": 0.99},
                    "optimizer": {"indexing_threshold": 20_000},
                    "vector_size": 3072,
                    "memory_estimate_bytes": 30_000_000,
                    "memory_estimate_gb": 0.03,
                    "error": None,
                }

        vectors = [[0.1] * 3072 for _ in range(5)]
        output = tmp_path / "sweep.json"

        sweep.run_sweep(
            top_k=3,
            trials=5,
            ef_values=[64, 128],
            output_path=output,
            service=_StubService(),
            sample_vectors=vectors,
        )

        data = json.loads(output.read_text())
        assert data["collection"] == "research_chunks"


# ============================================================================
# SC-4: Updated parameters deployed to Qdrant collection
# ============================================================================


class TestApplyHNSWSettings:
    """Validate apply_hnsw_settings uses correct parameters."""

    def test_apply_hnsw_settings_sends_correct_params(self):
        """apply_hnsw_settings should forward m=24, ef_construct=128 to Qdrant."""
        from app.services.qdrant_service import QdrantService

        mock_client = MagicMock()
        mock_client.collection_exists.return_value = True

        service = QdrantService(
            client=mock_client,
            collection_name="research_chunks",
            vector_size=3072,
        )

        service.apply_hnsw_settings(
            m=settings.qdrant_hnsw_m,
            ef_construct=settings.qdrant_hnsw_ef_construct,
            full_scan_threshold=20_000,
            on_disk=False,
        )

        call_args = mock_client.update_collection.call_args
        hnsw_config = call_args.kwargs.get("hnsw_config") or call_args[1].get("hnsw_config")
        assert hnsw_config.m == 24
        assert hnsw_config.ef_construct == 128
        assert hnsw_config.full_scan_threshold == 20_000

    def test_apply_hnsw_settings_enables_quantization(self):
        """Quantization should be enabled by default for memory efficiency."""
        from app.services.qdrant_service import QdrantService

        mock_client = MagicMock()
        mock_client.collection_exists.return_value = True

        service = QdrantService(
            client=mock_client,
            collection_name="research_chunks",
            vector_size=3072,
        )

        service.apply_hnsw_settings(
            m=24,
            ef_construct=128,
            full_scan_threshold=20_000,
            enable_quantization=True,
            quantile=0.99,
            always_ram=True,
        )

        call_args = mock_client.update_collection.call_args
        quant = call_args.kwargs.get("quantization_config") or call_args[1].get("quantization_config")
        assert quant is not None


# ============================================================================
# Parameter relationship validation
# ============================================================================


class TestParameterRelationships:
    """Validate HNSW parameter relationships and constraints."""

    def test_ef_construct_greater_than_2m(self):
        """ef_construct should be >= 2*m for index quality (HNSW best practice)."""
        assert settings.qdrant_hnsw_ef_construct >= 2 * settings.qdrant_hnsw_m

    def test_ef_search_less_than_ef_construct(self):
        """Query-time ef should be <= ef_construct for valid HNSW operation."""
        assert settings.qdrant_hnsw_ef_default <= settings.qdrant_hnsw_ef_construct

    def test_m_in_valid_range(self):
        """m should be in valid HNSW range [4, 128]."""
        assert 4 <= settings.qdrant_hnsw_m <= 128

    def test_3072d_m_higher_than_1536d(self):
        """m for 3072d should be higher than 16 (1536d baseline).

        Higher dimensions create sparser graphs, requiring more connections
        (higher m) to maintain recall quality.
        """
        m_1536d = 16  # Sprint 19 value
        assert settings.qdrant_hnsw_m > m_1536d

    def test_3072d_ef_construct_higher_than_1536d(self):
        """ef_construct for 3072d should be higher than 100 (1536d baseline)."""
        ef_construct_1536d = 100  # Sprint 19 value
        assert settings.qdrant_hnsw_ef_construct > ef_construct_1536d
