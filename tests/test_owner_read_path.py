"""Decision #424's project-owner read path, pinned as a fixture.

Derek decided a project's owner keeps READ access to every live document in that
project even without Space membership. #424 left two things for the security mission
to prove rather than assume: that the allow path does not also hand out writes, and
that soft-deleted rows stay excluded for the owner like everyone else (SEC-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.authorization import accessible_filter, authorize
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.document import Document
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace

_HASH = "unused-test-hash"


@pytest.fixture
def owner_outside_the_space(db_session):
    """A project owner who belongs to NO Space governing their own project.

    This is the exact shape decision #424 is about: before it, Space membership was
    the only read path, so the owner of a project in a Space they had not joined
    could not read their own documents.
    """
    settings.rbac_enabled = True
    owner = User(email=f"{uuid4()}@example.test", display_name="Project owner",
                 password_hash=_HASH, role="member")
    stranger = User(email=f"{uuid4()}@example.test", display_name="Stranger",
                    password_hash=_HASH, role="member")
    db_session.add_all([owner, stranger])
    db_session.flush()
    space = Workspace(name=f"Space {uuid4().hex[:6]}")
    db_session.add(space)
    db_session.flush()
    project = Project(name=f"Owned {uuid4().hex[:6]}", owner_id=owner.id, workspace_id=space.id)
    db_session.add(project)
    db_session.flush()
    # owner_id deliberately left unset: the document is readable via the PROJECT owner
    # path, not because the caller happens to own the row.
    document = Document(project_id=project.id, name="Owned source.pdf")
    db_session.add(document)
    db_session.commit()

    def principal(user, role="member"):
        return AuthenticatedUser(user_id=user.id, email=user.email,
                                 display_name=user.display_name, role=role)

    yield {"owner": principal(owner), "stranger": principal(stranger),
           "project": project, "document": document, "db": db_session}
    settings.rbac_enabled = False


@pytest.mark.unit
def test_the_project_owner_reads_a_document_they_do_not_personally_own(owner_outside_the_space):
    f = owner_outside_the_space
    assert authorize(f["owner"], "read", f["document"], f["db"]) is True


@pytest.mark.unit
def test_a_stranger_still_cannot_read_it(owner_outside_the_space):
    """The allow path must key off THIS project's owner, not any authenticated caller."""
    f = owner_outside_the_space
    assert authorize(f["stranger"], "read", f["document"], f["db"]) is False


@pytest.mark.unit
@pytest.mark.parametrize("action", ["update", "delete", "upload", "write"])
def test_the_owner_read_path_does_not_grant_writes(action, owner_outside_the_space):
    """#424: 'The change covers read access only ... unless the code shows reads and
    writes share a path, which the Sprint 52 security mission must check.' Checked."""
    f = owner_outside_the_space
    assert authorize(f["owner"], action, f["document"], f["db"]) is False


@pytest.mark.unit
def test_a_soft_deleted_document_is_not_readable_even_by_the_project_owner(owner_outside_the_space):
    f = owner_outside_the_space
    f["document"].deleted_at = datetime.now(UTC)
    f["db"].commit()
    assert authorize(f["owner"], "read", f["document"], f["db"]) is False


@pytest.mark.unit
def test_a_document_under_a_soft_deleted_project_is_not_readable_by_its_owner(owner_outside_the_space):
    f = owner_outside_the_space
    f["project"].deleted_at = datetime.now(UTC)
    f["db"].commit()
    assert authorize(f["owner"], "read", f["document"], f["db"]) is False


@pytest.mark.unit
def test_the_list_path_agrees_with_the_per_id_path(owner_outside_the_space):
    """#424 requires per-id reads and lists to agree; a split is how #422 happened."""
    f = owner_outside_the_space
    visible = (
        f["db"].query(Document)
        .filter(Document.deleted_at.is_(None))
        .filter(accessible_filter(f["owner"], Document, f["db"]))
        .all()
    )
    assert f["document"].id in {row.id for row in visible}

    hidden = (
        f["db"].query(Document)
        .filter(Document.deleted_at.is_(None))
        .filter(accessible_filter(f["stranger"], Document, f["db"]))
        .all()
    )
    assert f["document"].id not in {row.id for row in hidden}
