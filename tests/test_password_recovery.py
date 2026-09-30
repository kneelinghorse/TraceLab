"""Recovery must replace only the intended human's credentials, never on link open."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import (
    _resolve_user_from_jwt,
    create_access_token,
    hash_password,
    verify_password,
)
from app.dependencies import get_password_recovery_service
from app.main import app
from app.models.api_key import APIKey
from app.models.password_recovery import PasswordRecovery
from app.models.user import User
from app.services.password_recovery import PasswordRecoveryService


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://tracelab.test")
    monkeypatch.setattr(settings, "resend_api_key", "isolated-mail")
    monkeypatch.setattr(settings, "resend_from_address", "recovery@tracelab.test")
    monkeypatch.setattr(settings, "notification_emails_enabled", False)
    mail = AsyncMock()
    mail.send.return_value = "provider-accepted"
    service = PasswordRecoveryService(SessionLocal, mail)
    app.dependency_overrides[get_password_recovery_service] = lambda: service
    with SessionLocal() as db:
        user = User(email="recover@controlled.org", display_name="Recover", role="member",
                    password_hash=hash_password("original-password"), email_notifications_enabled=False)
        db.add(user)
        db.commit()
        user_id = user.id
    # No lifespan: these auth tests must not warm a Qdrant or model connection.
    yield TestClient(app), service, mail, user_id
    app.dependency_overrides.pop(get_password_recovery_service, None)


def request_link(recovery):
    client, _, mail, _ = recovery
    response = client.post("/api/v1/auth/password-reset/request", json={"email": " RECOVER@controlled.org "})
    assert response.status_code == 202
    message = mail.send.call_args.args[0]
    return message.text.split("#token=", 1)[1].split()[0]


def confirm(client, token, password="replacement-password"):  # noqa: S107 - isolated test credential
    return client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token, "new_password": password, "confirm_password": password,
    })


def test_recovery_revokes_old_credentials_but_request_and_open_do_not(recovery):
    client, _, mail, user_id = recovery
    old_token = create_access_token(subject=str(user_id))
    headers = {"Authorization": f"Bearer {old_token}"}
    key = client.post("/api/v1/auth/api-keys", headers=headers, json={"name": "old integration"}).json()["key"]
    token = request_link(recovery)
    assert "#token=" in mail.send.call_args.args[0].html
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert verify_password("original-password", user.password_hash)
        assert user.credential_version == 0
        row = db.get(PasswordRecovery, user_id)
        assert token not in row.token_hash
        assert len(row.token_hash) == 64
        assert db.query(APIKey).filter_by(user_id=user_id).count() == 1
    assert client.get("/api/v1/auth/password-reset/confirm").status_code == 405
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert confirm(client, token).status_code == 200
    assert confirm(client, token).status_code == 400
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": key}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "recover@controlled.org", "password": "original-password"}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"email": "recover@controlled.org", "password": "replacement-password"})
    assert response.status_code == 200
    claims = jwt.decode(response.json()["access_token"], settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert claims["credential_version"] == 1


@pytest.mark.parametrize("kind", ["unknown", "disabled", "service", "undeliverable"])
def test_requests_do_not_disclose_account_eligibility(recovery, kind):
    client, _, mail, user_id = recovery
    email = "recover@controlled.org"
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if kind == "unknown":
            email = "missing@controlled.org"
        elif kind == "disabled":
            user.is_active = False
        elif kind == "service":
            user.role = "service"
        else:
            email = user.email = "nobody@example.com"
        db.commit()
    response = client.post("/api/v1/auth/password-reset/request", json={"email": email})
    assert response.status_code == 202
    assert response.json() == {"message": "If this account can receive recovery email, instructions will be sent. Check your inbox and spam folder."}
    mail.send.assert_not_called()


def test_settings_invalidates_link_without_signing_out(recovery):
    client, _, _, user_id = recovery
    token = request_link(recovery)
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}
    response = client.patch("/api/v1/auth/me", headers=headers, json={
        "current_password": "original-password", "new_password": "settings-password",
    })
    assert response.status_code == 200
    assert confirm(client, token).status_code == 400
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_expired_link_and_weak_mismatch_are_non_mutating_and_secret_safe(recovery):
    client, _, _, user_id = recovery
    token = request_link(recovery)
    for payload in [
        {"token": token, "new_password": "tiny!", "confirm_password": "tiny!"},
        {"token": token, "new_password": "valid-password", "confirm_password": "different-password"},
    ]:
        response = client.post("/api/v1/auth/password-reset/confirm", json=payload)
        assert response.status_code == 422
        assert token not in response.text
        assert payload["new_password"] not in response.text
    with SessionLocal() as db:
        db.get(PasswordRecovery, user_id).expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert confirm(client, token).status_code == 400
    with SessionLocal() as db:
        assert verify_password("original-password", db.get(User, user_id).password_hash)


def test_legacy_jwt_only_works_at_revision_zero(recovery):
    client, _, _, user_id = recovery
    legacy = jwt.encode({"sub": str(user_id), "exp": datetime.utcnow() + timedelta(minutes=10)}, settings.secret_key, algorithm=settings.jwt_algorithm)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200
    token = request_link(recovery)
    assert confirm(client, token).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401
    with pytest.raises(HTTPException):
        _resolve_user_from_jwt(str(user_id))


def test_newest_link_replaces_prior_and_failed_send_can_retry(recovery):
    from app.core.rate_limit import recovery_recipient_limiter

    client, _, mail, user_id = recovery
    first = request_link(recovery)
    # A repeat click within the cooldown changes neither the token nor credentials.
    request_link(recovery)
    assert mail.send.call_count == 1
    def age_request():
        with SessionLocal() as db:
            db.get(PasswordRecovery, user_id).requested_at -= timedelta(minutes=2)
            db.commit()
        recovery_recipient_limiter.reset()
    age_request()
    second = request_link(recovery)
    assert second != first
    assert confirm(client, first).status_code == 400
    age_request()
    mail.send.return_value = None
    failed = request_link(recovery)
    assert confirm(client, second).status_code == 400
    assert confirm(client, failed).status_code == 400
    with SessionLocal() as db:
        assert db.get(PasswordRecovery, user_id).delivery_status == "failed"
        assert db.get(PasswordRecovery, user_id).token_hash is None
        assert db.get(User, user_id).credential_version == 0
    age_request()
    mail.send.return_value = "accepted-after-retry"
    assert confirm(client, request_link(recovery)).status_code == 200


def test_device_reset_purges_linked_grant_and_cache_leaves_pending_and_other_users(recovery):
    from app.api.v1.auth_device import _PENDING_PLAINTEXT
    from app.models.device_authorization import DeviceAuthorizationGrant

    client, _, _, user_id = recovery
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}
    approved = client.post("/api/v1/auth/device/code").json()
    pending = client.post("/api/v1/auth/device/code").json()
    assert client.post("/api/v1/auth/device/approve", headers=headers, json={"user_code": approved["user_code"]}).status_code == 200
    with SessionLocal() as db:
        grant = db.query(DeviceAuthorizationGrant).filter_by(device_code=approved["device_code"]).one()
        grant_id = grant.id
        assert grant_id in _PENDING_PLAINTEXT
        other = User(email="other@controlled.org", display_name="Other", role="member", password_hash=hash_password("other-password"))
        service = User(email="machine@controlled.org", display_name="Machine", role="service", password_hash=hash_password("machine-password"))
        db.add_all([other, service])
        db.commit()
        others = [(u.id, create_access_token(subject=str(u.id))) for u in (other, service)]
    assert confirm(client, request_link(recovery)).status_code == 200
    assert grant_id not in _PENDING_PLAINTEXT
    assert client.post("/api/v1/auth/device/token", json={"device_code": approved["device_code"]}).status_code == 400
    assert client.post("/api/v1/auth/device/approve", headers=headers, json={"user_code": pending["user_code"]}).status_code == 401
    with SessionLocal() as db:
        assert db.query(DeviceAuthorizationGrant).filter_by(device_code=pending["device_code"], status="pending").count() == 1
        for identity, jwt_token in others:
            assert db.get(User, identity).credential_version == 0
            assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {jwt_token}"}).status_code == 200


@pytest.mark.asyncio
async def test_stale_principal_cannot_refresh_mint_key_approve_or_receive_events(recovery):
    from app.api.v1.auth import create_api_key, refresh_token
    from app.api.v1.auth_device import approve_device_grant
    from app.api.v1.mission_events import _visible_events
    from app.core.mission_events import MissionEvent
    from app.core.security import require_authenticated_user_sse
    from app.schemas.api_key import APIKeyCreate
    from app.schemas.device_auth import DeviceApproveRequest

    client, _, _, user_id = recovery
    principal = _resolve_user_from_jwt(str(user_id))
    old_token = create_access_token(subject=str(user_id))
    assert confirm(client, request_link(recovery)).status_code == 200
    with pytest.raises(HTTPException) as exc:
        await require_authenticated_user_sse(token=old_token)
    assert exc.value.status_code == 401
    with SessionLocal() as db:
        for operation in (
            lambda: refresh_token(principal, db),
            lambda: create_api_key(APIKeyCreate(name="stale"), principal, db),
            lambda: approve_device_grant(DeviceApproveRequest(user_code="BCDF-GHJK"), principal, db),
        ):
            with pytest.raises(HTTPException) as exc:
                operation()
            assert exc.value.status_code == 401
            db.rollback()
        with pytest.raises(HTTPException):
            _visible_events([MissionEvent(event_type="system.heartbeat", timestamp="now")], principal, db)


def test_budgets_are_independent_bounded_and_do_not_lock_out_login(recovery):
    from app.core.rate_limit import RateLimitConfig, RateLimiter, recovery_request_limiter

    client, _, _, _ = recovery
    for _ in range(5):
        assert client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@controlled.org"}).status_code == 202
    assert client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@controlled.org"}).status_code == 429
    assert client.post("/api/v1/auth/login", json={"email": "recover@controlled.org", "password": "original-password"}).status_code == 200
    recovery_request_limiter.reset()
    limiter = RateLimiter(RateLimitConfig(max_keys=2))
    limiter.check_key("one")
    limiter.check_key("two")
    with pytest.raises(HTTPException):
        limiter.check_key("three")
    assert len(limiter._requests) == 2


def test_unavailable_configuration_is_identical_for_all_accounts(recovery, monkeypatch):
    client, _, mail, _ = recovery
    monkeypatch.setattr(settings, "frontend_url", "http://localhost:3000")
    responses = [client.post("/api/v1/auth/password-reset/request", json={"email": email}) for email in ("recover@controlled.org", "unknown@controlled.org")]
    assert responses[0].status_code == responses[1].status_code == 503
    assert responses[0].json() == responses[1].json()
    mail.send.assert_not_called()


@pytest.mark.asyncio
async def test_already_open_event_stream_stops_after_reset(recovery, monkeypatch):
    import app.core.mission_events as events
    from app.api.v1.mission_events import stream_mission_events

    client, _, _, user_id = recovery
    principal = _resolve_user_from_jwt(str(user_id))
    bus = events.MissionEventBus()
    monkeypatch.setattr(events, "_event_bus", bus)
    bus.emit(events.MissionEvent(event_type="system.heartbeat", timestamp="before"))
    response = await stream_mission_events(limit=1, _user=principal)
    stream = response.body_iterator
    assert "before" in await anext(stream)
    assert confirm(client, request_link(recovery)).status_code == 200
    bus.emit(events.MissionEvent(event_type="system.heartbeat", timestamp="after"))
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert bus.subscriber_count == 0


@pytest.mark.asyncio
async def test_account_lookup_and_mail_begin_after_response_is_sent(recovery):
    import json

    _, service, _, _ = recovery
    messages = []
    async def dispatch(email):
        assert messages[-1]["type"] == "http.response.body"
        assert not messages[-1].get("more_body")
        assert email == "unknown@controlled.org"
    service.request = dispatch
    async def receive():
        return {"type": "http.request", "body": json.dumps({"email": "unknown@controlled.org"}).encode()}
    async def send(message):
        messages.append(message)
    await app({"type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
               "path": "/api/v1/auth/password-reset/request", "raw_path": b"/api/v1/auth/password-reset/request",
               "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")],
               "client": ("127.0.0.1", 1234), "server": ("testserver", 443)}, receive, send)
    assert messages[0]["status"] == 202


@pytest.mark.asyncio
async def test_provider_errors_never_log_echoed_reset_links(recovery, monkeypatch, caplog):
    import httpx

    from app.services import notifications
    from app.services.notifications import ResendClient

    _, service, _, _ = recovery
    # Alembic's fileConfig can disable already-imported application loggers when
    # migration tests run first. Make this secrecy assertion independent of order.
    monkeypatch.setattr(notifications.logger, "disabled", False)
    caplog.set_level("WARNING", logger=notifications.logger.name)
    service.sender = ResendClient()
    provider_body = "private token-bearing provider error"
    async def reject(*args, **kwargs):
        return httpx.Response(400, text=provider_body + str(kwargs["json"]), request=httpx.Request("POST", "https://api.resend.com/emails"))
    monkeypatch.setattr(httpx.AsyncClient, "post", reject)
    await service.request("recover@controlled.org")
    assert provider_body not in caplog.text
    assert "#token=" not in caplog.text
    assert "status=400" in caplog.text


def test_disabled_or_service_target_cannot_redeem_an_already_issued_link(recovery):
    client, _, _, user_id = recovery
    token = request_link(recovery)
    with SessionLocal() as db:
        db.get(User, user_id).is_active = False
        db.commit()
    assert confirm(client, token).status_code == 400
    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.is_active, user.role = True, "service"
        db.commit()
    assert confirm(client, token).status_code == 400


def test_admin_purge_remains_valid_with_a_recovery_row(recovery, auth_headers):
    client, _, _, user_id = recovery
    request_link(recovery)
    response = client.delete(f"/api/v1/admin/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.get(User, user_id) is None
        assert db.get(PasswordRecovery, user_id) is None


def test_link_waits_for_provider_acceptance_and_late_failure_cannot_revoke_replacement(recovery):
    import hashlib

    client, service, _, user_id = recovery
    digest, message, _ = service._prepare("recover@controlled.org")
    token = message.text.split("#token=", 1)[1].split()[0]
    # A crash between issuing and finishing a send leaves an unusable pending slot.
    assert confirm(client, token).status_code == 400
    service._finish(digest, True)
    with SessionLocal() as db:
        db.get(PasswordRecovery, user_id).requested_at -= timedelta(minutes=2)
        db.commit()
    replacement = request_link(recovery)
    service._finish(hashlib.sha256(token.encode()).hexdigest(), False)
    assert confirm(client, replacement).status_code == 200
