"""Authenticated, project-scoped Evidence Ledger API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.authorization import (
    accessible_filter,
    accessible_project_ids,
    authorize_or_403,
    is_service_principal,
)
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.evidence_ledger import LedgerEntry, LedgerNote
from app.models.mission import Mission
from app.models.project import Project
from app.schemas.evidence_ledger import (
    CaptureRequest,
    CaptureResponse,
    LedgerDisposition,
    LedgerListResponse,
    LedgerNoteRead,
    LedgerSearchResponse,
    NoteUpsertRequest,
    PromotionRequest,
    PromotionResponse,
)
from app.services.evidence_ledger import (
    EvidenceLedgerService,
    get_evidence_ledger_service,
)
from app.services.report_promotion import ReportPromotionError

router = APIRouter()


def _load_project(
    db: Session,
    current_user: AuthenticatedUser,
    project_id: UUID,
    action: str,
) -> Project:
    if is_service_principal(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Evidence Ledger routes require a human user principal.",
        )
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    authorize_or_403(current_user, action, project, db)
    return project


def _authorize_mission(
    db: Session,
    current_user: AuthenticatedUser,
    mission_id: UUID | None,
    project_id: UUID,
    action: str,
) -> Mission | None:
    if mission_id is None:
        return None
    mission = db.query(Mission).filter(Mission.id == mission_id).first()
    if mission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found.",
        )
    authorize_or_403(current_user, action, mission, db)
    if mission.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mission does not belong to the requested project.",
        )
    return mission


def _normalize_required_filter(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} cannot be empty or whitespace.",
        )
    return normalized


def _normalize_optional_filter(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_filter(value, label)


def _evidence_access_filter(
    current_user: AuthenticatedUser,
    model: type[LedgerEntry] | type[LedgerNote],
    db: Session,
):
    """Extend child-row access with the owning project's owner allow-path."""
    base_filter = accessible_filter(current_user, model, db)
    if base_filter is None:
        return None
    owned_projects = select(Project.id).where(Project.owner_id == current_user.user_id)
    return or_(base_filter, model.project_id.in_(owned_projects))


@router.post(
    "/capture",
    response_model=CaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
def capture_evidence(
    request: CaptureRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> CaptureResponse:
    """Atomically capture one or more evidence claims."""
    project = _load_project(db, current_user, request.project_id, "create")
    _authorize_mission(
        db,
        current_user,
        request.mission_id,
        request.project_id,
        "create",
    )
    entries = service.capture(
        db,
        request,
        owner_id=current_user.user_id,
        workspace_id=project.workspace_id,
    )
    return CaptureResponse(entries=entries, count=len(entries))


@router.put("/notes/{note_key:path}", response_model=LedgerNoteRead)
def upsert_note(
    request: NoteUpsertRequest,
    note_key: str = Path(min_length=1, max_length=100),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> LedgerNoteRead:
    """Create or fully replace a keyed session note."""
    normalized_note_key = _normalize_required_filter(note_key, "note_key")
    if normalized_note_key in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="note_key cannot be a path-navigation segment.",
        )
    project = _load_project(db, current_user, request.project_id, "create")
    _authorize_mission(
        db,
        current_user,
        request.mission_id,
        request.project_id,
        "create",
    )
    note = service.upsert_note(
        db,
        normalized_note_key,
        request,
        owner_id=current_user.user_id,
        workspace_id=project.workspace_id,
    )
    return LedgerNoteRead.model_validate(note)


@router.get("", response_model=LedgerListResponse)
def list_evidence(
    project_id: UUID,
    session_key: str | None = Query(default=None, min_length=1, max_length=255),
    mission_id: UUID | None = None,
    disposition: LedgerDisposition | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> LedgerListResponse:
    """List accessible evidence and notes for one project."""
    _load_project(db, current_user, project_id, "read")
    _authorize_mission(db, current_user, mission_id, project_id, "read")
    project_scope = accessible_project_ids(current_user, db)
    normalized_session = _normalize_optional_filter(session_key, "session_key")
    entries, notes, entry_total, note_total = service.list_ledger(
        db,
        project_id=project_id,
        session_key=normalized_session,
        mission_id=mission_id,
        disposition=disposition,
        page=page,
        page_size=page_size,
        entry_access_filter=_evidence_access_filter(current_user, LedgerEntry, db),
        note_access_filter=_evidence_access_filter(current_user, LedgerNote, db),
        allowed_project_ids=project_scope,
    )
    return LedgerListResponse(
        entries=entries,
        notes=notes,
        entry_total=entry_total,
        note_total=note_total,
        page=page,
        page_size=page_size,
    )


@router.get("/search", response_model=LedgerSearchResponse)
def search_evidence(
    project_id: UUID,
    q: str = Query(min_length=1, max_length=4_000),
    session_key: str | None = Query(default=None, min_length=1, max_length=255),
    mission_id: UUID | None = None,
    disposition: LedgerDisposition | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> LedgerSearchResponse:
    """Search accessible claims with PostgreSQL FTS or literal ILIKE."""
    _load_project(db, current_user, project_id, "read")
    _authorize_mission(db, current_user, mission_id, project_id, "read")
    project_scope = accessible_project_ids(current_user, db)
    keyword = _normalize_required_filter(q, "q")
    normalized_session = _normalize_optional_filter(session_key, "session_key")
    entries, total = service.search(
        db,
        project_id=project_id,
        keyword=keyword,
        session_key=normalized_session,
        mission_id=mission_id,
        disposition=disposition,
        page=page,
        page_size=page_size,
        access_filter=_evidence_access_filter(current_user, LedgerEntry, db),
        allowed_project_ids=project_scope,
    )
    return LedgerSearchResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/promote",
    response_model=PromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_evidence(
    request: PromotionRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> PromotionResponse:
    """Promote a complete ledger session to a report or searchable document."""
    project = _load_project(db, current_user, request.project_id, "update")
    try:
        report, document, entry_count, note_count = service.promote(
            db,
            project_id=request.project_id,
            session_key=request.session_key,
            title=request.title,
            target=request.target,
            owner_id=current_user.user_id,
            workspace_id=project.workspace_id,
            created_by=current_user.email,
        )
    except ReportPromotionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return PromotionResponse(
        project_id=request.project_id,
        session_key=request.session_key,
        target=request.target,
        report_id=report.id,
        document_id=document.id if document is not None else None,
        title=report.title,
        entry_count=entry_count,
        note_count=note_count,
        status="completed" if document is not None else "created",
    )
