"""Tests for the admin user-management API + invite-code gating (Sprint 43 T43.5).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the role='admin'
bootstrap user. Covers: allow (admin) on list/role/disable, deny (non-admin -> 403),
the last-owner guard (cannot demote/disable the sole owner -> 409), and admin-only
invite-code generation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.database import engine
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    create_access_token,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from app.models.invite_code import InviteCode
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


def _device_grant(*, user_id, api_key_id, suffix):
    """An approved RFC-8628 grant linking a user to a minted api_key (for purge tests)."""
    return DeviceAuthorizationGrant(
        device_code=f"dc-{suffix}-{uuid4().hex}",
        user_code=f"UC{suffix}{uuid4().hex[:6]}".upper()[:16],
        client_label="test-device",
        status="approved",
        user_id=user_id,
        api_key_id=api_key_id,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )


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


class TestAdminUserCreate:
    """POST /admin/users — direct user provisioning at an explicit role (T47.1).

    Replaces the register->demote dance the live RBAC harness (T47.2) would
    otherwise need. Granting ROLE_OWNER stays owner-only."""

    def test_admin_can_create_member(self, client, auth_headers):
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "created-member@example.com",
                "password": "supersecret123",
                "display_name": "Created Member",
                "role": ROLE_MEMBER,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["role"] == ROLE_MEMBER
        assert body["email"] == "created-member@example.com"
        assert body["is_active"] is True

    def test_admin_can_create_viewer(self, client, auth_headers):
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "created-viewer@example.com",
                "password": "supersecret123",
                "display_name": "Created Viewer",
                "role": ROLE_VIEWER,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == ROLE_VIEWER

    def test_role_defaults_to_member_when_omitted(self, client, auth_headers):
        # Safe-by-default: a forgotten role mints the LEAST privilege, never admin.
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "created-default@example.com",
                "password": "supersecret123",
                "display_name": "Created Default",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == ROLE_MEMBER

    def test_created_user_can_login(self, client, auth_headers):
        # Verifies the password is hashed (not stored plain) and the account works.
        client.post(
            ADMIN_USERS_URL,
            json={
                "email": "loginable@example.com",
                "password": "supersecret123",
                "display_name": "Loginable",
                "role": ROLE_MEMBER,
            },
            headers=auth_headers,
        )
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "loginable@example.com", "password": "supersecret123"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["user"]["email"] == "loginable@example.com"

    def test_duplicate_email_rejected(self, client, db_session, auth_headers):
        _make_user(db_session, "dupe@example.com", ROLE_MEMBER)
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "dupe@example.com",
                "password": "supersecret123",
                "display_name": "Dupe",
                "role": ROLE_MEMBER,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text

    def test_invalid_role_rejected(self, client, auth_headers):
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "badrole@example.com",
                "password": "supersecret123",
                "display_name": "Bad Role",
                "role": "superuser",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text

    def test_member_cannot_create(self, client, db_session):
        member = _make_user(db_session, "creatordeny@example.com", ROLE_MEMBER)
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "nope@example.com",
                "password": "supersecret123",
                "display_name": "Nope",
                "role": ROLE_MEMBER,
            },
            headers=_bearer(member),
        )
        assert resp.status_code == 403, resp.text

    def test_admin_cannot_create_owner(self, client, auth_headers):
        # auth_headers is a mere admin; minting an owner is owner-only.
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "wouldbeowner@example.com",
                "password": "supersecret123",
                "display_name": "Would Be Owner",
                "role": ROLE_OWNER,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_create_owner(self, client, db_session):
        owner = _make_user(db_session, "realowner@example.com", ROLE_OWNER)
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "secondowner@example.com",
                "password": "supersecret123",
                "display_name": "Second Owner",
                "role": ROLE_OWNER,
            },
            headers=_bearer(owner),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == ROLE_OWNER

    def test_blank_display_name_rejected(self, client, auth_headers):
        # display_name is NOT NULL with no check constraint; a whitespace-only name
        # must be rejected at the schema edge (422), not silently stored.
        resp = client.post(
            ADMIN_USERS_URL,
            json={
                "email": "blankname@example.com",
                "password": "supersecret123",
                "display_name": "   ",
                "role": ROLE_MEMBER,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text


class TestAdminUserHardDelete:
    """DELETE /admin/users/{id} — full teardown of throwaway users (T47.1).

    Today the admin API only soft-disables. The live harness (T47.2) needs to leave
    no cruft, so the purge must clear the user's RESTRICT-FK dependents (api_keys,
    invite_codes) that would otherwise block the delete on Postgres."""

    def test_admin_can_hard_delete_user(self, client, db_session, auth_headers):
        target = _make_user(db_session, "todelete@example.com", ROLE_MEMBER)
        resp = client.delete(f"{ADMIN_USERS_URL}/{target.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert db_session.query(User).filter(User.id == target.id).first() is None

    def test_hard_delete_purges_api_keys(self, client, db_session, auth_headers):
        # "no leaked cruft": api_keys.user_id is a RESTRICT FK; a naive db.delete(user)
        # raises IntegrityError on Postgres. SQLite (FK off in tests) would hide that,
        # so assert the keys are actually gone — encodes WHY the cleanup must exist.
        target = _make_user(db_session, "todelete-keys@example.com", ROLE_MEMBER)
        db_session.add(
            APIKey(
                user_id=target.id,
                name="throwaway",
                key_hash="hash",
                key_prefix="tl_abc123",
            )
        )
        db_session.commit()
        resp = client.delete(f"{ADMIN_USERS_URL}/{target.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert db_session.query(APIKey).filter(APIKey.user_id == target.id).count() == 0

    def test_hard_delete_purges_invite_codes(self, client, db_session, auth_headers):
        # invite_codes.created_by AND used_by are RESTRICT FKs to users.
        target = _make_user(db_session, "todelete-invite@example.com", ROLE_MEMBER)
        db_session.add(InviteCode(code="OWNEDBYU", created_by=target.id))
        db_session.add(
            InviteCode(code="USEDBYUU", created_by=target.id, used_by=target.id)
        )
        db_session.commit()
        resp = client.delete(f"{ADMIN_USERS_URL}/{target.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert (
            db_session.query(InviteCode)
            .filter(InviteCode.created_by == target.id)
            .count()
            == 0
        )
        assert (
            db_session.query(InviteCode)
            .filter(InviteCode.used_by == target.id)
            .count()
            == 0
        )

    def test_cannot_delete_last_owner(self, client, db_session, auth_headers):
        owner = _make_user(db_session, "lastowner-del@example.com", ROLE_OWNER)
        resp = client.delete(f"{ADMIN_USERS_URL}/{owner.id}", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert db_session.query(User).filter(User.id == owner.id).first() is not None

    def test_can_delete_owner_when_another_exists(self, client, db_session, auth_headers):
        owner_a = _make_user(db_session, "ownerdel-a@example.com", ROLE_OWNER)
        _make_user(db_session, "ownerdel-b@example.com", ROLE_OWNER)
        resp = client.delete(f"{ADMIN_USERS_URL}/{owner_a.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text

    def test_delete_unknown_user_404(self, client, auth_headers):
        resp = client.delete(f"{ADMIN_USERS_URL}/{uuid4()}", headers=auth_headers)
        assert resp.status_code == 404, resp.text

    def test_cannot_delete_self(self, client, db_session, auth_headers):
        # The seeded admin (auth_headers principal) cannot nuke its own account.
        seeded = db_session.query(User).filter(User.role == ROLE_ADMIN).first()
        resp = client.delete(f"{ADMIN_USERS_URL}/{seeded.id}", headers=auth_headers)
        assert resp.status_code == 400, resp.text
        assert db_session.query(User).filter(User.id == seeded.id).first() is not None

    def test_member_cannot_delete(self, client, db_session):
        member = _make_user(db_session, "deldeny@example.com", ROLE_MEMBER)
        target = _make_user(db_session, "deltarget@example.com", ROLE_MEMBER)
        resp = client.delete(
            f"{ADMIN_USERS_URL}/{target.id}", headers=_bearer(member)
        )
        assert resp.status_code == 403, resp.text

    def test_hard_delete_purges_device_grants(self, client, db_session, auth_headers):
        # device_authorization_grants.user_id is a non-cascading FK; the grant also
        # carries api_key_id, so the purge must clear grants (and before their key).
        target = _make_user(db_session, "todelete-grant@example.com", ROLE_MEMBER)
        key = APIKey(user_id=target.id, name="k", key_hash="h", key_prefix="tl_grant01")
        db_session.add(key)
        db_session.flush()
        db_session.add(_device_grant(user_id=target.id, api_key_id=key.id, suffix="A"))
        db_session.commit()
        resp = client.delete(f"{ADMIN_USERS_URL}/{target.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert (
            db_session.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_id == target.id)
            .count()
            == 0
        )

    def test_hard_delete_survives_fk_enforcement(self, client, db_session, auth_headers):
        """Prove the purge's deletion ORDER holds under Postgres-style RESTRICT FKs.

        The default test DB is SQLite with FK enforcement OFF, so it cannot catch a
        wrong purge order (deleting api_keys before the device grant that references
        them via api_key_id). Enable PRAGMA foreign_keys=ON for THIS test so a bad
        order raises IntegrityError -> 500 exactly as prod Postgres would. This is the
        regression guard for the grants-before-api_keys ordering."""

        def _fk_on(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        event.listen(engine, "connect", _fk_on)
        engine.dispose()  # drop pooled connections so new ones pick up the PRAGMA
        try:
            target = _make_user(db_session, "fk-purge@example.com", ROLE_MEMBER)
            key = APIKey(
                user_id=target.id, name="k", key_hash="h", key_prefix="tl_fkkey01"
            )
            db_session.add(key)
            db_session.flush()
            db_session.add(_device_grant(user_id=target.id, api_key_id=key.id, suffix="B"))
            db_session.add(
                InviteCode(code="FKPURGE1", created_by=target.id, used_by=target.id)
            )
            db_session.commit()
            resp = client.delete(f"{ADMIN_USERS_URL}/{target.id}", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            assert db_session.query(User).filter(User.id == target.id).first() is None
        finally:
            event.remove(engine, "connect", _fk_on)
            engine.dispose()  # restore FK-off for subsequent tests

    def test_last_owner_self_delete_gets_409(self, client, db_session):
        # A sole owner deleting itself hits the precise last-owner guard (409), not
        # the generic self-delete 400 — the guards are ordered last-owner-first.
        owner = _make_user(db_session, "soleowner-self@example.com", ROLE_OWNER)
        resp = client.delete(f"{ADMIN_USERS_URL}/{owner.id}", headers=_bearer(owner))
        assert resp.status_code == 409, resp.text


class TestInviteCodeGating:
    def test_admin_can_generate_invite_code(self, client, auth_headers):
        resp = client.post("/api/v1/auth/invite-codes", headers=auth_headers)
        assert resp.status_code == 201, resp.text
        assert "code" in resp.json()

    def test_member_cannot_generate_invite_code(self, client, db_session):
        member = _make_user(db_session, "denyinvite@example.com", ROLE_MEMBER)
        resp = client.post("/api/v1/auth/invite-codes", headers=_bearer(member))
        assert resp.status_code == 403, resp.text
