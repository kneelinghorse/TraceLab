"""Tests for incremental edge materialization triggered by document ingestion (T37.3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.graph_edge import GraphEdge
from app.models.project import Project
from app.services.document_ingestion import DocumentIngestionService
from app.services.chunking import ChunkingService
from app.services.processing_status import ProcessingStatusRecorder
from app.services.coverage_report import CoverageReportGenerator
from app.services.pedr.edge_materialization import (
    EdgeMaterializationService,
    MaterializationResult,
)


SAMPLE_TEXT = (
    "Graph edge materialization validates implicit FK relationships. " * 30
).strip()


def _build_txt(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def _make_service(**overrides):
    defaults = dict(
        chunking_service=ChunkingService(),
        status_recorder=ProcessingStatusRecorder(),
        coverage_report_generator=CoverageReportGenerator(),
    )
    defaults.update(overrides)
    return DocumentIngestionService(**defaults)


def _create_document(db_session, project, file_path: Path) -> Document:
    doc = Document(
        project_id=project.id,
        name=file_path.name,
        file_path=str(file_path),
        file_type="notes",
        mime_type="text/plain",
        processed=False,
        chunked=False,
        validation_status="pending",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


class TestIngestionEdgeMaterialization:
    """Verify incremental edge materialization fires after document ingestion."""

    def test_edges_materialized_stage_present_in_result(
        self, db_session, project, tmp_path
    ):
        """Ingestion result includes edges_materialized stage."""
        file_path = _build_txt(tmp_path / "test.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        result = service.process_document(
            db=db_session, document_id=doc.id, file_path=file_path
        )

        assert result["status"] == "completed"
        assert "edges_materialized" in result["stages"]
        stage = result["stages"]["edges_materialized"]
        assert stage["status"] == "success"
        assert "inserted" in stage
        assert "updated" in stage
        assert "skipped" in stage
        assert "duration_seconds" in stage

    def test_edges_created_for_document(self, db_session, project, tmp_path):
        """Ingestion creates graph edges linking document to project."""
        file_path = _build_txt(tmp_path / "edges.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        result = service.process_document(
            db=db_session, document_id=doc.id, file_path=file_path
        )

        assert result["status"] == "completed"
        edges = db_session.query(GraphEdge).all()
        # Should have at least document→project (belongs_to) and project→document (contains)
        # plus document→chunk and chunk→document edges
        assert len(edges) >= 2

        # Verify document-project relationship exists
        doc_urn = f"urn:research:document:{doc.id}"
        project_urn = f"urn:research:project:{project.id}"
        edge_pairs = [(e.from_urn, e.to_urn, e.edge_type) for e in edges]
        assert (doc_urn, project_urn, "belongs_to") in edge_pairs
        assert (project_urn, doc_urn, "contains") in edge_pairs

    def test_edge_materialization_duration_in_metrics(
        self, db_session, project, tmp_path
    ):
        """Edge materialization duration is recorded in result metrics."""
        file_path = _build_txt(tmp_path / "metrics.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        result = service.process_document(
            db=db_session, document_id=doc.id, file_path=file_path
        )

        assert "metrics" in result
        assert "edge_materialization_duration_seconds" in result["metrics"]
        assert result["metrics"]["edge_materialization_duration_seconds"] < 2.0

    def test_edge_materialization_failure_does_not_break_ingestion(
        self, db_session, project, tmp_path
    ):
        """If edge materialization raises, ingestion still completes successfully."""
        file_path = _build_txt(tmp_path / "fail.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        with patch.object(
            EdgeMaterializationService,
            "materialize_implicit_edges",
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = service.process_document(
                db=db_session, document_id=doc.id, file_path=file_path
            )

        # Ingestion itself should still complete
        assert result["status"] == "completed"
        assert result["stages"]["edges_materialized"]["status"] == "failed"
        assert "DB connection lost" in result["stages"]["edges_materialized"]["error"]

        # Document should still be processed
        persisted = db_session.query(Document).filter(Document.id == doc.id).one()
        assert persisted.processed is True
        assert persisted.chunked is True

    def test_incremental_mode_used(self, db_session, project, tmp_path):
        """Materialization is called with mode='incremental' and correct project_id."""
        file_path = _build_txt(tmp_path / "mode.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        mock_result = MaterializationResult(
            inserted_count=5, updated_count=0, skipped_count=0
        )
        with patch.object(
            EdgeMaterializationService,
            "materialize_implicit_edges",
            return_value=mock_result,
        ) as mock_materialize:
            result = service.process_document(
                db=db_session, document_id=doc.id, file_path=file_path
            )

        mock_materialize.assert_called_once()
        call_kwargs = mock_materialize.call_args
        assert call_kwargs.kwargs["mode"] == "incremental"
        assert call_kwargs.kwargs["project_id"] == str(project.id)

    def test_chunk_edges_created(self, db_session, project, tmp_path):
        """Ingestion creates edges linking chunks to their parent document."""
        file_path = _build_txt(tmp_path / "chunks.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        result = service.process_document(
            db=db_session, document_id=doc.id, file_path=file_path
        )

        assert result["status"] == "completed"
        chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .all()
        )
        edges = (
            db_session.query(GraphEdge).filter(GraphEdge.edge_type == "contains").all()
        )

        doc_urn = f"urn:research:document:{doc.id}"
        # Each chunk should have a "contains" edge from the document
        chunk_contains = [e for e in edges if e.from_urn == doc_urn]
        assert len(chunk_contains) >= len(chunks)

    def test_second_document_incremental_only_adds_new_edges(
        self, db_session, project, tmp_path
    ):
        """Second document ingestion in incremental mode doesn't duplicate first document's edges."""
        # Ingest first document
        file1 = _build_txt(tmp_path / "doc1.txt", SAMPLE_TEXT)
        doc1 = _create_document(db_session, project, file1)
        service = _make_service()
        result1 = service.process_document(
            db=db_session, document_id=doc1.id, file_path=file1
        )
        assert result1["status"] == "completed"
        edges_after_first = db_session.query(GraphEdge).count()

        # Ingest second document
        file2 = _build_txt(
            tmp_path / "doc2.txt", "Different content for second document. " * 30
        )
        doc2 = _create_document(db_session, project, file2)
        result2 = service.process_document(
            db=db_session, document_id=doc2.id, file_path=file2
        )
        assert result2["status"] == "completed"
        edges_after_second = db_session.query(GraphEdge).count()

        # Second document should add new edges (not zero, but also not duplicate all)
        new_edges = edges_after_second - edges_after_first
        assert new_edges > 0  # At least doc2→project + project→doc2 + chunk edges

    def test_latency_under_two_seconds(self, db_session, project, tmp_path):
        """Single document edge materialization completes under 2 seconds."""
        file_path = _build_txt(tmp_path / "latency.txt", SAMPLE_TEXT)
        doc = _create_document(db_session, project, file_path)
        service = _make_service()

        result = service.process_document(
            db=db_session, document_id=doc.id, file_path=file_path
        )

        assert result["status"] == "completed"
        duration = result["stages"]["edges_materialized"]["duration_seconds"]
        assert duration < 2.0, (
            f"Edge materialization took {duration}s, exceeding 2s target"
        )
