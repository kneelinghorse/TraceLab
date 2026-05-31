"""is_active login + per-request enforcement and active-only last-owner guard (T46.3).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the bootstrap user.

Covers:
  * Login: a soft-disabled user cannot obtain a token even with correct credentials.
  * Per-request (the standing rule, decision #226 — disable takes effect on the NEXT
    request without token reissue): a previously-issued JWT and a valid API key both
    stop working the moment the user is disabled.
  * Active-only last-owner guard: disabling/demoting the last *active* owner is
    blocked (409) even when other — but disabled — owners exist; with a second
    active owner it is allowed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import (
    ROLE_ADMIN,
    ROLE_OWNER,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
    hash_password,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.user import User

ADMIN_USERS_URL = "/api/v1/admin/users"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
_PW = "correct-horse-battery"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_user(db, email, *, role=ROLE_ADMIN, is_active=True, password=None) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(password) if password else "x",
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _make_api_key(db, user) -> str:
    plain = generate_api_key()
    db.add(
        APIKey(
            user_id=user.id,
            name="k",
            key_hash=hash_api_key(plain),
            key_prefix=get_key_prefix(plain),
        )
    )
    db.commit()
    return plain


# --- Login enforcement ------------------------------------------------------


class TestLoginEnforcement:
    def test_active_user_can_login(self, client, db_session):
        _make_user(db_session, "active-login@x.io", password=_PW)
        resp = client.post(LOGIN_URL, json={"email": "active-login@x.io", "password": _PW})
        assert resp.status_code == 200, resp.text
        assert resp.json().get("access_token")

    def test_disabled_user_cannot_login(self, client, db_session):
        _make_user(db_session, "disabled-login@x.io", is_active=False, password=_PW)
        resp = client.post(LOGIN_URL, json={"email": "disabled-login@x.io", "password": _PW})
        assert resp.status_code == 403, resp.text
        assert "disabled" in resp.json()["detail"].lower()

    def test_disabled_user_wrong_password_still_401(self, client, db_session):
        # Credential failure must not be masked by the disabled check (still 401).
        _make_user(db_session, "disabled-badpw@x.io", is_active=False, password=_PW)
        resp = client.post(LOGIN_URL, json={"email": "disabled-badpw@x.io", "password": "nope"})
        assert resp.status_code == 401, resp.text


# --- Per-request enforcement (decision #226: blocked on the NEXT request) ----


class TestPerRequestEnforcement:
    def test_jwt_stops_working_when_user_disabled(self, client, db_session):
        user = _make_user(db_session, "jwt-disable@x.io")
        headers = _bearer(user)  # token minted while active
        assert client.get(ME_URL, headers=headers).status_code == 200

        user.is_active = False
        db_session.commit()

        resp = client.get(ME_URL, headers=headers)  # SAME token, no reissue
        assert resp.status_code == 403, resp.text
        assert "disabled" in resp.json()["detail"].lower()

    def test_api_key_stops_working_when_user_disabled(self, client, db_session):
        user = _make_user(db_session, "apikey-disable@x.io")
        plain = _make_api_key(db_session, user)
        assert client.get(ME_URL, headers={"X-API-Key": plain}).status_code == 200

        user.is_active = False
        db_session.commit()

        resp = client.get(ME_URL, headers={"X-API-Key": plain})
        assert resp.status_code == 403, resp.text


# --- Active-only last-owner guard -------------------------------------------


class TestActiveOnlyLastOwnerGuard:
    def test_cannot_disable_last_active_owner_when_other_owner_is_disabled(
        self, client, db_session, auth_headers
    ):
        active_owner = _make_user(db_session, "ao-active@x.io", role=ROLE_OWNER)
        _make_user(db_session, "ao-disabled@x.io", role=ROLE_OWNER, is_active=False)
        # active_owner is the ONLY active owner -> disabling it must be blocked.
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{active_owner.id}/active",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text

    def test_cannot_demote_last_active_owner_when_other_owner_is_disabled(
        self, client, db_session, auth_headers
    ):
        active_owner = _make_user(db_session, "do-active@x.io", role=ROLE_OWNER)
        _make_user(db_session, "do-disabled@x.io", role=ROLE_OWNER, is_active=False)
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{active_owner.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text

    def test_can_disable_owner_when_a_second_active_owner_exists(
        self, client, db_session, auth_headers
    ):
        owner_a = _make_user(db_session, "two-a@x.io", role=ROLE_OWNER)
        _make_user(db_session, "two-b@x.io", role=ROLE_OWNER)  # also active
        resp = client.patch(
            f"{ADMIN_USERS_URL}/{owner_a.id}/active",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

    def test_owner_lockout_impossible_via_disable_then_demote(
        self, client, db_session, auth_headers
    ):
        # Regression: with every other owner disabled, neither disabling NOR
        # demoting the last active owner can succeed -> owner admin can't be lost.
        last_active = _make_user(db_session, "lockout-active@x.io", role=ROLE_OWNER)
        _make_user(db_session, "lockout-disabled@x.io", role=ROLE_OWNER, is_active=False)
        disable = client.patch(
            f"{ADMIN_USERS_URL}/{last_active.id}/active",
            json={"is_active": False},
            headers=auth_headers,
        )
        demote = client.patch(
            f"{ADMIN_USERS_URL}/{last_active.id}/role",
            json={"role": ROLE_ADMIN},
            headers=auth_headers,
        )
        assert disable.status_code == 409, disable.text
        assert demote.status_code == 409, demote.text
