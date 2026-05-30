"""Tests for the Space management API (Sprint 44 T44.5).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the role='admin'
bootstrap user. Covers: happy path (create/list space, member add/remove, assign
project space, attach/detach tag), auth gating (non-admin -> 403, the OWASP deny
requirement), and edge cases (404 missing, 409 duplicate, un-assign to NULL).

These endpoints only manage grouping/grant data; no authorize() enforcement is
wired here (Sprint C). require_admin is the gate, applied router-level in
app/main.py and unit-tested in test_authz.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import ROLE_MEMBER, create_access_token
from app.main import app
from app.models.project import Project
from app.models.tag import Tag
from app.models.user import User
from app.models.workspace import Workspace

_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"
SPACES_URL = "/api/v1/admin/spaces"
PROJECTS_ADMIN_URL = "/api/v1/admin/projects"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_user(db, email, role=ROLE_MEMBER) -> User:
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


def _make_space(db, name="Space A") -> Workspace:
    space = Workspace(name=name)
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


def _make_project(db, name="Proj A") -> Project:
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_tag(db, name="theme-x") -> Tag:
    tag = Tag(name=name, category="theme")
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


class TestSpaceLifecycle:
    def test_admin_can_create_and_list_spaces(self, client, db_session, auth_headers):
        resp = client.post(SPACES_URL, json={"name": "Research"}, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        space_id = resp.json()["id"]
        assert resp.json()["name"] == "Research"

        listed = client.get(SPACES_URL, headers=auth_headers)
        assert listed.status_code == 200, listed.text
        assert any(s["id"] == space_id for s in listed.json())


class TestSpaceMembership:
    def test_admin_can_add_and_remove_member(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        user = _make_user(db_session, "m1@example.com")

        add = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(user.id)},
            headers=auth_headers,
        )
        assert add.status_code == 201, add.text
        body = add.json()
        assert body["workspace_id"] == str(space.id)
        assert body["user_id"] == str(user.id)
        assert body["role"] == ROLE_MEMBER  # default grant tier

        remove = client.delete(
            f"{SPACES_URL}/{space.id}/members/{user.id}", headers=auth_headers
        )
        assert remove.status_code == 200, remove.text

    def test_duplicate_member_is_conflict(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        user = _make_user(db_session, "dup@example.com")
        first = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(user.id)},
            headers=auth_headers,
        )
        assert first.status_code == 201, first.text
        again = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(user.id)},
            headers=auth_headers,
        )
        assert again.status_code == 409, again.text

    def test_add_member_unknown_space_404(self, client, db_session, auth_headers):
        user = _make_user(db_session, "nospace@example.com")
        resp = client.post(
            f"{SPACES_URL}/{uuid4()}/members",
            json={"user_id": str(user.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text

    def test_add_member_unknown_user_404(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        resp = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(uuid4())},
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text

    def test_invalid_grant_role_rejected(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        user = _make_user(db_session, "badrole@example.com")
        resp = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(user.id), "role": "superuser"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text

    def test_remove_non_member_404(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        resp = client.delete(
            f"{SPACES_URL}/{space.id}/members/{uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text


class TestProjectSpaceAssignment:
    def test_assign_and_unassign_project_space(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        project = _make_project(db_session)

        assigned = client.patch(
            f"{PROJECTS_ADMIN_URL}/{project.id}/space",
            json={"space_id": str(space.id)},
            headers=auth_headers,
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["space_id"] == str(space.id)
        db_session.refresh(project)
        assert str(project.workspace_id) == str(space.id)

        # un-assign -> space-less (NULL), tolerated by the membership path
        unassigned = client.patch(
            f"{PROJECTS_ADMIN_URL}/{project.id}/space",
            json={"space_id": None},
            headers=auth_headers,
        )
        assert unassigned.status_code == 200, unassigned.text
        assert unassigned.json()["space_id"] is None
        db_session.refresh(project)
        assert project.workspace_id is None

    def test_assign_unknown_project_404(self, client, db_session, auth_headers):
        space = _make_space(db_session)
        resp = client.patch(
            f"{PROJECTS_ADMIN_URL}/{uuid4()}/space",
            json={"space_id": str(space.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text

    def test_assign_unknown_space_404(self, client, db_session, auth_headers):
        project = _make_project(db_session)
        resp = client.patch(
            f"{PROJECTS_ADMIN_URL}/{project.id}/space",
            json={"space_id": str(uuid4())},
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text


class TestProjectTags:
    def test_attach_and_detach_tag(self, client, db_session, auth_headers):
        project = _make_project(db_session)
        tag = _make_tag(db_session)

        attach = client.post(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}", headers=auth_headers
        )
        assert attach.status_code == 201, attach.text
        assert attach.json()["project_id"] == str(project.id)
        assert attach.json()["tag_id"] == str(tag.id)

        detach = client.delete(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}", headers=auth_headers
        )
        assert detach.status_code == 200, detach.text

    def test_attach_duplicate_is_conflict(self, client, db_session, auth_headers):
        project = _make_project(db_session)
        tag = _make_tag(db_session)
        first = client.post(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}", headers=auth_headers
        )
        assert first.status_code == 201, first.text
        again = client.post(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}", headers=auth_headers
        )
        assert again.status_code == 409, again.text

    def test_attach_unknown_project_404(self, client, db_session, auth_headers):
        tag = _make_tag(db_session)
        resp = client.post(
            f"{PROJECTS_ADMIN_URL}/{uuid4()}/tags/{tag.id}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text

    def test_attach_unknown_tag_404(self, client, db_session, auth_headers):
        project = _make_project(db_session)
        resp = client.post(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text

    def test_detach_unattached_404(self, client, db_session, auth_headers):
        project = _make_project(db_session)
        tag = _make_tag(db_session)
        resp = client.delete(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text


class TestAdminGating:
    """Every management route is gated by require_admin -> non-admin gets 403."""

    def test_member_cannot_create_space(self, client, db_session):
        member = _make_user(db_session, "gate1@example.com", ROLE_MEMBER)
        resp = client.post(
            SPACES_URL, json={"name": "Nope"}, headers=_bearer(member)
        )
        assert resp.status_code == 403, resp.text

    def test_member_cannot_list_spaces(self, client, db_session):
        member = _make_user(db_session, "gate2@example.com", ROLE_MEMBER)
        resp = client.get(SPACES_URL, headers=_bearer(member))
        assert resp.status_code == 403, resp.text

    def test_member_cannot_add_member(self, client, db_session):
        member = _make_user(db_session, "gate3@example.com", ROLE_MEMBER)
        space = _make_space(db_session)
        resp = client.post(
            f"{SPACES_URL}/{space.id}/members",
            json={"user_id": str(member.id)},
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text

    def test_member_cannot_assign_project_space(self, client, db_session):
        member = _make_user(db_session, "gate4@example.com", ROLE_MEMBER)
        project = _make_project(db_session)
        space = _make_space(db_session)
        resp = client.patch(
            f"{PROJECTS_ADMIN_URL}/{project.id}/space",
            json={"space_id": str(space.id)},
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text

    def test_member_cannot_attach_tag(self, client, db_session):
        member = _make_user(db_session, "gate5@example.com", ROLE_MEMBER)
        project = _make_project(db_session)
        tag = _make_tag(db_session)
        resp = client.post(
            f"{PROJECTS_ADMIN_URL}/{project.id}/tags/{tag.id}",
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text
