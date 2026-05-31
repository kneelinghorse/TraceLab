"""Project CRUD endpoints (list/detail/create/update/stats)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.authorization import authorize_or_403
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.onboarding.idempotency import IdempotencyService
from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate
from app.services.cache_manager import get_cache_manager
from app.services.project_query_service import ProjectQueryService

router = APIRouter()
_service = ProjectQueryService()
_cache_manager = get_cache_manager()


# -----------------------------------------------------------------------------
# Restore endpoint (soft delete recovery)
# -----------------------------------------------------------------------------


@router.post("/{project_id}/restore", response_model=dict[str, Any])
def restore_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Restore a soft-deleted project.

    Requires authentication. Only works on projects that have been soft-deleted.
    """
    existing = _service.get_project(db, project_id, include_deleted=True)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    authorize_or_403(user, "restore", existing, db)
    result = _service.restore_project(db, project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is not deleted",
        )
    # Invalidate caches
    _cache_manager.invalidate_project_metadata(str(project_id))
    return {"status": "restored", "id": str(project_id)}


@router.get("", response_model=PaginatedResponse[ProjectRead])
def list_projects(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        ProjectQueryService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=ProjectQueryService.MAX_PAGE_SIZE,
        description="Results per page",
    ),
    search: str | None = Query(
        None,
        min_length=1,
        max_length=200,
        description="Case-insensitive substring match",
    ),
    include_deleted: bool = Query(False, description="Include soft-deleted projects in results"),
    db: Session = Depends(get_db),
):
    """Return paginated projects ordered by creation time.

    By default, soft-deleted projects are excluded. Use include_deleted=true to see all projects.
    """
    cache_key = _cache_manager.project_metadata_key(
        kind="list",
        search=search,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )

    def _loader() -> dict[str, Any]:
        projects, meta = _service.list_projects(
            db,
            page=page,
            page_size=page_size,
            search=search,
            include_deleted=include_deleted,
        )
        resources = [ProjectRead.model_validate(project) for project in projects]
        return {"data": resources, "pagination": meta}

    response, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return response


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ProjectRead:
    """Return a single project record."""
    project = _service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    authorize_or_403(user, "read", project, db)

    cache_key = _cache_manager.project_metadata_key(kind="detail", identifier=str(project_id))

    def _loader() -> ProjectRead:
        project = _service.get_project(db, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return ProjectRead.model_validate(project)

    result, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return result


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    """Create a new project owned by the authenticated caller.

    Supports idempotent retries via the optional Idempotency-Key header: replaying
    the same key with an identical body returns the original response; the same key
    with a different body returns 409. (Ported here from the onboarding router,
    whose POST /projects was dead-shadowed by this route — Sprint 43 review.)
    """
    idempotency = IdempotencyService(
        db, method=request.method, path=request.url.path, key=idempotency_key
    )
    cached = idempotency.check_replay(data.model_dump())
    if cached:
        return JSONResponse(content=cached.data, status_code=cached.status_code)

    project = _service.create_project(db, data, owner_id=current_user.user_id)
    resource = ProjectRead.model_validate(project)
    response_body = resource.model_dump(mode="json")

    idempotency.save_response(
        request_payload=data.model_dump(),
        response_payload=response_body,
        status_code=status.HTTP_201_CREATED,
    )
    db.commit()
    # Invalidate list cache
    _cache_manager.invalidate_project_metadata()
    return JSONResponse(content=response_body, status_code=status.HTTP_201_CREATED)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ProjectRead:
    """Update an existing project."""
    existing = _service.get_project(db, project_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    authorize_or_403(user, "update", existing, db)
    project = _service.update_project(db, project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    # Invalidate caches
    _cache_manager.invalidate_project_metadata(str(project_id))
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_200_OK, response_model=dict[str, Any])
def delete_project(
    project_id: UUID,
    confirm: bool = Query(
        False,
        description="Must be true to confirm deletion. This soft-deletes the project (can be restored later).",
    ),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Soft-delete a project.

    Requires authentication and explicit confirmation via confirm=true query parameter.
    This is a SOFT delete - the project and its data are hidden but can be restored
    using POST /projects/{id}/restore.

    To permanently delete, use a separate purge operation (not yet implemented).
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project deletion requires confirm=true query parameter. "
            "This will soft-delete the project (can be restored later).",
        )
    existing = _service.get_project(db, project_id, include_deleted=True)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    authorize_or_403(user, "delete", existing, db)
    result = _service.soft_delete_project(db, project_id, deleted_by=user.username)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is already deleted",
        )
    # Invalidate caches
    _cache_manager.invalidate_project_metadata(str(project_id))
    return {
        "status": "deleted",
        "id": str(project_id),
        "message": "Project soft-deleted. Use POST /projects/{id}/restore to recover.",
    }


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ProjectStats:
    """Get aggregated statistics for a project."""
    project = _service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    authorize_or_403(user, "read", project, db)

    cache_key = _cache_manager.project_metadata_key(kind="stats", identifier=str(project_id))

    def _loader() -> ProjectStats:
        stats = _service.get_project_stats(db, project_id)
        if not stats:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return stats

    result, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return result
