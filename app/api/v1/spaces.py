"""Space management API — lifecycle + membership (Sprint 44 T44.5).

Owner/admin-only backend (no UI) for managing Spaces (workspaces) and their
memberships. The whole router is gated by require_admin (wired in app/main.py),
mirroring the S43 admin_users router. This only manages grouping/grant data —
space_members is the access-grant unit, but NO authorize() enforcement is wired
into read/write routes here (that is Sprint C); this remains a zero-enforcement
sprint, so populating these rows does not change any data-access behavior today.

Owner-safety: managing Space membership can never strand the owner, because the
owner/admin tier is allowed by ROLE regardless of Space membership (see
authorize() — privileged roles short-circuit before the membership branch).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER, ROLE_VIEWER
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.space import (
    SpaceCreate,
    SpaceMemberCreate,
    SpaceMemberResponse,
    SpaceResponse,
)
from app.services.cache_manager import get_cache_manager

router = APIRouter(tags=["admin-spaces"])

_VALID_GRANT_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER})
_cache_manager = get_cache_manager()


def _invalidate_membership_caches() -> None:
    """A Space membership change moves which projects/documents a user may LIST, so
    the per-scope project + document list caches (T47.3) must be cleared — else a
    revoked member keeps seeing a stale cached list (and a new member misses theirs)
    until the TTL expires. Missions/reports/jobs lists are uncached (live queries)."""
    _cache_manager.invalidate_project_metadata()
    _cache_manager.invalidate_document_lists()


def _get_space_or_404(db: Session, space_id: UUID) -> Workspace:
    space = db.query(Workspace).filter(Workspace.id == space_id).first()
    if space is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Space not found")
    return space


@router.post("", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
def create_space(data: SpaceCreate, db: Session = Depends(get_db)) -> Workspace:
    """Create a new Space (admin only)."""
    space = Workspace(name=data.name)
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


@router.get("", response_model=list[SpaceResponse])
def list_spaces(db: Session = Depends(get_db)) -> list[Workspace]:
    """List all Spaces (admin only)."""
    return db.query(Workspace).order_by(Workspace.created_at.asc()).all()


@router.post(
    "/{space_id}/members",
    response_model=SpaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_space_member(
    space_id: UUID, data: SpaceMemberCreate, db: Session = Depends(get_db)
) -> SpaceMember:
    """Grant a user membership of a Space (admin only).

    Idempotency is rejected, not silent: re-adding an existing member is a 409 so
    the caller learns the grant already exists (the UNIQUE(workspace_id,user_id)
    constraint also enforces this at the DB).
    """
    if data.role not in _VALID_GRANT_ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Invalid role: {data.role!r}"
        )
    _get_space_or_404(db, space_id)
    if db.query(User).filter(User.id == data.user_id).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = (
        db.query(SpaceMember)
        .filter(
            SpaceMember.workspace_id == space_id,
            SpaceMember.user_id == data.user_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="User is already a member of this Space"
        )

    member = SpaceMember(workspace_id=space_id, user_id=data.user_id, role=data.role)
    db.add(member)
    db.commit()
    db.refresh(member)
    _invalidate_membership_caches()
    return member


@router.delete("/{space_id}/members/{user_id}", response_model=dict[str, str])
def remove_space_member(
    space_id: UUID, user_id: UUID, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Revoke a user's membership of a Space (admin only).

    Safe for the owner: the owner/admin tier is granted access by role, not by
    Space membership, so revoking a membership never locks the owner out.
    """
    member = (
        db.query(SpaceMember)
        .filter(
            SpaceMember.workspace_id == space_id,
            SpaceMember.user_id == user_id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )
    db.delete(member)
    db.commit()
    _invalidate_membership_caches()
    return {"status": "removed", "space_id": str(space_id), "user_id": str(user_id)}
