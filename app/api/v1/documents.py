"""
FastAPI routes for document ingestion.

Handles file uploads, format detection, parsing, redaction, chunking, and persistence.
"""

import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.authorization import accessible_filter, authorize_or_403
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.document import Document
from app.models.project import Project
from app.schemas.chunk import DocumentChunkRead
from app.schemas.document import DocumentListItem, DocumentRead
from app.schemas.pagination import PaginatedResponse
from app.services.cache_manager import get_cache_manager
from app.services.coverage_report import CoverageReportGenerator
from app.services.document_ingestion import DocumentIngestionService
from app.services.document_parser import DocumentParser
from app.services.document_query_service import DocumentQueryService
from app.services.processing_status import ProcessingStatusRecorder
from app.services.soft_delete_service import DocumentSoftDeleteService

router = APIRouter()
_soft_delete_service = DocumentSoftDeleteService()

# Storage directory for uploaded files
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ingestion_service: DocumentIngestionService | None = None
_ingestion_init_error: str | None = None
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
    project_id: UUID | None = Query(None, description="Filter by project identifier"),
    processed: bool | None = Query(None, description="Filter by processing state"),
    search: str | None = Query(
        None, min_length=1, max_length=200, description="Case-insensitive name search"
    ),
    include_deleted: bool = Query(
        False, description="Include soft-deleted documents in results"
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        DocumentQueryService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=DocumentQueryService.MAX_PAGE_SIZE,
        description="Results per page",
    ),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Return a paginated document list with optional filters.

    By default, soft-deleted documents are excluded. Use include_deleted=true to see all documents.
    With RBAC enabled, non-privileged callers see only documents whose owning project
    is in a Space they belong to (or that they own) — T47.3 closes the list leak.
    """
    access = accessible_filter(user, Document, db)
    # Cache PER access-scope (see list_projects): privileged/flag-off share "all";
    # each scoped caller gets its own entry so no cross-tenant cache serving.
    scope = "all" if access is None else str(user.user_id)
    cache_key = (
        *_cache_manager.document_list_key(
            project_id=str(project_id) if project_id else None,
            processed=processed,
            search=search,
            page=page,
            page_size=page_size,
            include_deleted=include_deleted,
        ),
        f"scope={scope}",
    )

    def _loader() -> dict[str, Any]:
        documents, meta = _document_query_service.list_documents(
            db,
            page=page,
            page_size=page_size,
            project_id=project_id,
            processed=processed,
            search=search,
            include_deleted=include_deleted,
            access_filter=access,
        )
        resources = [
            DocumentListItem.model_validate(document) for document in documents
        ]
        return {"data": resources, "pagination": meta}

    response, _ = _cache_manager.cached_value("document_lists", cache_key, _loader)
    return response


@router.post("/upload", response_model=DocumentRead)
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    file_type: str | None = None,
    source_type: str | None = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
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
                f"Unsupported file format: {file_path.suffix}. Supported: .pdf, .docx, .pptx, .csv, "
                ".xlsx, .md, .markdown, .txt"
            ),
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
        ".json": "application/json",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
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
            ".json": "config",
            ".xml": "config",
            ".yaml": "config",
            ".yml": "config",
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
        validation_status="pending",
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
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
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
    authorize_or_403(user, "process", document, db)

    # Get file path
    if not document.file_path:
        raise HTTPException(
            status_code=400, detail="Document has no associated file path"
        )

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404, detail=f"File not found: {document.file_path}"
        )

    # Initialize ingestion service
    try:
        ingestion_service = get_ingestion_service()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Ingestion service unavailable: {exc}"
        ) from exc

    # Process document (synchronously for now)
    # In production, this could be moved to background_tasks
    result = ingestion_service.process_document(
        db=db, document_id=document_id, file_path=file_path
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {result.get('error', 'Unknown error')}",
        )

    _cache_manager.invalidate_document_lists(str(document.project_id))
    return result


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DocumentRead:
    """Get a document by ID with stats and content preview."""
    document = _document_query_service.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    authorize_or_403(user, "read", document, db)
    _ = document.processing_events

    # Compute stats from chunks
    chunk_count = len(document.chunks) if document.chunks else 0
    total_tokens = (
        sum(c.token_count or 0 for c in document.chunks) if document.chunks else 0
    )

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
                last_space = truncated.rfind(" ")
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


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> FileResponse:
    """
    Download the original uploaded document file.

    Returns the file with its original filename and MIME type.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    authorize_or_403(user, "read", document, db)

    if not document.file_path:
        raise HTTPException(status_code=400, detail="Document has no associated file")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=file_path,
        filename=document.name,
        media_type=document.mime_type or "application/octet-stream",
    )


@router.get(
    "/{document_id}/chunks", response_model=PaginatedResponse[DocumentChunkRead]
)
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
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Return paginated chunks for a document, ordered by chunk index."""
    document = _document_query_service.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    authorize_or_403(user, "read", document, db)

    chunks, meta = _document_query_service.list_chunks_by_document(
        db,
        document_id,
        page=page,
        page_size=page_size,
    )
    resources = [DocumentChunkRead.model_validate(chunk) for chunk in chunks]
    return {"data": resources, "pagination": meta}


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: UUID,
    confirm: bool = Query(
        False,
        description="Must be true to confirm deletion. This soft-deletes the document (can be restored later).",
    ),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, str]:
    """Soft-delete a document.

    Requires authentication and explicit confirmation via confirm=true query parameter.
    This is a SOFT delete - the document and its data are hidden but can be restored
    using POST /documents/{id}/restore.

    The original file on disk is NOT deleted during soft delete.
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document deletion requires confirm=true query parameter. "
            "This will soft-delete the document (can be restored later).",
        )

    existing = _document_query_service.get_document(
        db, document_id, include_deleted=True
    )
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    authorize_or_403(user, "delete", existing, db)

    result = _soft_delete_service.soft_delete_document(
        db, document_id, deleted_by=user.username
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is already deleted",
        )

    document = _document_query_service.get_document(
        db, document_id, include_deleted=True
    )
    project_id = str(document.project_id) if document and document.project_id else None
    _cache_manager.invalidate_document_lists(project_id)
    return {
        "status": "deleted",
        "id": str(document_id),
        "message": "Document soft-deleted. Use POST /documents/{id}/restore to recover.",
    }


@router.post("/{document_id}/restore", response_model=dict[str, Any])
async def restore_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Restore a soft-deleted document.

    Requires authentication. Only works on documents that have been soft-deleted.
    """
    existing = _document_query_service.get_document(
        db, document_id, include_deleted=True
    )
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    authorize_or_403(user, "restore", existing, db)

    result = _soft_delete_service.restore_document(db, document_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is not deleted",
        )

    document = _document_query_service.get_document(db, document_id)
    project_id = str(document.project_id) if document and document.project_id else None
    _cache_manager.invalidate_document_lists(project_id)
    return {"status": "restored", "id": str(document_id)}


@router.get("/coverage/report")
async def get_coverage_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Generate and return ingestion coverage report."""
    generator = CoverageReportGenerator()
    report = generator.generate_report(db)
    return report


@router.get("/service/health")
async def ingestion_service_health() -> dict[str, Any]:
    """Health check for the ingestion pipeline service."""
    status = "healthy" if _ingestion_init_error is None else "degraded"
    response: dict[str, Any] = {"status": status, "service": "document-ingestion"}
    if _ingestion_init_error:
        response["detail"] = _ingestion_init_error
    return response
