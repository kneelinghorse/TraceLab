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
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import ROLE_ADMIN, ROLE_OWNER, ROLE_SERVICE, AuthenticatedUser

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Version stamp for the authorization policy below. Surfaced by GET
# /admin/rbac-status (T47.1) and logged at startup so operators can confirm WHICH
# policy a deploy is running. Bump this whenever the authorize() policy changes
# (roles, allow paths, or fail-closed semantics) so the change is observable.
POLICY_VERSION = "1.0"

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


def is_service_principal(user: AuthenticatedUser) -> bool:
    """True iff ``user`` is a service principal (machine identity, role 'service')."""
    return getattr(user, "role", None) == ROLE_SERVICE


def authorize_service_or_403(
    user: AuthenticatedUser,
    *,
    enforce_when_disabled: bool = False,
) -> None:
    """Require a SERVICE principal for a service-to-service write, or raise HTTP 403.

    Gates the trusted-origin WRITE surfaces (T47.4) — e.g. POST
    /missions/{id}/logs, called by the DeepSearch runner — so a human-auth token can
    no longer append/spoof records there (the BOLA gap decision #260(3) deferred).
    Unlike :func:`authorize`, this is NOT satisfied by the owner/admin tier: ONLY a
    ``role == 'service'`` principal passes; EVERY human role (viewer/member/admin/
    owner) is denied. A service principal, in turn, is fail-closed everywhere else
    (it is not in _PRIVILEGED_ROLES, owns no resources, and is in no Space), so it
    can do nothing but the service writes it is explicitly granted.

    Legacy service routes remain a no-op while ``rbac_enabled`` is False. New
    cross-tenant machine-only routes pass ``enforce_when_disabled=True`` so the
    service-role boundary is unconditional and cannot be widened by the feature
    flag. The distinction is explicit at each call site and regression-tested.
    """
    if not settings.rbac_enabled and not enforce_when_disabled:
        return
    if not is_service_principal(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a service principal.",
        )


def _user_space_ids(user: AuthenticatedUser, db: Session) -> list:
    """The workspace_ids ``user`` is a member of (empty list when none / no user_id)."""
    from app.models.space_member import SpaceMember

    user_id = getattr(user, "user_id", None)
    if user_id is None:
        return []
    rows = (
        db.query(SpaceMember.workspace_id)
        .filter(SpaceMember.user_id == user_id)
        .all()
    )
    return [row[0] for row in rows]


def accessible_filter(user: AuthenticatedUser, model: type, db: Session):
    """Query-level companion to :func:`authorize` for LIST endpoints (T47.3).

    Returns a SQLAlchemy boolean expression selecting the rows ``user`` may READ, or
    ``None`` meaning "no filter" (all rows). Apply it INSIDE the list query, before
    count + pagination, so lists stay pagination-safe AND consistent with the per-id
    ``authorize`` policy (the per-id flip deliberately left lists unfiltered — this
    closes that cross-tenant read leak, #262). The returned expression embeds literal
    space ids, so it is session-agnostic (services that use their own session can
    apply a filter built from the request session).

    Mirrors ``authorize``'s read allow-paths exactly:
      * ``rbac_enabled`` False -> ``None`` (byte-identical: every row, like authorize)
      * owner / admin tier      -> ``None`` (full access)
      * else: ``owner_id == caller``  OR  membership over the row's effective Space:
          - top-level row (no project_id, has workspace_id): ``workspace_id IN`` my
            spaces;
          - child row (has project_id): ``project_id IN`` (projects in my spaces);
            an orphan (project_id NULL) is excluded by ``IN`` -> fail closed (#260b).
        A model exposing NEITHER an owner_id NOR a resolvable Space column yields
        ``false()`` (the caller sees nothing) — never a silent all-rows.

    MODEL-PARITY POLICY (T47.3, decided in lieu of new owner_id/workspace_id columns):
    child models that carry a NOT-NULL ``project_id`` are governed VIA THEIR PARENT
    project's Space — Insight and IngestionJob qualify, so no migration is needed and
    ``authorize``/this filter cover them uniformly via the project_id branch.
    SavedSearch is governed by its own ``owner`` (username) column and is scoped at
    its own endpoint, so it is intentionally NOT passed through this helper.
    """
    if not settings.rbac_enabled:
        return None
    if user.role in _PRIVILEGED_ROLES:
        return None

    from sqlalchemy import false, or_, select

    conditions = []
    owner_id_col = getattr(model, "owner_id", None)
    if owner_id_col is not None:
        conditions.append(owner_id_col == user.user_id)

    space_ids = _user_space_ids(user, db)
    if space_ids:
        project_id_col = getattr(model, "project_id", None)
        if project_id_col is not None:
            # Child resource: governed by the OWNING project's Space, not its own
            # denormalized workspace_id (mirrors _effective_space_id). Orphans
            # (project_id NULL) are excluded by IN -> fail closed.
            from app.models.project import Project

            accessible_projects = select(Project.id).where(Project.workspace_id.in_(space_ids))
            conditions.append(project_id_col.in_(accessible_projects))
        else:
            workspace_id_col = getattr(model, "workspace_id", None)
            if workspace_id_col is not None:
                conditions.append(workspace_id_col.in_(space_ids))

    if not conditions:
        return false()  # no owner_id, no resolvable Space -> caller sees nothing
    return or_(*conditions)


def accessible_project_ids(
    user: AuthenticatedUser, db: Session
) -> list[UUID] | None:
    """Return the projects readable by ``user`` for non-relational backends.

    This is the project-ID companion to :func:`accessible_filter` for stores such
    as Qdrant, where a SQLAlchemy expression cannot be applied directly. ``None``
    means unrestricted access (RBAC disabled, or an owner/admin principal). An
    ordinary human principal receives projects they own OR projects governed by a
    Space they belong to. Service principals and principals with no matching
    ownership/membership grants receive an empty list so callers can fail closed.
    """
    if not settings.rbac_enabled:
        return None
    if user.role in _PRIVILEGED_ROLES:
        return None
    if user.role == ROLE_SERVICE:
        return []

    user_id = getattr(user, "user_id", None)
    if user_id is None:
        return []

    from sqlalchemy import or_

    from app.models.project import Project

    conditions = [Project.owner_id == user_id]
    space_ids = _user_space_ids(user, db)
    if space_ids:
        conditions.append(Project.workspace_id.in_(space_ids))

    rows = (
        db.query(Project.id)
        .filter(Project.deleted_at.is_(None), or_(*conditions))
        .all()
    )
    return [row[0] for row in rows]
