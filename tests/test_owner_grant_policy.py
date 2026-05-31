"""owner_id read-side exposure + owner-grant policy (Sprint C — T46.4).

DB-backed (autouse fixture seeds the role='admin' bootstrap user).

  * ProjectRead exposes owner_id (authoritative owner), on both create and read.
  * Granting ROLE_OWNER requires an OWNER caller: a mere admin gets 403 (closes the
    admin→owner privilege-escalation path); admins may still assign non-owner roles.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    create_access_token,
)
from app.main import app
from app.models.project import Project
from app.models.user import User

_HASH = "placeholder-not-a-real-hash"
ADMIN_USERS_URL = "/api/v1/admin/users"
PROJECTS_URL = "/api/v1/projects"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_user(db, email, role) -> User:
    user = User(
        email=email, display_name=email.split("@")[0], password_hash=_HASH, role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


# --- owner_id read-side exposure --------------------------------------------


class TestOwnerIdExposed:
    def test_create_response_includes_owner_id(self, client, db_session, auth_headers):
        resp = client.post(PROJECTS_URL, json={"name": "Owned"}, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "owner_id" in body
        # owner is stamped server-side from the caller (T43.4) — never null here.
        assert body["owner_id"] is not None

    def test_get_response_includes_owner_id(self, client, db_session, auth_headers):
        owner = _make_user(db_session, "proj-owner@x.io", ROLE_MEMBER)
        project = Project(name="Read me", owner_id=owner.id)
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        # rbac_enabled is False by default -> authorize() no-op -> admin can read.
        resp = client.get(f"{PROJECTS_URL}/{project.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["owner_id"] == str(owner.id)


# --- owner-grant policy -----------------------------------------------------


class TestOwnerGrantPolicy:
    def test_admin_cannot_grant_owner(self, client, db_session, auth_headers):
        # auth_headers is the seeded role='admin' bootstrap user.
        target = _make_user(db_session, "to-owner@x.io", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{target.id}/role",
            json={"role": ROLE_OWNER},
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text
        assert "owner" in resp.json()["detail"].lower()
        # target was NOT escalated
        db_session.refresh(target)
        assert target.role == ROLE_MEMBER

    def test_owner_can_grant_owner(self, client, db_session):
        owner = _make_user(db_session, "granter-owner@x.io", ROLE_OWNER)
        target = _make_user(db_session, "grantee@x.io", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{target.id}/role",
            json={"role": ROLE_OWNER},
            headers=_bearer(owner),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == ROLE_OWNER

    def test_admin_can_still_grant_non_owner_roles(self, client, db_session, auth_headers):
        target = _make_user(db_session, "to-admin@x.io", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{target.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == ROLE_ADMIN
