"""Ownership bootstrap + last-owner guard (Sprint 43 T43.3).

These helpers back the RBAC ownership model:

- ``ensure_owner_bootstrap`` is the idempotent startup safety net that guarantees
  at least one ``owner`` always exists, so the system can never be locked out of
  owner-level administration. The authoritative one-time promotion happens in
  Alembic migration 031; this is the defensive net for fresh/edge databases.
- ``is_last_owner`` / ``assert_not_last_owner`` enforce the "the last owner can
  never be demoted or deleted" hard constraint. The admin user-management API
  (T43.5) calls ``assert_not_last_owner`` before demoting or deleting a user.

Sprint 43 has ZERO role enforcement, so promoting the bootstrap user admin->owner
has no behavioral effect today (owner outranks admin and nothing gates on role).
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import ROLE_OWNER
from app.models.user import User

logger = logging.getLogger(__name__)


class LastOwnerError(Exception):
    """Raised when an operation would remove the final owner.

    The admin user-management API (T43.5) maps this to a 4xx response.
    """


def bootstrap_owner_email() -> str:
    """Email of the configured bootstrap user (Derek / AUTH_USERNAME).

    Reads AUTH_USERNAME from the environment directly (NOT pydantic settings),
    exactly as migrations 023/031 do, so the resolved email matches the SEEDED
    user even when AUTH_USERNAME is configured only via .env (which pydantic reads
    but ``os.environ`` does not). Derivation: the raw username if it already looks
    like an email, otherwise ``<username>@tracelab.local``. Email is the unique key.
    """
    username = os.environ.get("AUTH_USERNAME", "tracelab-admin")
    return username if "@" in username else f"{username}@tracelab.local"


def ensure_owner_bootstrap(db: Session) -> bool:
    """Guarantee at least one owner exists. Idempotent.

    No-op (returns False) if any user already has role 'owner'. Otherwise promotes
    the bootstrap user — resolved by unique email, falling back to the
    earliest-created user — to 'owner' and returns True. Returns False when there
    are no users at all (nothing to promote).
    """
    if db.query(User).filter(User.role == ROLE_OWNER).count() > 0:
        return False  # an owner already exists — nothing to do

    # Reached only on a fresh/edge DB (in prod migration 031 already promoted an
    # owner, so the count guard above short-circuits). id is a deterministic
    # secondary sort so the fallback can't flip on a created_at tie.
    user = (
        db.query(User).filter(User.email == bootstrap_owner_email()).first()
        or db.query(User).order_by(User.created_at.asc(), User.id.asc()).first()
    )
    if user is None:
        return False  # empty users table — nothing to promote

    user.role = ROLE_OWNER
    db.commit()
    logger.info("Owner bootstrap: promoted user %s to '%s'", user.email, ROLE_OWNER)
    return True


def is_last_owner(db: Session, user_id: UUID) -> bool:
    """True if ``user_id`` is an owner and no other owner exists."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role != ROLE_OWNER:
        return False
    other_owners = db.query(User).filter(User.role == ROLE_OWNER, User.id != user_id).count()
    return other_owners == 0


def assert_not_last_owner(db: Session, user_id: UUID) -> None:
    """Raise ``LastOwnerError`` if demoting/deleting ``user_id`` removes the final owner.

    Hard constraint: never lock out the owner. Callers (T43.5 admin API) invoke
    this before changing an owner's role away from 'owner' or deleting an owner.
    """
    if is_last_owner(db, user_id):
        raise LastOwnerError("Cannot remove or demote the last remaining owner")
