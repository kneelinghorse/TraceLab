"""Tests for role-based authorization helpers (Sprint 43 T43.1).

Covers:
- The role hierarchy ranking (viewer < member < admin < owner).
- require_admin / require_role dependency helpers (allow + deny paths).
- The users.role read path: role is populated on the AuthenticatedUser
  principal through BOTH auth resolvers (JWT and API key).

Sprint 43 surfaces role on the principal and defines these helpers but does
NOT gate any route with them — enforcement is Sprint C.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.core.security import (
    _ROLE_RANK,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    AuthenticatedUser,
    _resolve_user_from_jwt,
    _validate_api_key,
    generate_api_key,
    get_configured_credentials,
    get_key_prefix,
    hash_api_key,
    require_admin,
    require_role,
)
from app.models.api_key import APIKey
from app.models.user import User

# Not a real credential — these tests never authenticate by password, they only
# need a non-null value for the NOT NULL users.password_hash column.
_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"


def _principal(role: str) -> AuthenticatedUser:
    """Build a principal with the given role for direct dependency calls."""
    return AuthenticatedUser(
        user_id=uuid4(),
        email="user@example.com",
        display_name="user",
        role=role,
    )


@pytest.mark.unit
class TestRoleHierarchy:
    """The role ranking is the single source of truth for 'at least' checks."""

    def test_rank_is_strictly_ascending(self):
        # WHY: require_role relies on this ordering to let a higher role satisfy
        # a lower requirement. If the ranking is not strictly ascending, an admin
        # could fail a 'member' gate (or a viewer pass an 'admin' gate).
        assert _ROLE_RANK[ROLE_VIEWER] < _ROLE_RANK[ROLE_MEMBER] < _ROLE_RANK[ROLE_ADMIN] < _ROLE_RANK[ROLE_OWNER]

    def test_exactly_the_four_locked_roles_are_ranked(self):
        # WHY: the architecture (locked 2026-05-28) defines exactly four roles.
        # An extra/missing entry here means the principal could carry a role the
        # hierarchy does not understand, which must fail closed (tested below).
        assert set(_ROLE_RANK) == {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER}


@pytest.mark.unit
class TestRequireAdmin:
    """require_admin allows admin + owner, denies everyone else with 403."""

    @pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_OWNER])
    def test_admin_and_owner_allowed(self, role):
        principal = _principal(role)
        # Returns the SAME principal so downstream handlers can use it.
        assert require_admin(user=principal) is principal

    @pytest.mark.parametrize("role", [ROLE_MEMBER, ROLE_VIEWER, "ghost"])
    def test_lower_or_unknown_role_denied(self, role):
        # WHY: an authenticated-but-insufficient caller is 403 (forbidden), not
        # 401 (unauthenticated). Unknown roles must also be denied (fail closed).
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user=_principal(role))
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Admin role required" in exc_info.value.detail


@pytest.mark.unit
class TestRequireRole:
    """require_role(minimum) is a hierarchical 'at least this role' gate."""

    def test_higher_role_satisfies_lower_requirement(self):
        # WHY: the hierarchy is cumulative — owner/admin must pass a 'member' gate.
        dependency = require_role(ROLE_MEMBER)
        for role in (ROLE_MEMBER, ROLE_ADMIN, ROLE_OWNER):
            principal = _principal(role)
            assert dependency(user=principal) is principal

    def test_lower_role_denied(self):
        dependency = require_role(ROLE_ADMIN)
        for role in (ROLE_VIEWER, ROLE_MEMBER):
            with pytest.raises(HTTPException) as exc_info:
                dependency(user=_principal(role))
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "admin" in exc_info.value.detail

    def test_owner_requirement_only_satisfied_by_owner(self):
        dependency = require_role(ROLE_OWNER)
        assert dependency(user=_principal(ROLE_OWNER)).role == ROLE_OWNER
        for role in (ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER):
            with pytest.raises(HTTPException) as exc_info:
                dependency(user=_principal(role))
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_requirement_satisfied_by_every_known_role(self):
        dependency = require_role(ROLE_VIEWER)
        for role in (ROLE_VIEWER, ROLE_MEMBER, ROLE_ADMIN, ROLE_OWNER):
            assert dependency(user=_principal(role)).role == role

    def test_unknown_principal_role_denied_even_at_lowest_requirement(self):
        # WHY: a garbage/legacy role must never pass any gate — fail closed.
        dependency = require_role(ROLE_VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            dependency(user=_principal("ghost"))
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_minimum_role_raises_at_wiring_time(self):
        # WHY: a typo in the required role should blow up when the route is wired
        # (startup), not silently produce a gate that no one can ever pass.
        with pytest.raises(KeyError):
            require_role("superadmin")


class TestRolePrincipalReadPath:
    """role flows from users.role into the principal via BOTH auth resolvers.

    Not marked @pytest.mark.unit so the autouse fixture seeds the admin user
    and provides a clean schema (these tests hit the database).
    """

    def test_seed_admin_role_resolves_via_jwt(self, db_session):
        # Success criterion: users.role read path verified for the seed admin.
        username = get_configured_credentials().username
        seed = db_session.query(User).filter(User.display_name == username).first()
        assert seed is not None, "autouse fixture should have seeded the admin user"

        principal = _resolve_user_from_jwt(str(seed.id))
        assert principal.role == "admin"

    def test_non_default_role_resolves_via_jwt(self, db_session):
        # Proves the JWT path carries an arbitrary (non-'admin') role through.
        viewer = User(
            email="viewer@example.com",
            display_name="viewer-user",
            password_hash=_PLACEHOLDER_HASH,
            role=ROLE_VIEWER,
        )
        db_session.add(viewer)
        db_session.commit()
        db_session.refresh(viewer)

        principal = _resolve_user_from_jwt(str(viewer.id))
        assert principal.role == ROLE_VIEWER

    def test_legacy_display_name_jwt_path_carries_role(self, db_session):
        # The legacy display_name-subject fallback is a third construction site.
        member = User(
            email="legacy-member@example.com",
            display_name="legacy-member",
            password_hash=_PLACEHOLDER_HASH,
            role=ROLE_MEMBER,
        )
        db_session.add(member)
        db_session.commit()

        principal = _resolve_user_from_jwt("legacy-member")
        assert principal.role == ROLE_MEMBER

    def test_role_resolves_via_api_key(self, db_session):
        # Success criterion: role populated for the API-key auth path too.
        member = User(
            email="apikey-member@example.com",
            display_name="apikey-member",
            password_hash=_PLACEHOLDER_HASH,
            role=ROLE_MEMBER,
        )
        db_session.add(member)
        db_session.commit()
        db_session.refresh(member)

        raw_key = generate_api_key()
        db_session.add(
            APIKey(
                user_id=member.id,
                name="test key",
                key_hash=hash_api_key(raw_key),
                key_prefix=get_key_prefix(raw_key),
            )
        )
        db_session.commit()

        principal = _validate_api_key(raw_key)
        assert principal is not None
        assert principal.role == ROLE_MEMBER
