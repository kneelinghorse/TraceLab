"""
Document ingestion service.

Orchestrates the complete ingestion pipeline: parsing, redaction, chunking, and persistence.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.document_parser import DocumentParser
from app.services.chunking import ChunkingService
from app.services.processing_status import ProcessingStatusRecorder
from app.services.coverage_report import CoverageReportGenerator
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.qdrant_service import QdrantService, get_qdrant_service
from app.models.document import Document
from app.models.chunk import DocumentChunk

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    """Service for ingesting documents through the complete pipeline."""
    
    def __init__(
        self,
        chunking_service: Optional[ChunkingService] = None,
        status_recorder: Optional[ProcessingStatusRecorder] = None,
        coverage_report_generator: Optional[CoverageReportGenerator] = None,
        redaction_service: Optional[Any] = None,
        embedding_service: Optional[EmbeddingService] = None,
        qdrant_service: Optional[QdrantService] = None,
    ):
        """
        Initialize ingestion service.
        
        Args:
            chunking_service: Optional ChunkingService instance
            status_recorder: Optional recorder for status audit trail
            coverage_report_generator: Optional coverage report generator
        """
        self.parser = DocumentParser()
        self.chunking_service = chunking_service or ChunkingService()
        self.status_recorder = status_recorder or ProcessingStatusRecorder()
        self.coverage_report_generator = coverage_report_generator or CoverageReportGenerator()
        self.embedding_service = embedding_service
        self.qdrant_service = qdrant_service
        self.redaction_service = redaction_service
    
    def process_document(
        self,
        db: Session,
        document_id: UUID,
        file_path: Optional[Path] = None,
        file_content: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Process a document through the complete ingestion pipeline.
        
        Pipeline stages:
        1. Parse document to extract text
        2. Chunk parsed text (PII redaction disabled)
        3. Persist document and chunks to database
        
        Args:
            db: Database session
            document_id: UUID of the document record (must already exist)
            file_path: Optional path to file
            file_content: Optional file content bytes
        
        Returns:
            Dictionary with processing results and status
        """
        # Fetch document record
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Determine file path
        if file_path is None and document.file_path:
            file_path = Path(document.file_path)
        elif file_path is None and file_content is None:
            raise ValueError("Either file_path or file_content must be provided")
        
        current_stage: Optional[str] = None

        result: Dict[str, Any] = {
            "document_id": str(document_id),
            "status": "processing",
            "stages": {}
        }
        
        try:
            # Stage 1: Parse document
            if not DocumentParser.is_format_supported(file_path or Path(document.name)):
                raise ValueError(f"Unsupported file format: {file_path.suffix if file_path else 'unknown'}")
            current_stage = "extracted"
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "in_progress",
                message="Parsing document content",
            )

            raw_text = self.parser.parse(file_path, file_content)
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "succeeded",
                details={"text_length": len(raw_text)},
            )
            result["stages"]["extracted"] = {
                "status": "success",
                "text_length": len(raw_text)
            }
            
            # Stage 2: Redaction (optional)
            current_stage = "redacted"
            redaction_enabled = self.redaction_service is not None
            message = "Redacting document content" if redaction_enabled else "Redaction disabled"
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "in_progress",
                message=message,
            )

            if redaction_enabled:
                redaction_result = self.redaction_service.redact_document(
                    raw_text,
                    str(document_id),
                    metadata={"filename": document.name, "project_id": str(document.project_id)},
                )
                redacted_text = redaction_result.get("redacted_text", raw_text)
                redaction_details = {
                    "redaction_enabled": True,
                    "redacted_text_length": len(redacted_text)
                }
                redaction_stage_status = "succeeded"
            else:
                redacted_text = raw_text
                redaction_details = {
                    "redaction_enabled": False,
                    "redacted_text_length": len(redacted_text)
                }
                redaction_stage_status = "skipped"

            document.content = redacted_text
            document.processed = True
            document.validation_status = "validated"
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                redaction_stage_status,
                details=redaction_details,
                commit=False,
            )
            db.commit()
            db.refresh(document)

            redacted_stage_payload: Dict[str, Any] = {
                "status": redaction_stage_status,
                "redacted_text_length": len(redacted_text)
            }
            if not redaction_enabled:
                redacted_stage_payload["reason"] = "Redaction disabled"
            result["stages"]["redacted"] = redacted_stage_payload
            
            # Stage 3: Chunk parsed text
            current_stage = "chunked"
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "in_progress",
                message="Chunking redacted text",
            )

            chunks = self.chunking_service.chunk_document(redacted_text)
            # Stage 4: Persist chunks
            chunk_records = []
            for chunk in chunks:
                chunk_record = DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char
                )
                db.add(chunk_record)
                chunk_records.append(chunk_record)
            
            db.commit()
            
            # Link chunks (set prev/next relationships)
            for i, chunk_record in enumerate(chunk_records):
                if i > 0:
                    chunk_record.prev_chunk_id = chunk_records[i - 1].id
                if i < len(chunk_records) - 1:
                    chunk_record.next_chunk_id = chunk_records[i + 1].id
            db.commit()

            result["stages"]["chunked"] = {
                "status": "success",
                "chunk_count": len(chunk_records)
            }

            # Final status update
            document.chunked = True
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "succeeded",
                details={
                    "chunk_count": len(chunk_records),
                    "average_tokens": int(sum(c.token_count or 0 for c in chunk_records) / len(chunk_records)) if chunk_records else 0
                },
                commit=False,
            )
            db.commit()

            result["stages"]["persisted"] = {
                "status": "success",
                "chunks_created": len(chunk_records)
            }

            # Stage 5: Generate embeddings and upsert to Qdrant
            current_stage = "embedded"
            embeddings_configured = (
                settings.environment.lower() != "test"
                and bool(
                    self.embedding_service
                    or (settings.openai_api_key and settings.qdrant_url)
                )
            )

            if chunk_records and embeddings_configured:
                self.status_recorder.record(
                    db,
                    document_id,
                    current_stage,
                    "in_progress",
                    message="Generating embeddings and upserting to Qdrant",
                )

                try:
                    embedding_service = self.embedding_service or get_embedding_service()
                    self.embedding_service = embedding_service
                    qdrant_service = self.qdrant_service or get_qdrant_service()
                    self.qdrant_service = qdrant_service

                    texts = [chunk.content for chunk in chunk_records]
                    embeddings = embedding_service.generate_embeddings_batch(texts)
                    if len(embeddings) != len(chunk_records):
                        raise RuntimeError(
                            "Embedding generation count mismatch"
                        )

                    payload: List[Dict[str, Any]] = []
                    for chunk_record, embedding in zip(chunk_records, embeddings):
                        chunk_record.embedding_id = str(chunk_record.id)
                        payload_item: Dict[str, Any] = {
                            "chunk_id": chunk_record.id,
                            "embedding": embedding,
                            "content": chunk_record.content,
                            "document_id": document_id,
                            "project_id": document.project_id,
                            "chunk_index": chunk_record.chunk_index,
                        }
                        if document.source_type:
                            payload_item["source_type"] = document.source_type
                        payload.append(payload_item)

                    qdrant_service.upsert_chunks(payload)
                    document.embedded = True
                    self.status_recorder.record(
                        db,
                        document_id,
                        current_stage,
                        "succeeded",
                        details={
                            "chunks_embedded": len(payload)
                        },
                        commit=False,
                    )
                    db.commit()

                    result["stages"]["embedded"] = {
                        "status": "success",
                        "chunks_embedded": len(payload)
                    }
                except Exception as exc:
                    logger.exception("Failed to embed document %s", document_id)
                    raise
            elif chunk_records:
                self.status_recorder.record(
                    db,
                    document_id,
                    current_stage,
                    "skipped",
                    message="Embedding service not configured",
                    commit=False,
                )
                document.embedded = False
                db.commit()
                result["stages"]["embedded"] = {
                    "status": "skipped",
                    "reason": "Embedding service not configured"
                }
            else:
                result["stages"]["embedded"] = {
                    "status": "skipped",
                    "reason": "No chunks generated"
                }
                document.embedded = False
                db.commit()

            result["status"] = "completed"

            # Update ingestion coverage metrics
            self.coverage_report_generator.generate_report(db)
            
            return result
            
        except Exception as e:
            db.rollback()
            failure_stage = current_stage or "pipeline"
            self.status_recorder.record(
                db,
                document_id,
                failure_stage,
                "failed",
                message=str(e),
            )
            # Flag document for manual review
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.validation_status = "flagged"
                db.commit()

            result["status"] = "failed"
            result["error"] = str(e)
            return result
