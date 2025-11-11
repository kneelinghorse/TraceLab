"""
Document ingestion service.

Orchestrates the complete ingestion pipeline: parsing, redaction, chunking, and persistence.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.document_parser import DocumentParser
from app.services.chunking import ChunkingService
from app.services.processing_status import ProcessingStatusRecorder
from app.services.coverage_report import CoverageReportGenerator
from app.models.document import Document
from app.models.chunk import DocumentChunk


class DocumentIngestionService:
    """Service for ingesting documents through the complete pipeline."""
    
    def __init__(
        self,
        chunking_service: Optional[ChunkingService] = None,
        status_recorder: Optional[ProcessingStatusRecorder] = None,
        coverage_report_generator: Optional[CoverageReportGenerator] = None,
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
            
            # Stage 2: (Legacy) Redaction disabled
            current_stage = "redacted"
            redacted_text = raw_text
            document.content = redacted_text
            document.processed = True
            document.validation_status = "validated"
            self.status_recorder.record(
                db,
                document_id,
                current_stage,
                "succeeded",
                details={
                    "redaction_enabled": False,
                    "redacted_text_length": len(redacted_text)
                },
                commit=False,
            )
            db.commit()
            db.refresh(document)

            result["stages"]["redacted"] = {
                "status": "skipped",
                "reason": "Presidio redaction disabled",
                "redacted_text_length": len(redacted_text)
            }
            
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
            
            result["status"] = "completed"
            result["stages"]["persisted"] = {
                "status": "success",
                "chunks_created": len(chunk_records)
            }

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
