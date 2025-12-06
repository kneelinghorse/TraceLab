"""
FastAPI routes for document ingestion.

Handles file uploads, format detection, parsing, redaction, chunking, and persistence.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import Document
from app.models.project import Project
from app.schemas.chunk import DocumentChunkRead
from app.schemas.document import DocumentListItem, DocumentRead
from app.schemas.pagination import PaginatedResponse
from app.services.document_ingestion import DocumentIngestionService
from app.services.document_parser import DocumentParser
from app.services.coverage_report import CoverageReportGenerator
from app.services.processing_status import ProcessingStatusRecorder
from app.core.config import settings
from app.services.cache_manager import get_cache_manager
from app.services.document_query_service import DocumentQueryService

router = APIRouter()

# Storage directory for uploaded files
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ingestion_service: Optional[DocumentIngestionService] = None
_ingestion_init_error: Optional[str] = None
_status_recorder = ProcessingStatusRecorder()
_document_query_service = DocumentQueryService()
_cache_manager = get_cache_manager()


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


@router.get("", response_model=PaginatedResponse[DocumentListItem])
def list_documents(
    project_id: Optional[UUID] = Query(None, description="Filter by project identifier"),
    processed: Optional[bool] = Query(None, description="Filter by processing state"),
    search: Optional[str] = Query(None, min_length=1, max_length=200, description="Case-insensitive name search"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        DocumentQueryService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=DocumentQueryService.MAX_PAGE_SIZE,
        description="Results per page",
    ),
    db: Session = Depends(get_db),
):
    """Return a paginated document list with optional filters."""
    cache_key = _cache_manager.document_list_key(
        project_id=str(project_id) if project_id else None,
        processed=processed,
        search=search,
        page=page,
        page_size=page_size,
    )

    def _loader() -> Dict[str, Any]:
        documents, meta = _document_query_service.list_documents(
            db,
            page=page,
            page_size=page_size,
            project_id=project_id,
            processed=processed,
            search=search,
        )
        resources = [DocumentListItem.model_validate(document) for document in documents]
        return {"data": resources, "pagination": meta}

    response, _ = _cache_manager.cached_value("document_lists", cache_key, _loader)
    return response


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
    
    Supports: .pdf, .docx, .pptx, .csv, .xlsx, .md, .markdown, .txt
    
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
            detail=(
                "Unsupported file format: {suffix}. Supported: .pdf, .docx, .pptx, .csv, "
                ".xlsx, .md, .markdown, .txt"
            ).format(suffix=file_path.suffix)
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
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
    }
    mime_type = mime_types.get(file_path.suffix.lower())
    
    # Infer file_type from extension if not provided
    if not file_type:
        file_type_map = {
            ".pdf": "report",
            ".docx": "report",
            ".pptx": "report",
            ".csv": "survey",
            ".xlsx": "survey",
            ".md": "notes",
            ".markdown": "notes",
            ".txt": "notes",
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
    
    response = DocumentRead.model_validate(document)
    _cache_manager.invalidate_document_lists(str(project_id))
    return response


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
    
    _cache_manager.invalidate_document_lists(str(document.project_id))
    return result


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db)
) -> DocumentRead:
    """Get a document by ID with stats and content preview."""
    document = _document_query_service.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    _ = document.processing_events

    # Compute stats from chunks
    chunk_count = len(document.chunks) if document.chunks else 0
    total_tokens = sum(c.token_count or 0 for c in document.chunks) if document.chunks else 0

    # Compute word count from chunk content
    word_count = 0
    if document.chunks:
        for chunk in document.chunks:
            if chunk.content:
                word_count += len(chunk.content.split())

    # Generate content preview from first chunks (up to ~500 chars)
    preview = None
    if document.chunks:
        sorted_chunks = sorted(document.chunks, key=lambda c: c.chunk_index)
        preview_parts = []
        current_length = 0
        max_preview_length = 500

        for chunk in sorted_chunks:
            if not chunk.content:
                continue
            if current_length >= max_preview_length:
                break
            remaining = max_preview_length - current_length
            if len(chunk.content) <= remaining:
                preview_parts.append(chunk.content)
                current_length += len(chunk.content)
            else:
                # Truncate at word boundary if possible
                truncated = chunk.content[:remaining]
                last_space = truncated.rfind(' ')
                if last_space > remaining * 0.6:  # Only truncate at space if reasonable
                    truncated = truncated[:last_space]
                preview_parts.append(truncated + "...")
                break

        preview = " ".join(preview_parts) if preview_parts else None

    # Build response with stats
    response = DocumentRead.model_validate(document)
    response.chunk_count = chunk_count
    response.total_tokens = total_tokens
    response.word_count = word_count
    response.preview = preview

    return response


@router.get("/{document_id}/chunks", response_model=PaginatedResponse[DocumentChunkRead])
async def list_document_chunks(
    document_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        description="Results per page",
    ),
    db: Session = Depends(get_db),
):
    """Return paginated chunks for a document, ordered by chunk index."""
    document = _document_query_service.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    chunks, meta = _document_query_service.list_chunks_by_document(
        db,
        document_id,
        page=page,
        page_size=page_size,
    )
    resources = [DocumentChunkRead.model_validate(chunk) for chunk in chunks]
    return {"data": resources, "pagination": meta}


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """Delete a document and its associated chunks."""
    document = _document_query_service.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    
    # Delete file if it exists
    if document.file_path:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()
    
    # Delete document (chunks will be cascade deleted)
    project_id = str(document.project_id) if document.project_id else None
    db.delete(document)
    db.commit()
    _cache_manager.invalidate_document_lists(project_id)
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
