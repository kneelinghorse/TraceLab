"""
FastAPI routes for document ingestion.

Handles file uploads, format detection, parsing, redaction, chunking, and persistence.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import Document
from app.models.project import Project
from app.schemas.document import DocumentRead
from app.services.document_ingestion import DocumentIngestionService
from app.services.document_parser import DocumentParser
from app.services.coverage_report import CoverageReportGenerator
from app.services.processing_status import ProcessingStatusRecorder
from app.core.config import settings

router = APIRouter()

# Storage directory for uploaded files
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ingestion_service: Optional[DocumentIngestionService] = None
_ingestion_init_error: Optional[str] = None
_status_recorder = ProcessingStatusRecorder()


def get_ingestion_service() -> DocumentIngestionService:
    """Instantiate the ingestion service lazily for reuse."""
    global _ingestion_service, _ingestion_init_error
    if _ingestion_service is None:
        try:
            _ingestion_service = DocumentIngestionService()
            _ingestion_init_error = None
        except Exception as exc:  # pragma: no cover - defensive
            _ingestion_init_error = str(exc)
            raise
    return _ingestion_service


@router.post("/upload", response_model=DocumentRead)
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    file_type: Optional[str] = None,
    source_type: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
) -> DocumentRead:
    """
    Upload a document file.
    
    Supports: .pdf, .docx, .pptx, .csv, .xlsx
    
    The file is saved and a document record is created.
    Processing (parsing, redaction, chunking) can be triggered separately
    or can be done asynchronously in the background.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    # Validate file format
    file_path = Path(file.filename)
    if not DocumentParser.is_format_supported(file_path):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_path.suffix}. Supported: .pdf, .docx, .pptx, .csv, .xlsx"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Save file to disk
    file_id = uuid.uuid4()
    saved_file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    saved_file_path.write_bytes(file_content)
    
    # Detect MIME type from extension
    mime_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
    mime_type = mime_types.get(file_path.suffix.lower())
    
    # Infer file_type from extension if not provided
    if not file_type:
        file_type_map = {
            ".pdf": "report",
            ".docx": "report",
            ".pptx": "report",
            ".csv": "survey",
            ".xlsx": "survey"
        }
        file_type = file_type_map.get(file_path.suffix.lower(), "report")
    
    # Create document record
    document = Document(
        project_id=project_id,
        name=file.filename,
        file_path=str(saved_file_path),
        file_type=file_type,
        file_size=file_size,
        mime_type=mime_type,
        source_type=source_type,
        processed=False,
        chunked=False,
        embedded=False,
        validation_status="pending"
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Audit uploaded status
    _status_recorder.record(
        db,
        document.id,
        stage="uploaded",
        status="succeeded",
        details={
            "file_name": file.filename,
            "file_size_bytes": file_size,
            "mime_type": mime_type,
            "source_type": source_type,
        },
    )
    db.refresh(document)
    # Ensure relationship is loaded for response
    _ = document.processing_events
    
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/process")
async def process_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Process a document through the ingestion pipeline.
    
    Stages:
    1. Parse document to extract text
    2. Redact PII using Presidio
    3. Chunk redacted text
    4. Persist chunks to database
    
    Can be run synchronously or asynchronously via background tasks.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    
    # Get file path
    if not document.file_path:
        raise HTTPException(
            status_code=400,
            detail="Document has no associated file path"
        )
    
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {document.file_path}"
        )
    
    # Initialize ingestion service
    try:
        ingestion_service = get_ingestion_service()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ingestion service unavailable: {exc}"
        ) from exc
    
    # Process document (synchronously for now)
    # In production, this could be moved to background_tasks
    result = ingestion_service.process_document(
        db=db,
        document_id=document_id,
        file_path=file_path
    )
    
    if result["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {result.get('error', 'Unknown error')}"
        )
    
    return result


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db)
) -> DocumentRead:
    """Get a document by ID."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    _ = document.processing_events
    
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """Delete a document and its associated chunks."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    
    # Delete file if it exists
    if document.file_path:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()
    
    # Delete document (chunks will be cascade deleted)
    db.delete(document)
    db.commit()
    
    return {"message": f"Document {document_id} deleted"}


@router.get("/coverage/report")
async def get_coverage_report(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate and return ingestion coverage report."""
    generator = CoverageReportGenerator()
    report = generator.generate_report(db)
    return report


@router.get("/service/health")
async def ingestion_service_health() -> Dict[str, Any]:
    """Health check for the ingestion pipeline service."""
    status = "healthy" if _ingestion_init_error is None else "degraded"
    response: Dict[str, Any] = {"status": status, "service": "document-ingestion"}
    if _ingestion_init_error:
        response["detail"] = _ingestion_init_error
    return response
