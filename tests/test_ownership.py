"""Tests for ownership bootstrap + last-owner guard (Sprint 43 T43.3).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the role='admin'
bootstrap user and builds the schema. Covers:
- ensure_owner_bootstrap: promotes the bootstrap user when no owner exists,
  is idempotent, no-ops when an owner already exists, falls back to the oldest
  user, and no-ops on an empty users table.
- is_last_owner / assert_not_last_owner: the "never lock out the owner" guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER
from app.models.user import User
from app.services.ownership import (
    LastOwnerError,
    assert_not_last_owner,
    bootstrap_owner_email,
    ensure_owner_bootstrap,
    is_last_owner,
)

# Not a real credential — only a non-null value for the NOT NULL password_hash column.
_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"


def _make_user(db, email, role):
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=_PLACEHOLDER_HASH,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _owner_count(db):
    return db.query(User).filter(User.role == ROLE_OWNER).count()


class TestEnsureOwnerBootstrap:
    def test_promotes_bootstrap_user_when_no_owner(self, db_session):
        # autouse fixture seeds one role='admin' user; no owner exists yet.
        assert _owner_count(db_session) == 0
        assert ensure_owner_bootstrap(db_session) is True
        seed = db_session.query(User).filter(User.email == bootstrap_owner_email()).first()
        assert seed is not None and seed.role == ROLE_OWNER

    def test_idempotent_noop_on_second_call(self, db_session):
        ensure_owner_bootstrap(db_session)  # promotes the seed admin
        assert _owner_count(db_session) == 1
        assert ensure_owner_bootstrap(db_session) is False  # pure no-op
        assert _owner_count(db_session) == 1

    def test_noop_when_a_different_owner_already_exists(self, db_session):
        _make_user(db_session, "owner@example.com", ROLE_OWNER)
        seed = db_session.query(User).filter(User.email == bootstrap_owner_email()).first()
        assert ensure_owner_bootstrap(db_session) is False
        db_session.refresh(seed)
        assert seed.role == ROLE_ADMIN  # bootstrap user NOT promoted; owner already exists

    def test_falls_back_to_oldest_user_when_bootstrap_email_absent(self, db_session):
        # No user matches the bootstrap email -> promote the oldest-created user.
        # Explicit, distinct created_at so the assertion can't depend on tie-break.
        db_session.query(User).delete()  # remove the seed admin
        db_session.commit()
        base = datetime(2026, 1, 1, 0, 0, 0)
        first = User(
            email="first@example.com",
            display_name="first",
            password_hash=_PLACEHOLDER_HASH,
            role=ROLE_ADMIN,
            created_at=base,
        )
        second = User(
            email="second@example.com",
            display_name="second",
            password_hash=_PLACEHOLDER_HASH,
            role=ROLE_ADMIN,
            created_at=base + timedelta(hours=1),
        )
        db_session.add_all([first, second])
        db_session.commit()
        assert ensure_owner_bootstrap(db_session) is True
        db_session.refresh(first)
        db_session.refresh(second)
        assert first.role == ROLE_OWNER  # oldest-created user promoted
        assert second.role == ROLE_ADMIN

    def test_noop_on_empty_users(self, db_session):
        db_session.query(User).delete()
        db_session.commit()
        assert ensure_owner_bootstrap(db_session) is False
        assert _owner_count(db_session) == 0


class TestLastOwnerGuard:
    def test_sole_owner_is_last_and_guard_raises(self, db_session):
        owner = _make_user(db_session, "soleowner@example.com", ROLE_OWNER)
        assert is_last_owner(db_session, owner.id) is True
        with pytest.raises(LastOwnerError):
            assert_not_last_owner(db_session, owner.id)

    def test_not_last_when_another_owner_exists(self, db_session):
        owner_a = _make_user(db_session, "ownera@example.com", ROLE_OWNER)
        _make_user(db_session, "ownerb@example.com", ROLE_OWNER)
        assert is_last_owner(db_session, owner_a.id) is False
        assert_not_last_owner(db_session, owner_a.id)  # must not raise

    def test_non_owner_is_never_last_owner(self, db_session):
        member = _make_user(db_session, "member@example.com", ROLE_MEMBER)
        assert is_last_owner(db_session, member.id) is False
        assert_not_last_owner(db_session, member.id)  # must not raise

    def test_unknown_user_is_not_last_owner(self, db_session):
        ghost = uuid4()
        assert is_last_owner(db_session, ghost) is False
        assert_not_last_owner(db_session, ghost)  # must not raise
