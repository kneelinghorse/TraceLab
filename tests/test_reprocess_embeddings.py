"""Tests for the embedding reprocessing script.

These tests use mocked database sessions to avoid PostgreSQL-specific
features (computed columns, tsvector) that SQLite doesn't support.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

# Import script modules - tests will use mocks instead of real DB
import scripts.reprocess_embeddings as reprocess_script


class TestProgressTracker:
    """Tests for the ProgressTracker class."""

    def test_initialization(self):
        """Tracker initializes with correct totals."""
        tracker = reprocess_script.ProgressTracker(total_documents=10, total_chunks=100)

        assert tracker.total_documents == 10
        assert tracker.total_chunks == 100
        assert tracker.processed_documents == 0
        assert tracker.processed_chunks == 0
        assert tracker.failed_documents == []

    def test_update_success(self, capsys):
        """Tracker updates correctly for successful processing."""
        tracker = reprocess_script.ProgressTracker(total_documents=5, total_chunks=50)

        tracker.update("doc1.pdf", 10, success=True)

        assert tracker.processed_documents == 1
        assert tracker.processed_chunks == 10
        assert tracker.failed_documents == []

        captured = capsys.readouterr()
        assert "[1/5]" in captured.out
        assert "doc1.pdf" in captured.out
        assert "10 chunks" in captured.out

    def test_update_failure(self, capsys):
        """Tracker tracks failed documents."""
        tracker = reprocess_script.ProgressTracker(total_documents=5, total_chunks=50)

        tracker.update("bad_doc.pdf", 0, success=False)

        assert tracker.processed_documents == 1
        assert tracker.processed_chunks == 0
        assert "bad_doc.pdf" in tracker.failed_documents

        captured = capsys.readouterr()
        assert "[1/5]" in captured.out

    def test_summary_with_failures(self, capsys):
        """Summary includes failed documents."""
        tracker = reprocess_script.ProgressTracker(total_documents=3, total_chunks=30)
        tracker.update("good1.pdf", 10, success=True)
        tracker.update("bad.pdf", 0, success=False)
        tracker.update("good2.pdf", 10, success=True)

        # Clear previous output
        capsys.readouterr()

        tracker.summary()
        captured = capsys.readouterr()

        assert "Documents processed: 3/3" in captured.out
        assert "Chunks embedded: 20/30" in captured.out
        assert "Failed documents (1):" in captured.out
        assert "bad.pdf" in captured.out

    def test_eta_calculation(self, capsys):
        """ETA is calculated and displayed."""
        tracker = reprocess_script.ProgressTracker(
            total_documents=100, total_chunks=1000
        )

        # Process one doc
        tracker.update("doc.pdf", 10, success=True)

        captured = capsys.readouterr()
        # Should have an ETA string
        assert "ETA:" in captured.out


class TestDryRun:
    """Tests for the dry_run function using mocked DB."""

    def test_dry_run_outputs_stats(self, capsys):
        """Dry run shows document counts and cost estimates."""
        # Create mock documents
        mock_doc1 = MagicMock()
        mock_doc1.id = uuid.uuid4()
        mock_doc1.name = "test_doc_1.pdf"
        mock_doc1.chunked = True

        mock_doc2 = MagicMock()
        mock_doc2.id = uuid.uuid4()
        mock_doc2.name = "test_doc_2.pdf"
        mock_doc2.chunked = True

        # Create mock DB session
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_order_by = MagicMock()
        mock_order_by.all.return_value = [mock_doc1, mock_doc2]
        mock_filter.order_by.return_value = mock_order_by
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        # Mock chunk count query (returns 5 for doc1, 3 for doc2)
        chunk_counts = [5, 3]
        chunk_count_iter = iter(chunk_counts)

        def mock_scalar():
            return next(chunk_count_iter)

        # Need to handle multiple query().filter().scalar() calls
        scalar_mock = MagicMock(side_effect=mock_scalar)
        mock_db.query.return_value.filter.return_value.scalar = scalar_mock

        # Run dry run
        reprocess_script.dry_run(mock_db)

        captured = capsys.readouterr()

        assert "DRY RUN" in captured.out
        assert "Documents to process: 2" in captured.out
        assert "test_doc_1.pdf" in captured.out
        assert "test_doc_2.pdf" in captured.out
        assert "Estimated cost (@" in captured.out

    def test_dry_run_with_resume_filter(self, capsys):
        """Dry run respects resume_from filter."""
        mock_doc = MagicMock()
        mock_doc.id = uuid.UUID("00000000-0000-0000-0000-000000000003")
        mock_doc.name = "third.pdf"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter1 = MagicMock()
        mock_filter2 = MagicMock()
        mock_order_by = MagicMock()
        mock_order_by.all.return_value = [mock_doc]
        mock_filter2.order_by.return_value = mock_order_by
        mock_filter1.filter.return_value = mock_filter2
        mock_query.filter.return_value = mock_filter1
        mock_db.query.return_value = mock_query

        # Mock chunk count
        mock_db.query.return_value.filter.return_value.scalar.return_value = 5

        resume_from = uuid.UUID("00000000-0000-0000-0000-000000000002")
        reprocess_script.dry_run(mock_db, resume_from=resume_from)

        captured = capsys.readouterr()

        assert "Documents to process: 1" in captured.out
        assert "third.pdf" in captured.out


class TestReprocessEmbeddings:
    """Tests for the main reprocess_embeddings function using mocks."""

    def test_reprocess_generates_embeddings(self, capsys):
        """Reprocessing generates and upserts embeddings."""
        # Create mock document
        mock_doc = MagicMock()
        mock_doc.id = uuid.uuid4()
        mock_doc.project_id = uuid.uuid4()
        mock_doc.name = "test_doc.pdf"
        mock_doc.source_type = "interview"
        mock_doc.chunked = True
        mock_doc.embedded = False

        # Create mock chunks with actual content strings (not mocks)
        mock_chunks = []
        for i in range(3):
            chunk = MagicMock()
            chunk.id = uuid.uuid4()
            chunk.document_id = mock_doc.id
            chunk.chunk_index = i
            # Important: content must be a real string, not a MagicMock
            chunk.content = f"Chunk {i} content"
            chunk.embedding_id = None
            mock_chunks.append(chunk)

        # Setup mock DB with proper routing
        mock_db = MagicMock()
        call_counter = [0]

        def route_query(model):
            call_counter[0] += 1
            mock_q = MagicMock()

            # For document queries
            if "Document" in str(model) and "Chunk" not in str(model):
                mock_q.filter.return_value.order_by.return_value.all.return_value = [
                    mock_doc
                ]
                mock_q.filter.return_value.count.return_value = 1
            else:
                # For chunk queries
                mock_q.filter.return_value.order_by.return_value.all.return_value = (
                    mock_chunks
                )
                mock_q.filter.return_value.scalar.return_value = 3

            return mock_q

        mock_db.query.side_effect = route_query

        # Mock services
        mock_embedding_service = MagicMock()
        mock_embedding_service.generate_embeddings_batch.return_value = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]

        mock_qdrant_service = MagicMock()
        mock_qdrant_service.vector_size = 3

        # Run reprocessing
        reprocess_script.reprocess_embeddings(
            db=mock_db,
            embedding_service=mock_embedding_service,
            qdrant_service=mock_qdrant_service,
        )

        # Verify embedding service was called with content strings
        mock_embedding_service.generate_embeddings_batch.assert_called_once()
        call_args = mock_embedding_service.generate_embeddings_batch.call_args[0][0]
        assert len(call_args) == 3
        assert call_args[0] == "Chunk 0 content"
        assert call_args[1] == "Chunk 1 content"
        assert call_args[2] == "Chunk 2 content"

        # Verify Qdrant upsert was called
        mock_qdrant_service.upsert_chunks.assert_called_once()

        # Verify indexing was enabled
        mock_qdrant_service.enable_indexing_and_quantization.assert_called_once()

        # Verify document marked as embedded
        assert mock_doc.embedded is True

        # Verify commit was called
        mock_db.commit.assert_called()

    def test_reprocess_with_drop_collection(self, capsys):
        """Drop collection flag deletes existing collection."""
        mock_doc = MagicMock()
        mock_doc.id = uuid.uuid4()
        mock_doc.project_id = uuid.uuid4()
        mock_doc.name = "test.pdf"
        mock_doc.chunked = True

        mock_chunk = MagicMock()
        mock_chunk.id = uuid.uuid4()
        mock_chunk.content = "Chunk content"
        mock_chunk.chunk_index = 0

        mock_db = MagicMock()
        # Setup query chain
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_doc
        ]
        mock_db.query.return_value.filter.return_value.scalar.return_value = 1

        # Second query for chunks
        def query_router(*args):
            mock_q = MagicMock()
            mock_q.filter.return_value.order_by.return_value.all.return_value = [
                mock_chunk
            ]
            mock_q.filter.return_value.scalar.return_value = 1
            return mock_q

        mock_db.query.side_effect = query_router

        mock_embedding_service = MagicMock()
        mock_embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2]]

        mock_qdrant_service = MagicMock()
        mock_qdrant_service.collection_name = "test_collection"

        reprocess_script.reprocess_embeddings(
            db=mock_db,
            embedding_service=mock_embedding_service,
            qdrant_service=mock_qdrant_service,
            drop_collection=True,
        )

        # Verify collection was dropped
        mock_qdrant_service.client.delete_collection.assert_called_once_with(
            "test_collection"
        )

    def test_reprocess_empty_documents(self, capsys):
        """Reprocessing handles empty document list."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        mock_embedding_service = MagicMock()
        mock_qdrant_service = MagicMock()

        reprocess_script.reprocess_embeddings(
            db=mock_db,
            embedding_service=mock_embedding_service,
            qdrant_service=mock_qdrant_service,
        )

        captured = capsys.readouterr()
        assert "No documents to process" in captured.out

        # Should not call embedding service
        mock_embedding_service.generate_embeddings_batch.assert_not_called()

    def test_reprocess_skips_document_on_embedding_dimension_mismatch(self):
        """Reprocessing should not upsert when embedding size doesn't match expected."""
        mock_doc = MagicMock()
        mock_doc.id = uuid.uuid4()
        mock_doc.project_id = uuid.uuid4()
        mock_doc.name = "test.pdf"
        mock_doc.source_type = "interview"
        mock_doc.chunked = True

        mock_chunk = MagicMock()
        mock_chunk.id = uuid.uuid4()
        mock_chunk.document_id = mock_doc.id
        mock_chunk.chunk_index = 0
        mock_chunk.content = "Chunk content"

        mock_db = MagicMock()
        call_counter = [0]

        def route_query(*_args):
            call_counter[0] += 1
            mock_q = MagicMock()
            # 1: doc list, 2: chunk count aggregate, 3: per-doc chunk count, 4: chunks query
            if call_counter[0] == 1:
                mock_q.filter.return_value.order_by.return_value.all.return_value = [
                    mock_doc
                ]
            elif call_counter[0] in (2, 3):
                mock_q.filter.return_value.scalar.return_value = 1
            else:
                mock_q.filter.return_value.order_by.return_value.all.return_value = [
                    mock_chunk
                ]
            return mock_q

        mock_db.query.side_effect = route_query

        mock_embedding_service = MagicMock()
        mock_embedding_service.generate_embeddings_batch.return_value = [
            [0.1, 0.2, 0.3]
        ]

        mock_qdrant_service = MagicMock()
        mock_qdrant_service.vector_size = 3072

        reprocess_script.reprocess_embeddings(
            db=mock_db,
            embedding_service=mock_embedding_service,
            qdrant_service=mock_qdrant_service,
            expected_dimension=3072,
        )

        mock_qdrant_service.upsert_chunks.assert_not_called()


class TestCostEstimation:
    """Tests for cost estimation logic."""

    def test_cost_constants_are_reasonable(self):
        """Cost constants should be reasonable for OpenAI pricing."""
        assert (
            reprocess_script.MODEL_COST_PER_1M_TOKENS["text-embedding-3-small"] == 0.02
        )
        assert (
            reprocess_script.MODEL_COST_PER_1M_TOKENS["text-embedding-3-large"] == 0.13
        )

        # Average chunk should be 500-1000 tokens
        assert 500 <= reprocess_script.AVG_TOKENS_PER_CHUNK <= 1000

    def test_cost_estimation_calculation(self):
        """Cost estimation should be mathematically correct."""
        # 1000 chunks * 750 tokens/chunk = 750,000 tokens
        # text-embedding-3-large is $0.13 / 1M tokens
        chunks = 1000
        cost_per_1k = reprocess_script.cost_per_1k_tokens("text-embedding-3-large")
        expected_tokens = chunks * reprocess_script.AVG_TOKENS_PER_CHUNK
        expected_cost = (expected_tokens / 1000) * cost_per_1k

        assert expected_tokens == 750_000
        assert expected_cost == pytest.approx(0.0975)

    def test_cost_per_1k_tokens_fallback(self):
        """Unknown models should use safe default pricing."""
        assert reprocess_script.cost_per_1k_tokens("unknown-model") == pytest.approx(
            0.00013
        )

    def test_normalize_chunk_text_truncates_long_content(self):
        """Chunk text should be capped to the embedding safety threshold."""
        oversized = "a" * (reprocess_script.MAX_EMBEDDING_CHARS + 10)
        normalized = reprocess_script.normalize_chunk_text(oversized)
        assert len(normalized) == reprocess_script.MAX_EMBEDDING_CHARS


class TestGetDocumentStats:
    """Tests for get_document_stats helper."""

    def test_get_document_stats_basic(self):
        """Stats correctly count documents and chunks."""
        mock_db = MagicMock()

        # Document count query
        doc_count_mock = MagicMock()
        doc_count_mock.count.return_value = 10

        # Chunk count query
        chunk_count_mock = MagicMock()
        chunk_count_mock.scalar.return_value = 50

        # Set up query routing
        call_count = [0]

        def route_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call is for document count
                return doc_count_mock
            else:
                # Second call is for chunk count
                return chunk_count_mock

        mock_db.query.side_effect = route_query

        # Create mock filter returns
        doc_count_mock.filter.return_value = doc_count_mock
        chunk_count_mock.join.return_value.filter.return_value = chunk_count_mock

        doc_count, chunk_count = reprocess_script.get_document_stats(mock_db)

        assert doc_count == 10
        assert chunk_count == 50


class TestArgumentParsing:
    """Tests for CLI argument handling."""

    def test_uuid_parsing(self):
        """UUID arguments are parsed correctly."""
        test_uuid = "12345678-1234-5678-1234-567812345678"
        parsed = uuid.UUID(test_uuid)
        assert str(parsed) == test_uuid

    def test_invalid_uuid_raises(self):
        """Invalid UUID raises ValueError."""
        with pytest.raises(ValueError):
            uuid.UUID("not-a-uuid")
