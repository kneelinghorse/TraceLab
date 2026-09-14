"""Unit tests for the centralized authorize() policy (Sprint 43 T43.6).

Pure-logic (tests/unit/, no DB). Covers the no-op pass-through while the flag is
OFF (the byte-identical default) and the deny-by-default policy when the flag is
flipped ON, exercising BOTH allow and deny paths (the deny path is the OWASP
requirement).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core import authorization
from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    ROLE_VIEWER,
    AuthenticatedUser,
)

pytestmark = pytest.mark.unit


def _user(role: str, user_id=None) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id or uuid4(),
        email="u@example.com",
        display_name="u",
        role=role,
    )


@pytest.fixture
def rbac_on(monkeypatch):
    """Flip the master switch ON for the test, auto-restored afterwards."""
    monkeypatch.setattr(settings, "rbac_enabled", True)


class TestAuthorizeFlagOff:
    """Default (flag OFF): pass-through no-op — everything is allowed."""

    def test_default_flag_is_off(self):
        assert settings.rbac_enabled is False

    def test_noop_allows_viewer_on_someone_elses_resource(self):
        resource = SimpleNamespace(owner_id=uuid4())  # owned by another user
        assert authorization.authorize(_user(ROLE_VIEWER), "write", resource) is True

    def test_noop_allows_unknown_role(self):
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user("ghost"), "delete", resource) is True


class TestAuthorizeFlagOn:
    """Flag ON (Sprint C): deny-by-default policy."""

    def test_owner_role_allowed(self, rbac_on):
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user(ROLE_OWNER), "write", resource) is True

    def test_admin_role_allowed(self, rbac_on):
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user(ROLE_ADMIN), "write", resource) is True

    def test_resource_owner_allowed(self, rbac_on):
        uid = uuid4()
        resource = SimpleNamespace(owner_id=uid)
        assert authorization.authorize(_user(ROLE_MEMBER, user_id=uid), "write", resource) is True

    def test_resource_owner_allowed_regardless_of_role(self, rbac_on):
        # The ownership branch is role-agnostic: even a viewer who OWNS the resource
        # is allowed (pins that ownership access does not require a minimum role tier).
        uid = uuid4()
        resource = SimpleNamespace(owner_id=uid)
        assert authorization.authorize(_user(ROLE_VIEWER, user_id=uid), "read", resource) is True

    def test_member_non_owner_denied(self, rbac_on):
        # member who does NOT own the resource -> deny (the OWASP deny path)
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user(ROLE_MEMBER), "write", resource) is False

    def test_viewer_denied(self, rbac_on):
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user(ROLE_VIEWER), "read", resource) is False

    def test_unknown_role_denied(self, rbac_on):
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user("ghost"), "read", resource) is False

    def test_resource_without_owner_id_denied_for_non_privileged(self, rbac_on):
        # No owner_id attribute -> a non-admin/non-owner is denied (fail closed).
        assert authorization.authorize(_user(ROLE_MEMBER), "read", SimpleNamespace()) is False

    def test_space_membership_denied_without_session(self, rbac_on):
        # The Space-membership allow path (T44.3) needs a DB session to resolve the
        # Space and read space_members. Called without one, a member who does not
        # own the resource gets no access via that branch -> fail closed (deny).
        # The membership lookup itself is exercised against a real session in
        # tests/unit/test_space_membership.py.
        resource = SimpleNamespace(owner_id=uuid4())
        assert authorization.authorize(_user(ROLE_MEMBER), "read", resource) is False


class TestProjectOwnerDocumentRead:
    """Project ownership grants sibling-document reads, never document writes."""

    @pytest.fixture
    def owned_project_document(self):
        from app.models.document import Document
        from app.models.project import Project

        user = _user(ROLE_MEMBER)
        project = Project(id=uuid4(), owner_id=user.user_id, workspace_id=uuid4())
        document = Document(project_id=project.id, owner_id=uuid4())
        db = MagicMock()
        db.get.return_value = project
        db.query.return_value.filter.return_value.first.return_value = None
        return user, project, document, db

    def test_live_project_owner_reads_other_owned_document_without_space(self, rbac_on, owned_project_document):
        user, _, document, db = owned_project_document
        assert authorization.authorize(user, "read", document, db) is True

    @pytest.mark.parametrize("action", ["update", "process", "delete", "restore", "upload"])
    def test_project_ownership_never_grants_document_writes(self, rbac_on, owned_project_document, action):
        user, _, document, db = owned_project_document
        assert authorization.authorize(user, action, document, db) is False

    @pytest.mark.parametrize("deleted", ["project", "document"])
    def test_deleted_context_does_not_grant_new_read_path(self, rbac_on, owned_project_document, deleted):
        user, project, document, db = owned_project_document
        (project if deleted == "project" else document).deleted_at = datetime.utcnow()
        assert authorization.authorize(user, "read", document, db) is False

    def test_service_does_not_inherit_human_project_ownership(self, rbac_on, owned_project_document):
        user, _, document, db = owned_project_document
        service = _user(ROLE_SERVICE, user_id=user.user_id)
        assert authorization.authorize(service, "read", document, db) is False

    def test_missing_session_fails_closed(self, rbac_on, owned_project_document):
        user, _, document, _ = owned_project_document
        assert authorization.authorize(user, "read", document) is False

    @pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_OWNER])
    def test_privileged_grants_are_unchanged(self, rbac_on, owned_project_document, role):
        _, _, document, _ = owned_project_document
        assert authorization.authorize(_user(role), "delete", document) is True

    def test_flag_off_grants_are_unchanged(self, owned_project_document):
        user, project, document, db = owned_project_document
        project.deleted_at = datetime.utcnow()
        assert authorization.authorize(user, "delete", document, db) is True
