"""GET/PATCH /auth/me role-exposure contract (T48.1).

The frontend learns its role ONLY from /auth/me (decision #313 — role is never
baked into the JWT/TokenUser/StoredAuth), so these tests pin the contract the
admin UI depends on:

1. the caller's live role is returned for every role tier;
2. PATCH /me keeps returning role (the SECOND ProfileResponse construction site —
   a regression here would 500 once role became a required field);
3. role is resolved live from the DB per request, not the token (decision #226);
4. the JWT itself carries no role claim;
5. defense in depth: a non-admin who can now read its own role via /auth/me is
   still 403'd by the admin API — exposing role to the client relaxes nothing.

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the schema.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    ROLE_VIEWER,
    create_access_token,
)
from app.main import app
from app.models.user import User

ME_URL = "/api/v1/auth/me"
ADMIN_USERS_URL = "/api/v1/admin/users"
# Not a real credential — only a non-null value for the NOT NULL password_hash column.
_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"


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


@pytest.mark.parametrize(
    "role", [ROLE_VIEWER, ROLE_MEMBER, ROLE_ADMIN, ROLE_OWNER, ROLE_SERVICE]
)
def test_me_returns_live_role_for_each_tier(client, db_session, role):
    user = _make_user(db_session, f"{role}-me@example.com", role)
    resp = client.get(ME_URL, headers=_bearer(user))
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == role


def test_patch_me_returns_role_and_does_not_500(client, db_session):
    # Guards the "PATCH /me 500s" gotcha: role is required on ProfileResponse, so
    # the second construction site must populate it too.
    user = _make_user(db_session, "patch-me@example.com", ROLE_MEMBER)
    resp = client.patch(ME_URL, json={"display_name": "Renamed"}, headers=_bearer(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] == "Renamed"
    assert body["role"] == ROLE_MEMBER  # PATCH /me does not change role


def test_patch_me_cannot_self_escalate_role(client, db_session):
    # Defense in depth: role is NOT writable through /auth/me. ProfileUpdate omits
    # role and update_me never assigns it, so an injected role is silently ignored.
    # Pin it so a future edit (adding role to ProfileUpdate, or extra="allow") can't
    # quietly turn /me into a self-escalation primitive with no test going red.
    member = _make_user(db_session, "escalate@example.com", ROLE_MEMBER)
    resp = client.patch(
        ME_URL,
        json={"display_name": "Still Member", "role": ROLE_OWNER},
        headers=_bearer(member),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == ROLE_MEMBER

    # The DB row's role is unchanged too (not just the echoed response).
    db_session.expire_all()
    refreshed = db_session.query(User).filter(User.id == member.id).first()
    assert refreshed.role == ROLE_MEMBER


def test_me_role_is_live_db_value_not_token(client, db_session):
    # decision #226: a token minted while the user was a member must immediately
    # reflect a later promotion — role is read from the DB on every request.
    user = _make_user(db_session, "promoted@example.com", ROLE_MEMBER)
    headers = _bearer(user)  # token captured while still a member
    assert client.get(ME_URL, headers=headers).json()["role"] == ROLE_MEMBER

    user.role = ROLE_ADMIN
    db_session.commit()

    assert client.get(ME_URL, headers=headers).json()["role"] == ROLE_ADMIN


def test_jwt_carries_no_role_claim(db_session):
    user = _make_user(db_session, "noclaim@example.com", ROLE_ADMIN)
    token = create_access_token(subject=str(user.id))
    claims = jwt.get_unverified_claims(token)
    assert "role" not in claims
    assert set(claims) <= {"sub", "exp"}


def test_non_admin_still_403s_on_admin_api(client, db_session):
    # Defense in depth: /auth/me letting a member SEE its role does not let it ACT.
    member = _make_user(db_session, "member-gate@example.com", ROLE_MEMBER)
    resp = client.get(ADMIN_USERS_URL, headers=_bearer(member))
    assert resp.status_code == 403, resp.text
