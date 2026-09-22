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

from app.core.security import ROLE_OWNER, ROLE_SERVICE, AuthenticatedUser
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import DEFAULT_WORKSPACE_ID, Workspace

logger = logging.getLogger(__name__)


def default_workspace_id(db: Session, caller: AuthenticatedUser | None = None) -> UUID | None:
    """Resolve the Space (workspace_id) a newly created resource should belong to.

    T44.4: new projects must not be left space-less (workspace_id NULL), otherwise
    T44.3's membership/inheritance has no Space to resolve. The Space is derived
    server-side here and never trusted from a request body.

    PERSONAL-1 (decision #532): a human ``caller`` (any role but service) gets
    their personal Space, so a new project lands somewhere its creator owns.
    Only POST /projects passes a caller. The service principal, calls without a
    caller, and a human whose personal Space is missing (logged, never a NULL
    Space) get the seeded Default Workspace. Returns the Default Workspace's id
    when that row exists (migration 030 guarantees it in any migrated
    environment), or None when it is absent — degrading gracefully to a NULL
    Space (tolerated by the NULL-safe membership path) instead of failing the FK
    on insert.
    """
    if caller is not None and caller.role != ROLE_SERVICE:
        personal = (
            db.query(Workspace.id).filter(Workspace.personal_owner_id == caller.user_id).first()
            if caller.user_id is not None  # None would compile to IS NULL: a shared Space
            else None
        )
        if personal is not None:
            return personal[0]
        logger.warning(
            "No personal Space for user %s; the new project goes to Default Workspace",
            caller.user_id,
        )
    default = db.query(Workspace).filter(Workspace.id == DEFAULT_WORKSPACE_ID).first()
    return default.id if default is not None else None


def ensure_personal_space(db: Session, user: User) -> Workspace | None:
    """The user's personal Space, created with its membership row on the first call.

    PERSONAL-1 (decision #530): called by the two account-creation routes, POST
    /auth/register and POST /admin/users, and nowhere else. A second call returns
    the existing Space. The service principal gets none. Flushes without
    committing, so the route's commit creates the account and its Space together.
    """
    if user.role == ROLE_SERVICE:
        return None
    space = db.query(Workspace).filter(Workspace.personal_owner_id == user.id).first()
    if space is None:
        space = Workspace(name=f"{user.display_name}'s Space", personal_owner_id=user.id)
        db.add(space)
        db.flush()
        db.add(SpaceMember(workspace_id=space.id, user_id=user.id))
        db.flush()
    return space


def project_owner_workspace(
    db: Session, project_id: UUID | None
) -> tuple[UUID | None, UUID | None]:
    """The (owner_id, workspace_id) a resource created UNDER a project should inherit.

    For BACKGROUND create paths with no human caller (T48.4: DeepSearch auto-ingest
    and report promotion) — the new document inherits its parent project's owner +
    Space so it is visible to exactly the same principals as the project the instant
    rbac_enabled flips, instead of being minted NULL-owner and going invisible to
    non-admins. Returns ``(None, None)`` when project_id is None or the project is
    missing — fail-safe: leave the row unattributed rather than mis-attributed (the
    037 backfill mops up any NULL stragglers).
    """
    if project_id is None:
        return (None, None)
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return (None, None)
    return (project.owner_id, project.workspace_id)


class LastOwnerError(Exception):
    """Raised when an operation would remove the final owner.

    The admin user-management API (T43.5) maps this to a 4xx response.
    """


class BootstrapIdentityError(Exception):
    """Raised when AUTH_USERNAME is not an email address (Sprint 55 RBAC-1).

    The old derivation turned a bare ``AUTH_USERNAME`` into
    ``<username>@tracelab.local``. That is not a harmless placeholder: in
    production it minted a real ``users`` row holding the irreducible ``owner``
    role at a domain reserved by RFC 6761, which nothing can route mail to and
    no human can be reached at. Refuse to invent an identity instead.
    """


def bootstrap_owner_email() -> str:
    """Email of the configured bootstrap user (Derek / AUTH_USERNAME).

    Reads AUTH_USERNAME from the environment directly (NOT pydantic settings),
    exactly as migrations 023/031 do, so the resolved email matches the SEEDED
    user even when AUTH_USERNAME is configured only via .env (which pydantic reads
    but ``os.environ`` does not). Email is the unique key.

    AUTH_USERNAME must already BE an email address. Sprint 55 RBAC-1 removed the
    ``<username>@tracelab.local`` fallback: a bare username raises
    ``BootstrapIdentityError`` rather than fabricating an account at a
    non-routable domain. The email case is unchanged, byte for byte.
    """
    username = os.environ.get("AUTH_USERNAME", "tracelab-admin")
    if "@" not in username:
        raise BootstrapIdentityError(
            f"AUTH_USERNAME must be an email address; got {username!r}. "
            f"TraceLab no longer derives {username}@tracelab.local — that domain "
            "is non-routable (RFC 6761), so the account it creates can never "
            "receive mail or be recovered. Set AUTH_USERNAME to the bootstrap "
            "owner's real email address."
        )
    return username


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
    """True if ``user_id`` is an owner and no other ACTIVE owner exists.

    Sprint C (T46.3): only ``is_active`` owners count as a fallback, because a
    soft-disabled owner can no longer log in (is_active is enforced at every auth
    path). So disabling or demoting the last *active* owner is blocked even when
    other — but disabled — owners exist; otherwise owner administration could be
    locked out the moment the flag flips.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role != ROLE_OWNER:
        return False
    other_active_owners = (
        db.query(User)
        .filter(
            User.role == ROLE_OWNER,
            User.is_active.is_(True),
            User.id != user_id,
        )
        .count()
    )
    return other_active_owners == 0


def assert_not_last_owner(db: Session, user_id: UUID) -> None:
    """Raise ``LastOwnerError`` if demoting/deleting ``user_id`` removes the final owner.

    Hard constraint: never lock out the owner. Callers (T43.5 admin API) invoke
    this before changing an owner's role away from 'owner' or deleting an owner.
    """
    if is_last_owner(db, user_id):
        raise LastOwnerError("Cannot remove or demote the last remaining owner")
