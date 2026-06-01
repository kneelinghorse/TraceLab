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
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    AuthenticatedUser,
    hash_password,
    require_admin,
)
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from app.models.invite_code import InviteCode
from app.models.user import User
from app.schemas.auth import AdminUserCreate, AdminUserResponse
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


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    caller: AuthenticatedUser = Depends(require_admin),
) -> User:
    """Provision a user at an explicit role (T47.1).

    Admins may create any NON-owner role; granting ROLE_OWNER requires the caller to
    be an owner (mirrors set_user_role, closing the admin->owner escalation path).
    Gives the live RBAC harness (T47.2) a clean way to mint throwaway test users
    instead of the register->demote dance."""
    if payload.role not in _VALID_ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Invalid role: {payload.role!r}"
        )
    if payload.role == ROLE_OWNER and caller.role != ROLE_OWNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only an owner can grant the owner role",
        )
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    caller: AuthenticatedUser = Depends(require_admin),
) -> dict:
    """Hard-delete a user and purge its dependent rows (T47.1).

    The admin API previously offered only soft-disable; the live harness (T47.2)
    needs a full teardown so throwaway test users leave no cruft. The last active
    owner can never be deleted (409), and an admin cannot delete its own account
    (400, anti-lockout).

    Postgres FKs into users are mixed: owner_id (projects/collections/missions/
    reports/documents) is ON DELETE SET NULL and space_members is ON DELETE CASCADE
    — the DB handles those. api_keys, invite_codes, and device_authorization_grants
    have non-cascading users FKs, so they would block the delete; we clear them
    explicitly. ORDER MATTERS: a device grant references BOTH users.id AND
    api_keys.id, so it must be deleted BEFORE its api_key (else `DELETE FROM
    api_keys` fails its FK check at statement-end on Postgres while a grant still
    points at the key). Delete order is therefore grants -> api_keys -> invite_codes
    -> user. SQLite in tests does not enforce FKs, so a dedicated FK-enforced test
    (PRAGMA foreign_keys=ON) guards this order. Any NEW table with a non-cascading
    users/api_keys FK MUST be added to this purge in dependency order."""
    user = _get_user_or_404(db, user_id)
    # Last-owner guard first so a sole owner deleting itself gets the precise 409
    # ("last owner") rather than the generic 400 ("own account"); both still block.
    if user.role == ROLE_OWNER:
        try:
            assert_not_last_owner(db, user_id)
        except LastOwnerError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if user_id == caller.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    # Children before parents: grants (-> api_keys, users) -> api_keys (-> users)
    # -> invite_codes (-> users) -> user.
    db.query(DeviceAuthorizationGrant).filter(DeviceAuthorizationGrant.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(APIKey).filter(APIKey.user_id == user_id).delete(synchronize_session=False)
    db.query(InviteCode).filter(or_(InviteCode.created_by == user_id, InviteCode.used_by == user_id)).delete(
        synchronize_session=False
    )

    email = user.email
    db.delete(user)
    db.commit()
    return {"success": True, "id": str(user_id), "message": f"User '{email}' deleted"}


@router.patch("/{user_id}/role", response_model=AdminUserResponse)
def set_user_role(
    user_id: UUID,
    role: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    caller: AuthenticatedUser = Depends(require_admin),
) -> User:
    """Change a user's role. Admins may assign any NON-owner role; granting
    ROLE_OWNER requires the caller to be an owner (closes the admin→owner
    privilege-escalation path, T46.4). The last active owner cannot be demoted."""
    if role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid role: {role!r}")
    # Only an owner can mint another owner; a mere admin cannot self-promote or
    # escalate anyone to owner via this endpoint.
    if role == ROLE_OWNER and caller.role != ROLE_OWNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only an owner can grant the owner role",
        )
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
