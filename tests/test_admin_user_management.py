"""Tests for the admin user-management API + invite-code gating (Sprint 43 T43.5).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the role='admin'
bootstrap user. Covers: allow (admin) on list/role/disable, deny (non-admin -> 403),
the last-owner guard (cannot demote/disable the sole owner -> 409), and admin-only
invite-code generation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER, create_access_token
from app.main import app
from app.models.user import User

# Not a real credential — only a non-null value for the NOT NULL password_hash column.
_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"
ADMIN_USERS_URL = "/api/v1/admin/users"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


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


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


class TestAdminUsersAllow:
    def test_admin_can_list_users(self, client, db_session, auth_headers):
        resp = client.get(ADMIN_USERS_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        users = resp.json()
        assert len(users) >= 1
        assert {"id", "email", "role", "is_active", "created_at"} <= set(users[0])

    def test_admin_can_change_role(self, client, db_session, auth_headers):
        member = _make_user(db_session, "member1@example.com", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{member.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == ROLE_ADMIN

    def test_admin_can_disable_user(self, client, db_session, auth_headers):
        member = _make_user(db_session, "member2@example.com", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{member.id}/active",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

    def test_invalid_role_rejected(self, client, db_session, auth_headers):
        member = _make_user(db_session, "member3@example.com", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{member.id}/role",
            json={"role": "superuser"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text

    def test_unknown_user_returns_404(self, client, auth_headers):
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{uuid4()}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text


class TestAdminUsersDeny:
    def test_member_cannot_list_users(self, client, db_session):
        member = _make_user(db_session, "denylist@example.com", ROLE_MEMBER)
        resp = client.get(ADMIN_USERS_URL, headers=_bearer(member))
        assert resp.status_code == 403, resp.text
        assert "Admin role required" in resp.json()["detail"]

    def test_member_cannot_change_role(self, client, db_session):
        member = _make_user(db_session, "denyrole@example.com", ROLE_MEMBER)
        target = _make_user(db_session, "target1@example.com", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{target.id}/role",
            json={"role": ROLE_ADMIN},
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text

    def test_member_cannot_disable_user(self, client, db_session):
        member = _make_user(db_session, "denyactive@example.com", ROLE_MEMBER)
        target = _make_user(db_session, "target2@example.com", ROLE_MEMBER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{target.id}/active",
            json={"is_active": False},
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text


class TestLastOwnerGuard:
    def test_cannot_demote_sole_owner(self, client, db_session, auth_headers):
        owner = _make_user(db_session, "soleowner@example.com", ROLE_OWNER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{owner.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text

    def test_cannot_disable_sole_owner(self, client, db_session, auth_headers):
        owner = _make_user(db_session, "soleowner2@example.com", ROLE_OWNER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{owner.id}/active",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text

    def test_can_demote_owner_when_another_owner_exists(self, client, db_session, auth_headers):
        owner_a = _make_user(db_session, "ownera@example.com", ROLE_OWNER)
        _make_user(db_session, "ownerb@example.com", ROLE_OWNER)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{owner_a.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == ROLE_ADMIN


class TestInviteCodeGating:
    def test_admin_can_generate_invite_code(self, client, auth_headers):
        resp = client.post("/api/v1/auth/invite-codes", headers=auth_headers)
        assert resp.status_code == 201, resp.text
        assert "code" in resp.json()

    def test_member_cannot_generate_invite_code(self, client, db_session):
        member = _make_user(db_session, "denyinvite@example.com", ROLE_MEMBER)
        resp = client.post("/api/v1/auth/invite-codes", headers=_bearer(member))
        assert resp.status_code == 403, resp.text
