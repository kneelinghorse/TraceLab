"""The Librarian's HTTP surface (LIB-1).

Three calls, all human-principal only and all authorized against the project
with the caller's own principal (criterion 7): a conversational turn, a mission
draft, and the explicit creation of that draft as a pristine mission.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.v1.missions import _to_response
from app.core.authorization import authorize_or_403, is_service_principal
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.project import Project
from app.schemas.librarian import (
    CreatedMissionResponse,
    CreateFromDraftRequest,
    DraftRequest,
    DraftResponse,
    EvidenceRef,
    TurnRequest,
    TurnResponse,
)
from app.services.librarian import (
    LibrarianConflict,
    LibrarianDraftError,
    LibrarianService,
)
from app.services.librarian_model import (
    APIError,
    LibrarianUnavailable,
    RateLimitError,
    get_librarian_model,
)
from app.services.mission_service import MissionValidationError

logger = logging.getLogger(__name__)

router = APIRouter()


def get_librarian_service() -> LibrarianService:
    """Dependency factory; tests override it with a service built on a fake model."""
    return LibrarianService(model_factory=get_librarian_model)


def _load_project(
    db: Session,
    current_user: AuthenticatedUser,
    project_id: UUID,
    action: str,
) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    if project is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found.")
    authorize_or_403(current_user, action, project, db)
    return project


def _require_human(current_user: AuthenticatedUser) -> None:
    # The Librarian acts as its user, never as a service role (roadmap principle 4).
    if is_service_principal(current_user):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="The Librarian requires a human user principal.",
        )


def _provider_error(exc: Exception) -> HTTPException:
    logger.error("Librarian model provider error: %s", exc)
    return HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail="The Librarian's model provider returned an error. Try again shortly.",
    )


@router.post("/turns", response_model=TurnResponse)
def librarian_turn(
    payload: TurnRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: LibrarianService = Depends(get_librarian_service),
) -> TurnResponse:
    """One conversational turn. Corpus claims are validated against evidence retrieved in this turn."""
    _require_human(current_user)
    project = _load_project(db, current_user, payload.project_id, "read") if payload.project_id else None
    try:
        result = service.converse(db, current_user, project, payload.messages)
    except LibrarianUnavailable as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (RateLimitError, APIError) as exc:
        raise _provider_error(exc) from exc
    return TurnResponse(
        segments=result.reply.segments,
        suggested_action=result.reply.suggested_action,
        evidence=[
            EvidenceRef(
                id=entry.id,
                claim=entry.claim,
                source_url=entry.source_url,
                disposition=entry.disposition,
                href=f"/evidence/{entry.id}",
            )
            for entry in result.evidence
        ],
        withheld_count=result.withheld_count,
        usage=result.usage,
        model=result.model,
    )


@router.post("/drafts", response_model=DraftResponse)
def librarian_draft(
    payload: DraftRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: LibrarianService = Depends(get_librarian_service),
) -> DraftResponse:
    """Turn the conversation into a mission draft, compiled and linted but not saved."""
    _require_human(current_user)
    project = _load_project(db, current_user, payload.project_id, "read")
    try:
        result = service.draft_mission(project, payload.messages)
    except LibrarianUnavailable as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LibrarianDraftError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The Librarian could not produce a valid mission draft: {exc}",
        ) from exc
    except (RateLimitError, APIError) as exc:
        raise _provider_error(exc) from exc
    return DraftResponse(
        draft=result.draft,
        preview=result.preview,
        preview_error=result.preview_error,
        lint_errors=result.lint_errors,
        lint_warnings=result.lint_warnings,
        notes=result.notes,
        usage=result.usage,
        model=result.model,
    )


@router.post(
    "/missions",
    response_model=CreatedMissionResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={200: {"description": "The same draft was already created; the existing mission is returned."}},
)
def librarian_create_mission(
    payload: CreateFromDraftRequest,
    response: Response,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: LibrarianService = Depends(get_librarian_service),
) -> CreatedMissionResponse:
    """Create the reviewed draft as a pristine draft mission. Explicit, human-confirmed, idempotent."""
    _require_human(current_user)
    project = _load_project(db, current_user, payload.project_id, "create")
    try:
        mission, created = service.create_mission(db, project, payload.draft)
    except LibrarianConflict as exc:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissionValidationError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not created:
        response.status_code = http_status.HTTP_200_OK
    return CreatedMissionResponse(mission=_to_response(mission), created=created)
