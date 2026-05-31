"""Admin user-management API (Sprint 43 T43.5).

Backend endpoints (no UI) for the owner/admin tier: list users, change a user's
role, and enable/disable a user. The whole router is gated by require_admin (wired
in app/main.py). The last ACTIVE owner can never be demoted or disabled (LastOwnerError -> 409
Conflict). Disabling (is_active=False) is enforced at every auth path as of
Sprint C (T46.3): a disabled user can no longer log in or be resolved as a
principal.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER, ROLE_VIEWER
from app.models.user import User
from app.schemas.auth import AdminUserResponse
from app.services.ownership import LastOwnerError, assert_not_last_owner

router = APIRouter(tags=["admin-users"])

_VALID_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER})


def _get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    """List all users (admin only)."""
    return db.query(User).order_by(User.created_at.asc()).all()


@router.patch("/{user_id}/role", response_model=AdminUserResponse)
def set_user_role(
    user_id: UUID,
    role: str = Body(..., embed=True),
    db: Session = Depends(get_db),
) -> User:
    """Change a user's role (admin only). The last owner cannot be demoted."""
    if role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid role: {role!r}")
    user = _get_user_or_404(db, user_id)
    # Demoting an owner away from 'owner' must not remove the final owner.
    if user.role == ROLE_OWNER and role != ROLE_OWNER:
        try:
            assert_not_last_owner(db, user_id)
        except LastOwnerError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    user.role = role
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/active", response_model=AdminUserResponse)
def set_user_active(
    user_id: UUID,
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
) -> User:
    """Enable or disable a user (admin only). The last active owner cannot be disabled.

    As of Sprint C (T46.3), is_active is enforced: a disabled user is rejected at
    login and on every per-request auth path (JWT + API key).
    """
    user = _get_user_or_404(db, user_id)
    # Disabling the final owner would lock out owner administration (once enforced).
    if not is_active and user.role == ROLE_OWNER:
        try:
            assert_not_last_owner(db, user_id)
        except LastOwnerError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user
