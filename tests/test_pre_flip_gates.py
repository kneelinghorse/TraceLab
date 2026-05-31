"""Pre-flip verification — gates 2 & 6 (Sprint C, T46.5).

These are VERIFY-not-build checks that must be green before T46.6 flips
rbac_enabled=ON. The authorize() policy and route wiring are tested elsewhere;
this file locks the two subtle correctness gates from the pre-flip checklist:

  * Gate 2 — the owner allow-path equality ``resource.owner_id == user.user_id``
    is UUID-vs-UUID on EVERY auth path. A string owner_id would silently
    false-DENY the true owner (then deny-by-default locks them out). We prove both
    the positive (UUID==UUID allows) and the failure mode (str != UUID denies), and
    that resolved principals + the ORM column are genuinely uuid.UUID.
  * Gate 6 — owner-bootstrap identity parity: bootstrap_owner_email() (runtime) must
    derive the SAME email as Alembic migration 031 (migration-time), or the flip
    could bootstrap a different owner than the backfill. Idempotency itself is
    covered in tests/test_ownership.py::TestEnsureOwnerBootstrap.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.authorization import authorize
from app.core.config import settings
from app.core.security import (
    ROLE_MEMBER,
    AuthenticatedUser,
    _resolve_user_from_jwt,
    _validate_api_key,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.models.api_key import APIKey
from app.models.project import Project
from app.models.user import User

_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _make_user(db) -> User:
    user = User(
        email=f"{uuid4()}@x.io", display_name="u", password_hash=_HASH, role=ROLE_MEMBER
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Gate 2: owner_id == user_id is UUID-vs-UUID ----------------------------


class TestGate2UuidEquality:
    def test_uuid_equality_allows_owner(self, rbac_on):
        uid = uuid4()
        user = AuthenticatedUser(user_id=uid, email="o@x", display_name="o", role=ROLE_MEMBER)
        resource = SimpleNamespace(owner_id=uid, workspace_id=None)  # UUID owner_id
        assert authorize(user, "read", resource) is True

    def test_string_owner_id_would_false_deny(self, rbac_on):
        # The teeth: if owner_id were stored/compared as a STRING, the equality
        # against a UUID user_id is False -> the real owner is wrongly DENIED. This
        # is exactly the gate-2 hazard (decision #245(2)); it must stay impossible.
        uid = uuid4()
        user = AuthenticatedUser(user_id=uid, email="o@x", display_name="o", role=ROLE_MEMBER)
        resource = SimpleNamespace(owner_id=str(uid), workspace_id=None)
        assert authorize(user, "read", resource) is False

    def test_jwt_resolved_principal_user_id_is_uuid(self, db_session):
        user = _make_user(db_session)
        resolved = _resolve_user_from_jwt(str(user.id))
        assert isinstance(resolved.user_id, UUID)
        assert resolved.user_id == user.id

    def test_api_key_resolved_principal_user_id_is_uuid(self, db_session):
        user = _make_user(db_session)
        plain = generate_api_key()
        db_session.add(
            APIKey(
                user_id=user.id,
                name="k",
                key_hash=hash_api_key(plain),
                key_prefix=get_key_prefix(plain),
            )
        )
        db_session.commit()
        resolved = _validate_api_key(plain)
        assert resolved is not None
        assert isinstance(resolved.user_id, UUID)

    def test_project_owner_id_column_is_uuid(self, db_session):
        user = _make_user(db_session)
        project = Project(name="p", owner_id=user.id)
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        assert isinstance(project.owner_id, UUID)


# --- Gate 6: bootstrap identity parity (migration 031 <-> runtime) ----------


class TestGate6BootstrapParity:
    def test_username_with_at_is_used_verbatim(self, monkeypatch):
        from app.services.ownership import bootstrap_owner_email

        monkeypatch.setenv("AUTH_USERNAME", "derek@deniedart.com")
        assert bootstrap_owner_email() == "derek@deniedart.com"

    def test_bare_username_gets_tracelab_local_suffix(self, monkeypatch):
        from app.services.ownership import bootstrap_owner_email

        monkeypatch.setenv("AUTH_USERNAME", "tracelab-admin")
        assert bootstrap_owner_email() == "tracelab-admin@tracelab.local"

    def test_default_when_unset_matches_migration_default(self, monkeypatch):
        # Migration 031 and runtime both default to 'tracelab-admin' when AUTH_USERNAME
        # is absent — keep them in lockstep so the flip can't bootstrap a stray owner.
        from app.services.ownership import bootstrap_owner_email

        monkeypatch.delenv("AUTH_USERNAME", raising=False)
        assert bootstrap_owner_email() == "tracelab-admin@tracelab.local"
