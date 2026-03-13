"""Tests for embedding and Qdrant integration inside the ingestion pipeline."""

from __future__ import annotations

from pathlib import Path

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.processing_status import (
    DocumentProcessingStatus as ProcessingStatusModel,
)
from app.services.chunking import Chunk
from app.services.document_ingestion import DocumentIngestionService
from app.services.processing_status import ProcessingStatusRecorder


class StubChunkingService:
    """Deterministic chunking stub."""

    def __init__(self, chunk_count: int = 1):
        self.chunk_count = chunk_count
        self.calls = 0

    def chunk_document(self, text: str) -> list[Chunk]:
        self.calls += 1
        chunks: list[Chunk] = []
        for index in range(self.chunk_count):
            chunks.append(
                Chunk(
                    content=f"{text} [chunk-{index}]",
                    chunk_index=index,
                    start_char=index * 10,
                    end_char=index * 10 + len(text),
                    token_count=600,
                )
            )
        return chunks


class StubEmbeddingService:
    """Records batch requests and returns predictable vectors."""

    def __init__(self):
        self.batches: list[list[str]] = []

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[float(idx), float(idx) + 0.5] for idx, _ in enumerate(texts)]


class StubQdrantService:
    """Captures ensure/upsert interactions."""

    def __init__(self, *, fail_upsert: bool = False):
        self.collection_name = "research_chunks"
        self.ensure_calls: list[bool] = []
        self.upserts: list[list[dict]] = []
        self.fail_upsert = fail_upsert

    def ensure_collection(self, write_optimized: bool = False) -> None:
        self.ensure_calls.append(write_optimized)

    def upsert_chunks(self, payload: list[dict]) -> None:
        if self.fail_upsert:
            raise RuntimeError("simulated qdrant failure")
        self.upserts.append(payload)


class StubCoverageReport:
    """Avoids touching filesystem for coverage artifacts."""

    def __init__(self):
        self.calls = 0

    def generate_report(self, db):
        self.calls += 1
        return {"calls": self.calls}


def _create_document(db_session, project, file_path: Path) -> Document:
    document = Document(
        project_id=project.id,
        name=file_path.name,
        file_path=str(file_path),
        file_type="notes",
        mime_type="text/markdown",
        processed=False,
        chunked=False,
        embedded=False,
        validation_status="pending",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _service(embedding_service, qdrant_service, chunking_service=None):
    return DocumentIngestionService(
        chunking_service=chunking_service or StubChunkingService(),
        status_recorder=ProcessingStatusRecorder(),
        coverage_report_generator=StubCoverageReport(),
        redaction_service=None,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
    )


def test_embedding_stage_upserts_vectors_and_sets_metrics(
    db_session, project, tmp_path
):
    """End-to-end happy path: embeddings flow into Qdrant and metrics are recorded."""
    file_path = tmp_path / "embedding.md"
    file_path.write_text("TraceLab embedding pipeline smoke test.")
    document = _create_document(db_session, project, file_path)

    embedding = StubEmbeddingService()
    qdrant = StubQdrantService()
    chunking = StubChunkingService()

    service = _service(embedding, qdrant, chunking)
    result = service.process_document(db_session, document.id, file_path=file_path)

    assert result["status"] == "completed"
    embedded_stage = result["stages"]["embedded"]
    assert embedded_stage["status"] == "success"
    assert embedded_stage["chunks_embedded"] == 1
    assert embedded_stage["collection"] == qdrant.collection_name
    assert embedded_stage["duration_seconds"] >= 0
    assert result["metrics"]["embedding_duration_seconds"] >= 0

    assert qdrant.ensure_calls == [False]
    assert len(qdrant.upserts) == 1
    payload = qdrant.upserts[0][0]
    assert payload["document_id"] == document.id
    assert payload["chunk_index"] == 0

    persisted_doc = db_session.query(Document).filter(Document.id == document.id).one()
    assert persisted_doc.embedded is True

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .all()
    )
    assert len(chunks) == 1
    assert chunks[0].embedding_id == str(chunks[0].id)

    statuses = (
        db_session.query(ProcessingStatusModel)
        .filter(
            ProcessingStatusModel.document_id == document.id,
            ProcessingStatusModel.stage == "embedded",
        )
        .all()
    )
    status_values = {entry.status for entry in statuses}
    assert status_values == {"in_progress", "succeeded"}


def test_embedding_stage_records_failure_without_corrupting_document(
    db_session, project, tmp_path
):
    """Qdrant failures should surface cleanly while leaving document state coherent."""
    file_path = tmp_path / "embedding.md"
    file_path.write_text("Failure path test.")
    document = _create_document(db_session, project, file_path)

    embedding = StubEmbeddingService()
    qdrant = StubQdrantService(fail_upsert=True)

    service = _service(embedding, qdrant)
    result = service.process_document(db_session, document.id, file_path=file_path)

    assert result["status"] == "failed"
    assert result["stages"]["embedded"]["status"] == "failed"
    assert "simulated qdrant failure" in result["error"]

    refreshed = db_session.query(Document).filter(Document.id == document.id).one()
    assert refreshed.embedded is False
    assert refreshed.validation_status == "flagged"

    statuses = (
        db_session.query(ProcessingStatusModel)
        .filter(
            ProcessingStatusModel.document_id == document.id,
            ProcessingStatusModel.stage == "embedded",
        )
        .all()
    )
    status_pairs = {(status.status, status.message) for status in statuses}
    assert (
        "in_progress",
        "Generating embeddings and upserting to Qdrant",
    ) in status_pairs
    assert any(status.status == "failed" for status in statuses)
