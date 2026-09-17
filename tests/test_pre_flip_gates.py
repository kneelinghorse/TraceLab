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

    def test_bare_username_is_refused_instead_of_fabricated(self, monkeypatch):
        # Sprint 55 RBAC-1: this used to return "tracelab-admin@tracelab.local".
        # That derivation minted the production owner row at a non-routable
        # domain, so a bare username is now a hard error, not a default.
        from app.services.ownership import (
            BootstrapIdentityError,
            bootstrap_owner_email,
        )

        monkeypatch.setenv("AUTH_USERNAME", "tracelab-admin")
        with pytest.raises(BootstrapIdentityError) as exc:
            bootstrap_owner_email()
        # The operator must be told what to do, not just that something failed.
        assert "tracelab-admin" in str(exc.value)
        assert "email address" in str(exc.value)

    def test_default_when_unset_is_refused(self, monkeypatch):
        # The absent-AUTH_USERNAME default ('tracelab-admin') is itself a bare
        # username, so an unconfigured deploy now fails loudly rather than
        # silently bootstrapping a stray owner at @tracelab.local.
        from app.services.ownership import (
            BootstrapIdentityError,
            bootstrap_owner_email,
        )

        monkeypatch.delenv("AUTH_USERNAME", raising=False)
        with pytest.raises(BootstrapIdentityError):
            bootstrap_owner_email()


# --- Gate 6b: the migration-side half of the same refusal (Sprint 56 HYG-2) -----


def _load_migration(filename: str):
    """Import an Alembic revision by path (module names start with a digit)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{filename[:3]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGate6bMigrationBootstrapIdentity:
    """Runtime refusing a bare AUTH_USERNAME is only half the fix.

    app/services/ownership.py raises at request time, but migration 023 is what
    CREATES the row. Until it refuses too, a fresh provision with a bare
    AUTH_USERNAME silently mints a new ``<username>@tracelab.local`` owner — the
    exact account Sprint 55 RBAC-1 spent a mission demoting. Next-step #368.
    """

    def test_email_username_is_seeded_verbatim(self):
        mig = _load_migration("023_add_users_table.py")
        assert mig.seed_admin_email("derek@deniedart.com") == "derek@deniedart.com"

    def test_bare_username_is_refused_not_fabricated(self):
        mig = _load_migration("023_add_users_table.py")
        with pytest.raises(mig.BootstrapIdentityError) as exc:
            mig.seed_admin_email("tracelab-admin")
        message = str(exc.value)
        # An operator who hits this at provision time must learn what to change.
        assert "tracelab-admin" in message
        assert "email address" in message
        assert "AUTH_USERNAME" in message

    def test_023_is_the_only_migration_that_creates_a_user(self):
        """The three backfills may KEEP the derivation; they must not mint with it.

        031/037/038 derive the same legacy address on purpose, to resolve a row a
        pre-Sprint-55 023 created. That is safe only while they cannot create one,
        so lock it: if a future migration starts INSERTing into users, it has to
        come here and decide deliberately whether the refusal applies to it too.
        """
        import re
        from pathlib import Path

        versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
        inserts_users = re.compile(r"INSERT\s+INTO\s+users", re.IGNORECASE)

        creators = sorted(
            path.name
            for path in versions.glob("*.py")
            if inserts_users.search(path.read_text())
        )
        assert creators == ["023_add_users_table.py"], (
            "a migration other than 023 now creates a users row: " f"{creators}"
        )

    def test_backfills_that_keep_the_derivation_only_read(self):
        """Each derivation site outside 023 must be lookup-only."""
        from pathlib import Path

        versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
        derivers = {
            "031_backfill_ownership.py",
            "037_backfill_doc_coll_owner.py",
            "038_backfill_mission_report.py",
        }
        for name in sorted(derivers):
            source = (versions / name).read_text()
            assert "@tracelab.local" in source, (
                f"{name} no longer derives the legacy address; if that was "
                "deliberate, update this test and confirm legacy databases still "
                "resolve their bootstrap owner"
            )
            assert "INSERT INTO users" not in source.upper().replace("  ", " ")
