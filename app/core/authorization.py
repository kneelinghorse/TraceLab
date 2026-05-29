"""Centralized authorization policy (Sprint 43 T43.6).

``authorize`` is the single RBAC chokepoint. It is gated by the ``rbac_enabled``
config flag (default OFF): while OFF it is a pass-through no-op that allows
everything, so day-one behavior is byte-identical (ZERO enforcement). Sprint C
flips the flag ON to activate the deny-by-default policy below, AFTER the owner is
bootstrapped. NO route calls this yet — wiring it into routes is Sprint C.

Policy when enabled (deny-by-default):
  1. owner / admin tier            -> allow (full access)
  2. the resource's owner          -> allow (resource.owner_id == caller)
  3. Space membership over resource -> allow (STUBBED until Sprint B; denies today)
  4. otherwise                     -> deny
"""

from __future__ import annotations

from app.core.config import settings
from app.core.security import ROLE_ADMIN, ROLE_OWNER, AuthenticatedUser

# Tier with unconditional access under the enabled policy.
_PRIVILEGED_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN})


def _has_space_membership(user: AuthenticatedUser, resource: object) -> bool:
    """Whether the caller has access via Space membership over the resource.

    Stubbed: Spaces (the access-grant unit) arrive in Sprint B, so this always
    returns False today. Sprint B/C implement the space_members lookup with
    downward inheritance (project_id -> space_id).
    """
    return False


def authorize(user: AuthenticatedUser, action: str, resource: object) -> bool:
    """Return whether ``user`` may perform ``action`` on ``resource``.

    No-op pass-through (returns True) while ``settings.rbac_enabled`` is False — the
    Sprint 43 default — so enabling RBAC is a single flag flip. ``action`` is part of
    the contract for Sprint C action-level policy; the current policy does not branch
    on it (privileged roles and the resource owner are allowed for every action).
    """
    if not settings.rbac_enabled:
        return True  # zero-enforcement: allow everything (byte-identical day-one)

    # --- deny-by-default policy (active only when the flag is ON) ---
    if user.role in _PRIVILEGED_ROLES:
        return True

    owner_id = getattr(resource, "owner_id", None)
    if owner_id is not None and owner_id == user.user_id:
        return True

    # Space membership is the final allow path (stubbed until Sprint B); otherwise deny.
    return _has_space_membership(user, resource)
