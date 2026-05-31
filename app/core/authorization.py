"""Centralized authorization policy (Sprint 43 T43.6; Space membership T44.3).

``authorize`` is the single RBAC chokepoint. It is gated by the ``rbac_enabled``
config flag (default OFF): while OFF it is a pass-through no-op that allows
everything, so day-one behavior is byte-identical (ZERO enforcement). Sprint C
flips the flag ON to activate the deny-by-default policy below, AFTER the owner is
bootstrapped. NO route calls this yet — wiring it into routes is Sprint C.

Policy when enabled (deny-by-default):
  1. owner / admin tier            -> allow (full access)
  2. the resource's owner          -> allow (resource.owner_id == caller)
  3. Space membership over resource -> allow (caller is a member of the
     resource's effective Space; child resources inherit their owning project's
     Space via project_id -> space_id). Requires a DB session; without one this
     branch fails closed.
  4. otherwise                     -> deny
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import ROLE_ADMIN, ROLE_OWNER, AuthenticatedUser

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Tier with unconditional access under the enabled policy.
_PRIVILEGED_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN})

# Sentinel distinguishing "resource has no project_id column at all" (top-level
# Project/Collection) from "resource has a project_id column whose value is NULL"
# (an orphan child Mission/Report). getattr(..., None) collapses both to None;
# they need opposite handling, so we probe with a unique object instead.
_NO_PROJECT_FK = object()


def _effective_space_id(resource: object, db: Session) -> object | None:
    """Resolve the Space (workspace_id) that governs access to ``resource``.

    A child resource (one carrying ``project_id``) inherits its access Space from
    the owning project: project_id -> projects.workspace_id (downward inheritance,
    architecture #196). A top-level resource (e.g. a Project, which has no
    project_id) uses its own ``workspace_id``.

    An *orphan* child — one that has a ``project_id`` column but whose value is
    NULL — cannot resolve an owning project, so it fails closed (returns None) per
    decision #260(b). It MUST NOT fall back to its own denormalized
    ``workspace_id``; doing so would let any member of the child's own Space reach
    a resource that has been detached from every project.

    Returns None when the Space cannot be resolved (no/NULL workspace_id, missing
    project, orphan child, None resource) — callers must treat None as "no
    membership" (fail-closed).
    """
    project_id = getattr(resource, "project_id", _NO_PROJECT_FK)
    if project_id is _NO_PROJECT_FK:
        # Top-level resource (e.g. Project/Collection): no project_id column at
        # all -> governed by its own Space.
        return getattr(resource, "workspace_id", None)
    if project_id is None:
        # Orphan child: has a project_id column but it is NULL -> no owning
        # project to inherit from -> fail closed (decision #260b).
        return None

    # Child resource with a real project_id: the owning project's Space is
    # authoritative, NOT the child's own (denormalized) workspace_id column.
    from app.models.project import Project

    project = db.get(Project, project_id)
    return getattr(project, "workspace_id", None) if project is not None else None


def _has_space_membership(
    user: AuthenticatedUser, resource: object, db: Session
) -> bool:
    """Whether ``user`` has access via Space membership over ``resource``.

    Resolves the resource's effective Space (own workspace_id, or the owning
    project's workspace_id for child resources) and checks for a space_members row
    granting ``user`` membership of that Space. Fails closed on every
    None/NULL/unknown path: an unresolved Space, or a missing user_id, denies.
    """
    user_id = getattr(user, "user_id", None)
    if user_id is None:
        return False

    space_id = _effective_space_id(resource, db)
    if space_id is None:
        return False  # NULL/unknown Space -> no membership (fail-closed)

    from app.models.space_member import SpaceMember

    membership = (
        db.query(SpaceMember)
        .filter(
            SpaceMember.workspace_id == space_id,
            SpaceMember.user_id == user_id,
        )
        .first()
    )
    return membership is not None


def authorize(
    user: AuthenticatedUser,
    action: str,
    resource: object,
    db: Session | None = None,
) -> bool:
    """Return whether ``user`` may perform ``action`` on ``resource``.

    No-op pass-through (returns True) while ``settings.rbac_enabled`` is False — the
    Sprint 43 default — so enabling RBAC is a single flag flip. ``action`` is part of
    the contract for Sprint C action-level policy; the current policy does not branch
    on it (privileged roles and the resource owner are allowed for every action).

    ``db`` is required only to evaluate the Space-membership allow path (Sprint C
    routes pass their request session). When the policy reaches that branch without
    a session it fails closed (deny) rather than touching a global session — the
    safe direction if a call site forgets to pass ``db``.
    """
    if not settings.rbac_enabled:
        return True  # zero-enforcement: allow everything (byte-identical day-one)

    # --- deny-by-default policy (active only when the flag is ON) ---
    if user.role in _PRIVILEGED_ROLES:
        return True

    owner_id = getattr(resource, "owner_id", None)
    if owner_id is not None and owner_id == user.user_id:
        return True

    # Space membership is the final allow path; it needs a DB session to resolve
    # the Space and read space_members. No session -> fail closed.
    if db is None:
        return False
    return _has_space_membership(user, resource, db)


def authorize_or_403(
    user: AuthenticatedUser,
    action: str,
    resource: object,
    db: Session,
) -> None:
    """Authorize ``user`` for ``action`` on ``resource`` or raise HTTP 403.

    Imperative wrapper over :func:`authorize` for route call sites (Sprint C
    T46.2). The route loads the resource (returning 404 itself if it is absent),
    then calls this immediately before reading/mutating it. The request session is
    threaded through so the Space-membership branch can resolve; all fail-closed
    semantics are inherited from ``authorize``.

    While ``rbac_enabled`` is False ``authorize`` is a no-op (returns True), so
    this never raises and wired routes stay byte-identical to pre-Sprint-C
    behaviour for the *authorization* layer. (Authentication, added to the same
    routes, is independent of the flag.)
    """
    if not authorize(user, action, resource, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this resource.",
        )
