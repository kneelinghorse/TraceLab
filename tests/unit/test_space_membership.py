"""Unit tests for the Space-membership allow path (Sprint 44 T44.3).

Exercises _has_space_membership / authorize() against a REAL session (in-memory
SQLite — fast, self-contained, no external service) so the actual membership
query and the downward project_id -> space_id inheritance run, not a mock.

Coverage matrix:
  * flag OFF  -> pass-through no-op (allowed) regardless of membership
  * flag ON   -> member of the resource's own Space            -> allow
  * flag ON   -> non-member                                    -> deny
  * flag ON   -> CHILD resource inherits the owning project's Space (allow/deny)
  * flag ON   -> every fail-closed path (NULL Space, missing project, no session)

The deny path is the OWASP requirement; inheritance is the architecture (#196).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import authorization
from app.core.config import settings
from app.core.database import Base
from app.core.security import ROLE_MEMBER, AuthenticatedUser

# Import the models whose tables we materialize. Importing the package registers
# every mapper; we create_all only the four tables this policy touches so the
# suite stays independent of PG-only column types elsewhere in the registry.
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

pytestmark = pytest.mark.unit

DEFAULT_PW_HASH = "x"  # users.password_hash is NOT NULL


@pytest.fixture
def db():
    """A throwaway in-memory SQLite session with just the policy's tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Workspace.__table__,
            Project.__table__,
            SpaceMember.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _member(user_id: uuid.UUID) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id, email="m@example.com", display_name="m", role=ROLE_MEMBER
    )


def _seed_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    db.add(
        User(
            id=uid,
            email=f"{uid}@example.com",
            display_name="member",
            password_hash=DEFAULT_PW_HASH,
            role=ROLE_MEMBER,
        )
    )
    db.flush()
    return uid


def _seed_space(db) -> uuid.UUID:
    wid = uuid.uuid4()
    db.add(Workspace(id=wid, name="Space"))
    db.flush()
    return wid


def _grant(db, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    db.add(SpaceMember(workspace_id=workspace_id, user_id=user_id))
    db.flush()


# --- flag OFF: byte-identical no-op -----------------------------------------


def test_flag_off_allows_non_member(db):
    """Flag OFF: even a non-member of the resource's Space is allowed (no-op)."""
    assert settings.rbac_enabled is False
    space_id = _seed_space(db)
    uid = _seed_user(db)
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=space_id)
    # user is NOT granted membership, yet flag-off authorize allows everything.
    assert authorization.authorize(_member(uid), "read", resource, db) is True


# --- flag ON: own-Space membership ------------------------------------------


def test_member_of_own_space_allowed(db, rbac_on):
    space_id = _seed_space(db)
    uid = _seed_user(db)
    _grant(db, space_id, uid)
    # top-level resource (no project_id) governed by its own workspace_id
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=space_id)
    assert authorization.authorize(_member(uid), "read", resource, db) is True


def test_non_member_denied(db, rbac_on):
    space_id = _seed_space(db)
    uid = _seed_user(db)
    # no _grant -> not a member
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=space_id)
    assert authorization.authorize(_member(uid), "read", resource, db) is False


def test_member_of_a_different_space_denied(db, rbac_on):
    member_space = _seed_space(db)
    other_space = _seed_space(db)
    uid = _seed_user(db)
    _grant(db, member_space, uid)  # member of member_space, not other_space
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=other_space)
    assert authorization.authorize(_member(uid), "read", resource, db) is False


# --- flag ON: downward inheritance (project_id -> space_id) ------------------


def _seed_project(db, workspace_id) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="proj", workspace_id=workspace_id))
    db.flush()
    return pid


def test_child_resource_inherits_project_space_allowed(db, rbac_on):
    """A child resource (carries project_id) inherits the owning project's Space."""
    space_id = _seed_space(db)
    uid = _seed_user(db)
    _grant(db, space_id, uid)
    project_id = _seed_project(db, space_id)
    # child resource has NO own workspace_id set (None) but a project_id -> inherits
    child = SimpleNamespace(owner_id=uuid.uuid4(), project_id=project_id, workspace_id=None)
    assert authorization.authorize(_member(uid), "read", child, db) is True


def test_child_resource_inheritance_uses_project_not_own_workspace(db, rbac_on):
    """Inheritance is authoritative: the project's Space governs, not the child's
    own (denormalized) workspace_id. Member of the project's Space is allowed even
    if the child's own workspace_id points at a Space they are NOT in."""
    project_space = _seed_space(db)
    stale_child_space = _seed_space(db)
    uid = _seed_user(db)
    _grant(db, project_space, uid)  # member of the PROJECT's space only
    project_id = _seed_project(db, project_space)
    child = SimpleNamespace(
        owner_id=uuid.uuid4(), project_id=project_id, workspace_id=stale_child_space
    )
    assert authorization.authorize(_member(uid), "read", child, db) is True


def test_child_resource_member_of_childs_own_space_but_not_projects_denied(db, rbac_on):
    """The flip side: being a member of the child's own workspace_id but NOT the
    owning project's Space is denied — inheritance ignores the child's column."""
    project_space = _seed_space(db)
    child_own_space = _seed_space(db)
    uid = _seed_user(db)
    _grant(db, child_own_space, uid)  # member of the child's own space, NOT project's
    project_id = _seed_project(db, project_space)
    child = SimpleNamespace(
        owner_id=uuid.uuid4(), project_id=project_id, workspace_id=child_own_space
    )
    assert authorization.authorize(_member(uid), "read", child, db) is False


# --- flag ON: fail-closed paths ---------------------------------------------


def test_null_space_denied(db, rbac_on):
    """Resource with no resolvable Space (workspace_id None) -> deny."""
    uid = _seed_user(db)
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=None)
    assert authorization.authorize(_member(uid), "read", resource, db) is False


def test_child_with_missing_project_denied(db, rbac_on):
    """Child resource whose project_id resolves to no project -> deny."""
    uid = _seed_user(db)
    child = SimpleNamespace(owner_id=uuid.uuid4(), project_id=uuid.uuid4())
    assert authorization.authorize(_member(uid), "read", child, db) is False


def test_child_whose_project_has_null_space_denied(db, rbac_on):
    """Child resource whose owning project has a NULL workspace_id -> deny."""
    uid = _seed_user(db)
    project_id = _seed_project(db, None)  # project with NULL space
    child = SimpleNamespace(owner_id=uuid.uuid4(), project_id=project_id)
    assert authorization.authorize(_member(uid), "read", child, db) is False


def test_no_session_denied(db, rbac_on):
    """No DB session reaches the membership branch -> fail closed (deny)."""
    resource = SimpleNamespace(owner_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    assert authorization.authorize(_member(uuid.uuid4()), "read", resource, None) is False


def test_none_resource_denied(db, rbac_on):
    """A None resource resolves to no Space -> deny (None-guarded)."""
    assert authorization.authorize(_member(uuid.uuid4()), "read", None, db) is False
