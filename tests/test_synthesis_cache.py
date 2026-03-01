"""Tests for SynthesisCacheService."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.synthesis_cache import SynthesisCache
from app.services.synthesis_cache import SynthesisCacheService


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_session_factory(test_engine):
    """Create a session factory for the test engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def cache_service(test_session_factory):
    """Create a SynthesisCacheService with test database."""
    return SynthesisCacheService(session_factory=test_session_factory)


@pytest.fixture
def sample_chunk_ids():
    """Generate sample chunk UUIDs."""
    return [uuid4() for _ in range(3)]


@pytest.fixture
def sample_citations():
    """Generate sample citations."""
    return [
        {"chunk_id": str(uuid4()), "document_id": str(uuid4()), "excerpt": "Sample excerpt 1"},
        {"chunk_id": str(uuid4()), "document_id": str(uuid4()), "excerpt": "Sample excerpt 2"},
    ]


class TestComputeHash:
    """Tests for hash computation."""

    def test_compute_hash_basic(self, cache_service, sample_chunk_ids):
        """Test basic hash computation."""
        result = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
        )
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_compute_hash_deterministic(self, cache_service, sample_chunk_ids):
        """Test that hash is deterministic for same inputs."""
        hash1 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
        )
        assert hash1 == hash2

    def test_compute_hash_sorts_chunk_ids(self, cache_service):
        """Test that chunk IDs are sorted for consistent hashing."""
        id1, id2, id3 = uuid4(), uuid4(), uuid4()

        hash1 = cache_service.compute_hash(
            chunk_ids=[id1, id2, id3],
            prompt="test",
            output_format="summary",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=[id3, id1, id2],  # Different order
            prompt="test",
            output_format="summary",
        )
        assert hash1 == hash2

    def test_compute_hash_normalizes_prompt(self, cache_service, sample_chunk_ids):
        """Test that prompt is normalized (stripped and lowercased)."""
        hash1 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="  Test Prompt  ",
            output_format="markdown",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="test prompt",
            output_format="markdown",
        )
        assert hash1 == hash2

    def test_compute_hash_normalizes_format(self, cache_service, sample_chunk_ids):
        """Test that format is normalized to lowercase."""
        hash1 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="test",
            output_format="MARKDOWN",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="test",
            output_format="markdown",
        )
        assert hash1 == hash2

    def test_compute_hash_handles_none_prompt(self, cache_service, sample_chunk_ids):
        """Test that None prompt is handled correctly."""
        hash1 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt=None,
            output_format="markdown",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="",
            output_format="markdown",
        )
        assert hash1 == hash2

    def test_compute_hash_different_inputs_different_hashes(self, cache_service, sample_chunk_ids):
        """Test that different inputs produce different hashes."""
        hash1 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="prompt 1",
            output_format="markdown",
        )
        hash2 = cache_service.compute_hash(
            chunk_ids=sample_chunk_ids,
            prompt="prompt 2",
            output_format="markdown",
        )
        assert hash1 != hash2


class TestCacheSet:
    """Tests for cache set operation."""

    def test_set_creates_entry(
        self, cache_service, test_session_factory, sample_chunk_ids, sample_citations
    ):
        """Test that set creates a new cache entry."""
        cache_id = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
            content="Test content",
            citations=sample_citations,
            tokens_used=100,
            model_used="gpt-5.1",
        )

        assert cache_id is not None

        # Verify entry exists in DB
        session = test_session_factory()
        entry = session.query(SynthesisCache).filter(SynthesisCache.id == cache_id).one_or_none()
        session.close()

        assert entry is not None
        assert entry.content == "Test content"
        assert entry.tokens_used == 100
        assert entry.model_used == "gpt-5.1"
        assert entry.hit_count == 0

    def test_set_handles_concurrent_writes(
        self, cache_service, sample_chunk_ids, sample_citations
    ):
        """Test that concurrent writes are handled gracefully."""
        # First set
        cache_id1 = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
            content="Content 1",
            citations=sample_citations,
            tokens_used=100,
        )

        # Second set with same params - should return existing
        cache_id2 = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
            content="Content 2",  # Different content
            citations=sample_citations,
            tokens_used=200,
        )

        # Should return the same entry (first one wins)
        assert cache_id1 == cache_id2


class TestCacheGet:
    """Tests for cache get operation."""

    def test_get_returns_cached_result(
        self, cache_service, sample_chunk_ids, sample_citations
    ):
        """Test that get returns cached result and updates hit count."""
        # Set up cache entry
        cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
            content="Cached content",
            citations=sample_citations,
            tokens_used=150,
        )

        # Get from cache
        result = cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Test prompt",
            output_format="markdown",
        )

        assert result is not None
        assert result["content"] == "Cached content"
        assert result["citations"] == sample_citations
        assert result["tokens_used"] == 150
        assert result["cache_hit"] is True
        assert result["hit_count"] == 1

    def test_get_returns_none_on_miss(self, cache_service, sample_chunk_ids):
        """Test that get returns None on cache miss."""
        result = cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Uncached prompt",
            output_format="markdown",
        )
        assert result is None

    def test_get_increments_hit_count(
        self, cache_service, sample_chunk_ids, sample_citations
    ):
        """Test that each get increments hit count."""
        cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
            content="Content",
            citations=sample_citations,
            tokens_used=100,
        )

        # Multiple gets
        result1 = cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
        )
        result2 = cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
        )
        result3 = cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
        )

        assert result1["hit_count"] == 1
        assert result2["hit_count"] == 2
        assert result3["hit_count"] == 3

    def test_get_updates_last_hit_at(
        self, cache_service, test_session_factory, sample_chunk_ids, sample_citations
    ):
        """Test that get updates last_hit_at timestamp."""
        cache_id = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
            content="Content",
            citations=sample_citations,
            tokens_used=100,
        )

        # Verify last_hit_at is None initially
        session = test_session_factory()
        entry = session.query(SynthesisCache).filter(SynthesisCache.id == cache_id).one()
        initial_hit_at = entry.last_hit_at
        session.close()

        assert initial_hit_at is None

        # Get from cache
        cache_service.get(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
        )

        # Verify last_hit_at is now set
        session = test_session_factory()
        entry = session.query(SynthesisCache).filter(SynthesisCache.id == cache_id).one()
        session.close()

        assert entry.last_hit_at is not None


class TestRecordHit:
    """Tests for record_hit operation."""

    def test_record_hit_increments_count(
        self, cache_service, test_session_factory, sample_chunk_ids, sample_citations
    ):
        """Test that record_hit increments hit count."""
        cache_id = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
            content="Content",
            citations=sample_citations,
            tokens_used=100,
        )

        # Record hits
        cache_service.record_hit(cache_id=cache_id)
        cache_service.record_hit(cache_id=cache_id)

        # Verify count
        session = test_session_factory()
        entry = session.query(SynthesisCache).filter(SynthesisCache.id == cache_id).one()
        session.close()

        assert entry.hit_count == 2

    def test_record_hit_handles_missing_entry(self, cache_service):
        """Test that record_hit handles missing entry gracefully."""
        # Should not raise
        cache_service.record_hit(cache_id=str(uuid4()))


class TestGetStats:
    """Tests for get_stats operation."""

    def test_get_stats_empty_cache(self, cache_service):
        """Test stats for empty cache."""
        stats = cache_service.get_stats()

        assert stats["total_entries"] == 0
        assert stats["total_hits"] == 0
        assert stats["total_tokens_cached"] == 0
        assert stats["total_tokens_saved"] == 0
        assert stats["top_entries"] == []

    def test_get_stats_with_entries(
        self, cache_service, sample_citations
    ):
        """Test stats with cache entries."""
        # Add entries
        ids1 = [uuid4() for _ in range(3)]
        ids2 = [uuid4() for _ in range(3)]

        cache_service.set(
            chunk_ids=ids1,
            prompt="Prompt 1",
            output_format="markdown",
            content="Content 1",
            citations=sample_citations,
            tokens_used=100,
        )
        cache_service.set(
            chunk_ids=ids2,
            prompt="Prompt 2",
            output_format="summary",
            content="Content 2",
            citations=sample_citations,
            tokens_used=200,
        )

        # Add hits
        cache_service.get(chunk_ids=ids1, prompt="Prompt 1", output_format="markdown")
        cache_service.get(chunk_ids=ids1, prompt="Prompt 1", output_format="markdown")
        cache_service.get(chunk_ids=ids2, prompt="Prompt 2", output_format="summary")

        stats = cache_service.get_stats()

        assert stats["total_entries"] == 2
        assert stats["total_hits"] == 3
        assert stats["total_tokens_cached"] == 300
        # tokens_saved = 2 * 100 + 1 * 200 = 400
        assert stats["total_tokens_saved"] == 400
        assert len(stats["top_entries"]) == 2

    def test_get_stats_top_entries_ordered(
        self, cache_service, sample_citations
    ):
        """Test that top entries are ordered by hit count."""
        # Add entries with different hit counts
        ids1 = [uuid4() for _ in range(2)]
        ids2 = [uuid4() for _ in range(2)]
        ids3 = [uuid4() for _ in range(2)]

        cache_service.set(
            chunk_ids=ids1,
            prompt="P1",
            output_format="markdown",
            content="C1",
            citations=sample_citations,
            tokens_used=100,
        )
        cache_service.set(
            chunk_ids=ids2,
            prompt="P2",
            output_format="markdown",
            content="C2",
            citations=sample_citations,
            tokens_used=100,
        )
        cache_service.set(
            chunk_ids=ids3,
            prompt="P3",
            output_format="markdown",
            content="C3",
            citations=sample_citations,
            tokens_used=100,
        )

        # Create varying hit counts: ids2 = 5 hits, ids1 = 3 hits, ids3 = 1 hit
        for _ in range(5):
            cache_service.get(chunk_ids=ids2, prompt="P2", output_format="markdown")
        for _ in range(3):
            cache_service.get(chunk_ids=ids1, prompt="P1", output_format="markdown")
        cache_service.get(chunk_ids=ids3, prompt="P3", output_format="markdown")

        stats = cache_service.get_stats()
        top = stats["top_entries"]

        assert len(top) == 3
        assert top[0]["hit_count"] == 5
        assert top[1]["hit_count"] == 3
        assert top[2]["hit_count"] == 1


class TestInvalidate:
    """Tests for cache invalidation."""

    def test_invalidate_by_cache_id(
        self, cache_service, test_session_factory, sample_chunk_ids, sample_citations
    ):
        """Test invalidating a specific cache entry."""
        cache_id = cache_service.set(
            chunk_ids=sample_chunk_ids,
            prompt="Test",
            output_format="markdown",
            content="Content",
            citations=sample_citations,
            tokens_used=100,
        )

        count = cache_service.invalidate(cache_id=cache_id)

        assert count == 1

        # Verify entry is deleted
        session = test_session_factory()
        entry = session.query(SynthesisCache).filter(SynthesisCache.id == cache_id).one_or_none()
        session.close()

        assert entry is None

    def test_invalidate_missing_entry(self, cache_service):
        """Test invalidating non-existent entry."""
        count = cache_service.invalidate(cache_id=str(uuid4()))
        assert count == 0

    def test_invalidate_requires_param(self, cache_service):
        """Test that invalidate requires either cache_id or chunk_ids."""
        with pytest.raises(ValueError, match="Either cache_id or chunk_ids"):
            cache_service.invalidate()


class TestSynthesisServiceIntegration:
    """Integration tests with SynthesisService."""

    def test_synthesis_service_uses_cache(self, cache_service, sample_chunk_ids, sample_citations):
        """Test that SynthesisService integrates with cache."""
        from unittest.mock import MagicMock, patch

        # Mock the OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated content [1][2]"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150

        # Patch OpenAI and settings
        with patch("app.services.synthesis.OpenAI") as mock_openai_class, \
            patch("app.services.synthesis.settings") as mock_settings, \
             patch("app.services.synthesis._openai_import_error", None):

            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_chat_model = "gpt-5.1"

            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_class.return_value = mock_client

            from app.services.synthesis import SynthesisService

            # Create service with cache
            service = SynthesisService(
                client=mock_client,
                cache_service=cache_service,
                enable_cache=True,
            )

            # Note: This test would require database fixtures with actual chunks
            # For now, just verify the service can be created with cache enabled
            assert service.cache_service is cache_service
            assert service.enable_cache is True
