"""RBAC observability endpoint + register-role footgun fix (Sprint 47 T47.1).

DB-backed (the autouse fixture seeds the role='admin' bootstrap user). Covers:

- GET /api/v1/admin/rbac-status: anon->401, member->403, admin/owner->200 with the
  documented body {rbac_enabled, owner_count, your_role, policy_version}. The /admin
  router mounts authenticated-only (main.py), so the route MUST self-gate with an
  explicit Depends(require_admin) or a mere member could read it.
- POST /auth/register no longer silently mints an admin (the footgun): a registered
  user defaults to 'member', not 'admin'.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.authorization import POLICY_VERSION
from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER, create_access_token
from app.main import app
from app.models.invite_code import InviteCode
from app.models.user import User

# Not a real credential — only a non-null value for the NOT NULL password_hash column.
_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"
RBAC_STATUS_URL = "/api/v1/admin/rbac-status"
REGISTER_URL = "/api/v1/auth/register"


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


class TestRbacStatusEndpoint:
    def test_anonymous_gets_401(self, client):
        # Router-level auth (protected_dependencies) rejects an unauthenticated caller.
        resp = client.get(RBAC_STATUS_URL)
        assert resp.status_code == 401, resp.text

    def test_member_gets_403(self, client, db_session):
        # The route must SELF-GATE: the /admin router is only authenticated-only, so
        # without an explicit require_admin a member would read RBAC internals.
        member = _make_user(db_session, "rbacstatus-member@example.com", ROLE_MEMBER)
        resp = client.get(RBAC_STATUS_URL, headers=_bearer(member))
        assert resp.status_code == 403, resp.text

    def test_admin_gets_200_with_documented_body(self, client, auth_headers):
        resp = client.get(RBAC_STATUS_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) >= {
            "rbac_enabled",
            "owner_count",
            "your_role",
            "policy_version",
        }
        assert body["rbac_enabled"] is False  # default OFF in the test environment
        assert body["your_role"] == ROLE_ADMIN
        assert body["policy_version"] == POLICY_VERSION
        assert isinstance(body["owner_count"], int)

    def test_owner_gets_200(self, client, db_session):
        owner = _make_user(db_session, "rbacstatus-owner@example.com", ROLE_OWNER)
        resp = client.get(RBAC_STATUS_URL, headers=_bearer(owner))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["your_role"] == ROLE_OWNER
        assert body["owner_count"] >= 1  # the owner we just created is counted


class TestRegisterDefaultRole:
    """The footgun: /auth/register hard-coded role='admin', so every invite minted
    an admin. A registered user must default to a non-admin role."""

    def _make_invite(self, db) -> str:
        # created_by is a NOT NULL FK to users -> reference the seeded admin.
        admin = db.query(User).filter(User.role == ROLE_ADMIN).first()
        invite = InviteCode(code="TESTCODE", created_by=admin.id)
        db.add(invite)
        db.commit()
        return invite.code

    def test_registered_user_defaults_to_member_not_admin(self, client, db_session):
        code = self._make_invite(db_session)
        resp = client.post(
            REGISTER_URL,
            json={
                "email": "newcomer@example.com",
                "password": "supersecret123",
                "display_name": "Newcomer",
                "invite_code": code,
            },
        )
        assert resp.status_code == 201, resp.text
        created = db_session.query(User).filter(User.email == "newcomer@example.com").first()
        assert created is not None
        assert created.role == ROLE_MEMBER
        assert created.role != ROLE_ADMIN
