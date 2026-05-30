"""FastAPI router implementing the onboarding workflow."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.project import Project
from app.onboarding.idempotency import IdempotencyService
from app.onboarding.jobs import create_job, process_job
from app.onboarding.schemas import JobRead
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.schemas.project import ProjectRead, ProjectUpdate
from app.services.cache_manager import get_cache_manager
from app.services.processing_status import ProcessingStatusRecorder

router = APIRouter(tags=["onboarding"])

_status_recorder = ProcessingStatusRecorder()
_cache_manager = get_cache_manager()


def _idempotency(
    *,
    request: Request,
    key: str | None,
    db: Session,
) -> IdempotencyService:
    return IdempotencyService(
        db,
        method=request.method,
        path=request.url.path,
        key=key,
    )


# NOTE: POST /projects intentionally lives ONLY on the projects router
# (app/api/v1/projects.py). It was previously duplicated here but dead-shadowed by
# first-match-wins router resolution — and this copy did not record owner_id from the
# caller (predated T43.4). Removed in the Sprint 43 review follow-up; the idempotency
# support was ported to the canonical handler. The duplicate-route guard in main.py
# now prevents this shadowing class from recurring.


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    """Update project metadata with idempotent replay support."""
    idempotency = _idempotency(request=request, key=idempotency_key, db=db)
    payload_dict = payload.model_dump(exclude_unset=True)
    cached = idempotency.check_replay(payload_dict)
    if cached:
        return JSONResponse(content=cached.data, status_code=cached.status_code)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    for field, value in payload_dict.items():
        setattr(project, field, value)
    db.flush()
    db.refresh(project)

    resource = ProjectRead.model_validate(project)
    response_body = resource.model_dump(mode="json")

    idempotency.save_response(
        request_payload=payload_dict,
        response_payload=response_body,
        status_code=status.HTTP_200_OK,
    )
    db.commit()
    _cache_manager.invalidate_project_metadata(str(project_id))
    return JSONResponse(content=response_body, status_code=status.HTTP_200_OK)


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def register_document(
    payload: DocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    """Register a document for ingestion via the onboarding workflow."""
    payload_dict = payload.model_dump()
    idempotency = _idempotency(request=request, key=idempotency_key, db=db)
    cached = idempotency.check_replay(payload_dict)
    if cached:
        return JSONResponse(content=cached.data, status_code=cached.status_code)

    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(
            status_code=404, detail=f"Project {payload.project_id} not found"
        )

    if not payload.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_path is required for onboarding document registration",
        )

    path = Path(payload.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"File not found at {payload.file_path}"
        )

    mutable_payload = payload.model_dump(exclude_none=True)
    mutable_payload.setdefault("file_size", path.stat().st_size)
    mutable_payload.setdefault("mime_type", _infer_mime_type(path))

    document = Document(**mutable_payload)
    db.add(document)
    db.flush()
    db.refresh(document)

    _status_recorder.record(
        db,
        document.id,
        stage="registered",
        status="succeeded",
        details={"file_path": document.file_path, "mime_type": document.mime_type},
        commit=False,
    )
    db.flush()
    db.refresh(document)

    resource = DocumentRead.model_validate(document)
    response_body = resource.model_dump(mode="json")

    idempotency.save_response(
        request_payload=payload_dict,
        response_payload=response_body,
        status_code=status.HTTP_201_CREATED,
    )
    db.commit()
    _cache_manager.invalidate_document_lists(str(payload.project_id))
    return JSONResponse(content=response_body, status_code=status.HTTP_201_CREATED)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    """Update document metadata."""
    payload_dict = payload.model_dump(exclude_unset=True)
    idempotency = _idempotency(request=request, key=idempotency_key, db=db)
    cached = idempotency.check_replay(payload_dict)
    if cached:
        return JSONResponse(content=cached.data, status_code=cached.status_code)

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    for field, value in payload_dict.items():
        setattr(document, field, value)
    db.flush()
    db.refresh(document)

    resource = DocumentRead.model_validate(document)
    response_body = resource.model_dump(mode="json")

    idempotency.save_response(
        request_payload=payload_dict,
        response_payload=response_body,
        status_code=status.HTTP_200_OK,
    )
    db.commit()
    _cache_manager.invalidate_document_lists(str(document.project_id))
    return JSONResponse(content=response_body, status_code=status.HTTP_200_OK)


# NOTE: GET /documents/{document_id} intentionally lives ONLY on the documents router
# (app/api/v1/documents.py), whose handler is a superset (stats + content preview). The
# copy here was dead-shadowed by first-match-wins resolution; removed in the Sprint 43
# review follow-up. The duplicate-route guard in main.py prevents recurrence.


@router.post(
    "/jobs",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_ingestion_job(
    *,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    """Create an ingestion job and dispatch it to the background runner."""
    payload_dict = {"document_id": str(document_id)}
    idempotency = _idempotency(request=request, key=idempotency_key, db=db)
    cached = idempotency.check_replay(payload_dict)
    if cached:
        return JSONResponse(
            content=cached.data,
            status_code=cached.status_code,
            headers={"Location": f"{settings.api_v1_prefix}/jobs/{cached.data['id']}"},
        )

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if not document.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is missing file_path; cannot enqueue ingestion job",
        )

    job = create_job(db, document=document)
    db.flush()
    db.refresh(job)

    background_tasks.add_task(process_job, job.id)

    resource = JobRead.model_validate(job)
    response_body = resource.model_dump(mode="json")

    idempotency.save_response(
        request_payload=payload_dict,
        response_payload=response_body,
        status_code=status.HTTP_202_ACCEPTED,
    )
    db.commit()

    headers = {"Location": f"{settings.api_v1_prefix}/jobs/{job.id}"}
    return JSONResponse(
        content=response_body, status_code=status.HTTP_202_ACCEPTED, headers=headers
    )


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> JobRead:
    """Return ingestion job status."""
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobRead.model_validate(job)


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db)) -> list[JobRead]:
    """List all ingestion jobs."""
    jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).all()
    return [JobRead.model_validate(job) for job in jobs]


def _infer_mime_type(path: Path) -> str | None:
    """Infer MIME type based on file extension."""
    mapping = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
    }
    return mapping.get(path.suffix.lower())
