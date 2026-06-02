"""Project grouping admin API — Space assignment + tags (Sprint 44 T44.5).

Owner/admin-only backend (no UI) for the project-side grouping operations:
assigning a project to a Space (workspace_id) and attaching/detaching cross-
cutting project tags. The whole router is gated by require_admin (wired in
app/main.py). Mutates grouping data only; no authorize() enforcement is wired
here (Sprint C). Distinct from the public projects CRUD router (mounted at
/api/v1/projects) so the admin gate is not mixed into the per-id read/write
routes — and so there is no (method, path) shadow with them.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.models.project_tag import ProjectTag
from app.models.tag import Tag
from app.models.workspace import Workspace
from app.schemas.space import (
    ProjectSpaceResponse,
    ProjectSpaceUpdate,
    ProjectTagResponse,
)
from app.services.cache_manager import get_cache_manager

router = APIRouter(tags=["admin-project-grouping"])

_cache_manager = get_cache_manager()


def _get_project_or_404(db: Session, project_id: UUID) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}/space", response_model=ProjectSpaceResponse)
def set_project_space(
    project_id: UUID, data: ProjectSpaceUpdate, db: Session = Depends(get_db)
) -> ProjectSpaceResponse:
    """Assign a project to a Space, or un-assign it (admin only).

    ``space_id`` None leaves the project space-less (workspace_id NULL) — the
    legacy state, tolerated by the NULL-safe membership/inheritance path. The
    target Space must exist when provided.
    """
    project = _get_project_or_404(db, project_id)
    if (
        data.space_id is not None
        and db.query(Workspace).filter(Workspace.id == data.space_id).first() is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Space not found")
    project.workspace_id = data.space_id
    db.commit()
    db.refresh(project)
    # A Space (re)assignment changes the project's cached metadata AND which
    # members may list it / its documents — so this must bust at the SAME scope
    # as the membership-change path (spaces.py:_invalidate_membership_caches):
    # a FULL document-list bust, because the unfiltered `GET /documents` listing
    # is cached per-user under '*' keys that a project-scoped bust would miss,
    # leaving stale RBAC visibility for the TTL. invalidate_project_metadata
    # already clears every list key regardless of the project_id passed.
    _cache_manager.invalidate_project_metadata(str(project_id))
    _cache_manager.invalidate_document_lists()
    return ProjectSpaceResponse(project_id=project.id, space_id=project.workspace_id)


@router.post(
    "/{project_id}/tags/{tag_id}",
    response_model=ProjectTagResponse,
    status_code=status.HTTP_201_CREATED,
)
def attach_project_tag(
    project_id: UUID, tag_id: UUID, db: Session = Depends(get_db)
) -> ProjectTag:
    """Attach a (theme) tag to a project (admin only).

    Re-attaching an existing link is a 409 (the composite PK also enforces it).
    """
    _get_project_or_404(db, project_id)
    if db.query(Tag).filter(Tag.id == tag_id).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tag not found")

    existing = (
        db.query(ProjectTag)
        .filter(ProjectTag.project_id == project_id, ProjectTag.tag_id == tag_id)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Tag already attached to this project"
        )

    link = ProjectTag(project_id=project_id, tag_id=tag_id)
    db.add(link)
    db.commit()
    return link


@router.delete("/{project_id}/tags/{tag_id}", response_model=dict[str, str])
def detach_project_tag(
    project_id: UUID, tag_id: UUID, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Detach a tag from a project (admin only)."""
    link = (
        db.query(ProjectTag)
        .filter(ProjectTag.project_id == project_id, ProjectTag.tag_id == tag_id)
        .first()
    )
    if link is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Tag is not attached to this project"
        )
    db.delete(link)
    db.commit()
    return {"status": "detached", "project_id": str(project_id), "tag_id": str(tag_id)}
