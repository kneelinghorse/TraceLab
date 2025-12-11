"""Tests for PEDR enhancements: include_embeddings and source_origin filtering (B21.7).

These tests verify:
1. include_embeddings parameter passes through to semantic search layer
2. source_origin filter is applied to Qdrant queries
3. Embedding vectors are returned when include_embeddings=True
4. Results include source_origin metadata from Qdrant payload
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from app.services.pedr.search_orchestrator import (
    PEDRSearchOrchestrator,
    PEDRSearchResult,
    PEDRSearchResponse,
    create_pedr_orchestrator,
)
from app.schemas.pedr_search import (
    PEDRSearchRequest,
    PEDRSearchResult as PEDRSearchResultSchema,
)


class TestPEDRSearchResultFields:
    """Tests for new fields in PEDRSearchResult dataclass."""

    def test_source_origin_field_exists(self):
        """PEDRSearchResult has source_origin field."""
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
            source_origin="synthesized",
        )
        assert result.source_origin == "synthesized"

    def test_embedding_field_exists(self):
        """PEDRSearchResult has embedding field."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
            embedding=embedding,
        )
        assert result.embedding == embedding

    def test_source_origin_defaults_to_none(self):
        """source_origin defaults to None when not provided."""
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
        )
        assert result.source_origin is None

    def test_embedding_defaults_to_none(self):
        """embedding defaults to None when not provided."""
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
        )
        assert result.embedding is None

    def test_to_dict_includes_source_origin(self):
        """to_dict() includes source_origin in output."""
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
            source_origin="upload",
        )
        result_dict = result.to_dict()
        assert "source_origin" in result_dict
        assert result_dict["source_origin"] == "upload"

    def test_to_dict_includes_embedding_when_present(self):
        """to_dict() includes embedding when it has a value."""
        embedding = [0.1, 0.2, 0.3]
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
            embedding=embedding,
        )
        result_dict = result.to_dict()
        assert "embedding" in result_dict
        assert result_dict["embedding"] == embedding

    def test_to_dict_omits_embedding_when_none(self):
        """to_dict() omits embedding when it is None."""
        result = PEDRSearchResult(
            chunk_id="test-123",
            content="test content",
            embedding=None,
        )
        result_dict = result.to_dict()
        assert "embedding" not in result_dict


class TestPEDRSearchRequestSchema:
    """Tests for new fields in PEDRSearchRequest schema."""

    def test_source_origin_field_exists(self):
        """PEDRSearchRequest has source_origin field."""
        request = PEDRSearchRequest(
            query="test query",
            source_origin="synthesized",
        )
        assert request.source_origin == "synthesized"

    def test_include_embeddings_field_exists(self):
        """PEDRSearchRequest has include_embeddings field."""
        request = PEDRSearchRequest(
            query="test query",
            include_embeddings=True,
        )
        assert request.include_embeddings is True

    def test_source_origin_defaults_to_none(self):
        """source_origin defaults to None."""
        request = PEDRSearchRequest(query="test query")
        assert request.source_origin is None

    def test_include_embeddings_defaults_to_false(self):
        """include_embeddings defaults to False."""
        request = PEDRSearchRequest(query="test query")
        assert request.include_embeddings is False


class TestPEDRSearchResultSchemaFields:
    """Tests for new fields in PEDRSearchResult Pydantic schema."""

    def test_source_origin_field_exists(self):
        """PEDRSearchResult schema has source_origin field."""
        result = PEDRSearchResultSchema(
            chunk_id="test-123",
            content="test content",
            rrf_score=0.5,
            rrf_rank=1,
            source_origin="imported",
        )
        assert result.source_origin == "imported"

    def test_embedding_field_exists(self):
        """PEDRSearchResult schema has embedding field."""
        embedding = [0.1, 0.2, 0.3]
        result = PEDRSearchResultSchema(
            chunk_id="test-123",
            content="test content",
            rrf_score=0.5,
            rrf_rank=1,
            embedding=embedding,
        )
        assert result.embedding == embedding

    def test_fields_default_to_none(self):
        """source_origin and embedding default to None."""
        result = PEDRSearchResultSchema(
            chunk_id="test-123",
            content="test content",
            rrf_score=0.5,
            rrf_rank=1,
        )
        assert result.source_origin is None
        assert result.embedding is None


class TestPEDRSearchOrchestratorParameters:
    """Tests for new parameters in PEDRSearchOrchestrator.search()."""

    def test_search_accepts_source_origin_parameter(self):
        """search() accepts source_origin parameter."""
        orchestrator = PEDRSearchOrchestrator()
        # Should not raise - just testing parameter acceptance
        # We're not executing the full search since services aren't wired up
        import inspect
        sig = inspect.signature(orchestrator.search)
        params = list(sig.parameters.keys())
        assert "source_origin" in params

    def test_search_accepts_include_embeddings_parameter(self):
        """search() accepts include_embeddings parameter."""
        orchestrator = PEDRSearchOrchestrator()
        import inspect
        sig = inspect.signature(orchestrator.search)
        params = list(sig.parameters.keys())
        assert "include_embeddings" in params


class TestSourceOriginPassthrough:
    """Tests for source_origin filter being passed through the search stack."""

    def test_source_origin_in_search_params_dict(self):
        """search() includes source_origin in search_params passed to layers."""
        # Create mock semantic search function to capture arguments
        captured_kwargs = {}

        def mock_semantic_search(**kwargs):
            captured_kwargs.update(kwargs)
            return []

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        orchestrator.search(
            query="test query",
            source_origin="synthesized",
        )

        assert "source_origin" in captured_kwargs
        assert captured_kwargs["source_origin"] == "synthesized"

    def test_source_origin_none_by_default_in_search_params(self):
        """source_origin is None by default in search_params."""
        captured_kwargs = {}

        def mock_semantic_search(**kwargs):
            captured_kwargs.update(kwargs)
            return []

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        orchestrator.search(query="test query")

        assert captured_kwargs.get("source_origin") is None


class TestIncludeEmbeddingsPassthrough:
    """Tests for include_embeddings parameter being passed through."""

    def test_include_embeddings_in_search_params_dict(self):
        """search() includes include_embeddings in search_params passed to layers."""
        captured_kwargs = {}

        def mock_semantic_search(**kwargs):
            captured_kwargs.update(kwargs)
            return []

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        orchestrator.search(
            query="test query",
            include_embeddings=True,
        )

        assert "include_embeddings" in captured_kwargs
        assert captured_kwargs["include_embeddings"] is True

    def test_include_embeddings_false_by_default_in_search_params(self):
        """include_embeddings is False by default in search_params."""
        captured_kwargs = {}

        def mock_semantic_search(**kwargs):
            captured_kwargs.update(kwargs)
            return []

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        orchestrator.search(query="test query")

        assert captured_kwargs.get("include_embeddings") is False


class TestEmbeddingInResults:
    """Tests for embedding vectors appearing in results."""

    def test_embedding_passed_through_finalize_results(self):
        """Embedding from semantic results is passed through to final results."""

        def mock_semantic_search(**kwargs):
            return [
                {
                    "chunk_id": "chunk-1",
                    "content": "test content",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "score": 0.9,
                    "source_origin": "upload",
                    "embedding": [0.1, 0.2, 0.3],
                }
            ]

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        response = orchestrator.search(
            query="test query",
            include_embeddings=True,
        )

        assert len(response.results) == 1
        result = response.results[0]
        assert result.embedding == [0.1, 0.2, 0.3]
        assert result.source_origin == "upload"


class TestSourceOriginInResults:
    """Tests for source_origin appearing in results."""

    def test_source_origin_passed_through_from_semantic_results(self):
        """source_origin from semantic results is passed through to final results."""

        def mock_semantic_search(**kwargs):
            return [
                {
                    "chunk_id": "chunk-1",
                    "content": "synthesized content",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "score": 0.9,
                    "source_origin": "synthesized",
                }
            ]

        orchestrator = PEDRSearchOrchestrator(
            lexical_search=lambda **kw: [],
            semantic_search=mock_semantic_search,
        )
        response = orchestrator.search(query="test query")

        assert len(response.results) == 1
        result = response.results[0]
        assert result.source_origin == "synthesized"


class TestCacheKeyIncludesNewParams:
    """Tests for cache key including new parameters."""

    def test_cache_filters_include_source_origin(self):
        """Cache filters include source_origin and include_embeddings."""
        # This test verifies the cache key includes source_origin
        # by checking the cache_filters dict in the search method
        captured_cache_filters = {}

        with patch("app.services.pedr.search_orchestrator.get_pedr_cache") as mock_cache:
            # Set up mock to capture the filters passed to cache.get()
            def capture_get(query, top_k, filters, *args, **kwargs):
                captured_cache_filters.update(filters)
                return None  # Cache miss

            mock_cache.return_value.get.side_effect = capture_get
            mock_cache.return_value.get_stats.return_value.to_dict.return_value = {}

            orchestrator = PEDRSearchOrchestrator(
                lexical_search=lambda **kw: [],
                semantic_search=lambda **kw: [],
            )
            orchestrator.search(
                query="test query",
                source_origin="synthesized",
                include_embeddings=True,
            )

            # Verify cache filters included new params
            assert captured_cache_filters.get("source_origin") == "synthesized"
            assert captured_cache_filters.get("include_embeddings") is True
