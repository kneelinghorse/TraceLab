"""Admins may send recovery mail, never choose another user's password or mailbox."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies import get_password_recovery_service
from app.main import app
from app.models.password_recovery import PasswordRecovery, PasswordRecoveryAudit
from app.models.user import User
from app.services.password_recovery import PasswordRecoveryService


@pytest.fixture
def admin_recovery(monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://tracelab.test")
    monkeypatch.setattr(settings, "resend_api_key", "isolated-mail")
    monkeypatch.setattr(settings, "resend_from_address", "recovery@tracelab.test")
    monkeypatch.setattr(settings, "notification_emails_enabled", False)
    monkeypatch.setattr(settings, "rbac_enabled", True)
    mail = AsyncMock()
    mail.send.return_value = "provider-accepted"
    service = PasswordRecoveryService(SessionLocal, mail)
    monkeypatch.setitem(app.dependency_overrides, get_password_recovery_service, lambda: service)
    with SessionLocal() as db:
        caller = User(email="admin@controlled.org", display_name="Admin", role="admin", password_hash=hash_password("original-password"))
        target = User(email="recover@controlled.org", display_name="Recover", role="member", password_hash=hash_password("original-password"))
        db.add_all([caller, target])
        db.commit()
        caller_id, target_id = caller.id, target.id
    return TestClient(app), mail, caller_id, target_id


def send(fixture, *, target_id=None, body=None, authenticated=True):
    client, _, caller_id, default_target = fixture
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(caller_id))}"} if authenticated else {}
    return client.post(f"/api/v1/admin/users/{target_id or default_target}/password-reset", json={} if body is None else body, headers=headers)


@pytest.mark.parametrize("caller_role", ["admin", "owner"])
@pytest.mark.parametrize("target_role", ["member", "viewer", "admin", "owner", "self"])
def test_privileged_humans_can_send_to_every_eligible_target_without_changing_credentials(admin_recovery, caller_role, target_role):
    _, mail, caller_id, target_id = admin_recovery
    with SessionLocal() as db:
        db.get(User, caller_id).role = caller_role
        if target_role == "self":
            target_id = caller_id
        else:
            db.get(User, target_id).role = target_role
        db.commit()
    response = send(admin_recovery, target_id=target_id)
    assert response.status_code == 200
    assert response.json()["delivery_status"] == "accepted"
    assert "delivered" not in response.json()["message"].lower()
    message = mail.send.call_args.args[0]
    token = message.text.split("#token=", 1)[1].split()[0]
    assert token not in response.text
    with SessionLocal() as db:
        user = db.get(User, target_id)
        assert message.to == user.email
        assert user.credential_version == 0 and user.is_active
        assert verify_password("original-password", user.password_hash)
        audit = db.query(PasswordRecoveryAudit).one()
        assert (audit.actor_user_id, audit.target_user_id, audit.outcome) == (caller_id, target_id, "accepted")
        assert audit.completed_at >= audit.requested_at
        assert token not in str(vars(audit)) and message.to not in str(vars(audit))


@pytest.mark.parametrize("role", ["member", "viewer", "service", None])
def test_unprivileged_callers_never_send_or_create_an_audit(admin_recovery, role):
    _, mail, caller_id, _ = admin_recovery
    if role:
        with SessionLocal() as db:
            db.get(User, caller_id).role = role
            db.commit()
    assert send(admin_recovery, authenticated=role is not None).status_code == (403 if role else 401)
    mail.send.assert_not_called()
    with SessionLocal() as db:
        assert db.query(PasswordRecoveryAudit).count() == 0


@pytest.mark.parametrize("field,value,reason", [("is_active", False, "disabled"), ("role", "service", "service"), ("email", "local@tracelab.local", "deliverable")])
def test_ineligible_target_is_explained_and_never_changed(admin_recovery, field, value, reason):
    _, mail, _, target_id = admin_recovery
    with SessionLocal() as db:
        setattr(db.get(User, target_id), field, value)
        db.commit()
    response = send(admin_recovery)
    assert response.status_code == 400 and reason in response.json()["detail"].lower()
    mail.send.assert_not_called()
    with SessionLocal() as db:
        assert getattr(db.get(User, target_id), field) == value
        assert db.get(PasswordRecovery, target_id) is None
        assert db.query(PasswordRecoveryAudit).one().outcome == "ineligible"


def test_recipient_and_redirect_overrides_are_rejected(admin_recovery):
    response = send(admin_recovery, body={"email": "attacker@controlled.org", "redirect_url": "https://controlled.org"})
    assert response.status_code == 422
    admin_recovery[1].send.assert_not_called()


def test_repeat_requests_share_public_cooldown_and_recipient_budget(admin_recovery):
    client, mail, _, target_id = admin_recovery
    assert send(admin_recovery).status_code == 200
    assert send(admin_recovery).status_code == 429
    assert client.post("/api/v1/auth/password-reset/request", json={"email":"recover@controlled.org"}).status_code == 202
    with SessionLocal() as db:
        row = db.get(PasswordRecovery, target_id)
        row.requested_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
    assert send(admin_recovery).status_code == 429  # Shared recipient budget, not another mail path.
    assert mail.send.call_count == 1
    with SessionLocal() as db:
        assert [r.outcome for r in db.query(PasswordRecoveryAudit).order_by(PasswordRecoveryAudit.requested_at)] == ["accepted", "rate_limited", "rate_limited"]


def test_send_failure_is_audited_without_credentials_and_retry_replaces_link(admin_recovery):
    _, mail, _, target_id = admin_recovery
    mail.send.return_value = None
    response = send(admin_recovery)
    assert response.status_code == 503
    with SessionLocal() as db:
        recovery = db.get(PasswordRecovery, target_id)
        assert recovery.token_hash is None and recovery.delivery_status == "failed"
        assert db.query(PasswordRecoveryAudit).one().outcome == "failed"
        recovery.requested_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
    mail.send.return_value = "provider-accepted"
    assert send(admin_recovery).status_code == 200
    with SessionLocal() as db:
        assert {r.outcome for r in db.query(PasswordRecoveryAudit)} == {"failed", "accepted"}
        assert db.get(User, target_id).credential_version == 0


def test_pending_admin_audit_and_late_failure_preserve_newer_link(admin_recovery):
    import hashlib

    client, _, caller_id, target_id = admin_recovery
    service = app.dependency_overrides[get_password_recovery_service]()
    digest, message, audit_id = service._prepare(None, target_user_id=target_id, actor_user_id=caller_id)
    first_token = message.text.split("#token=", 1)[1].split()[0]
    with SessionLocal() as db:
        assert db.get(PasswordRecoveryAudit, audit_id).outcome == "pending"
        assert db.get(PasswordRecoveryAudit, audit_id).completed_at is None
        row = db.get(PasswordRecovery, target_id)
        row.requested_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
    response = client.post("/api/v1/auth/password-reset/confirm", json={"token":first_token,"new_password":"replacement-password","confirm_password":"replacement-password"})
    assert response.status_code == 400  # Provider has not acknowledged this admin request.
    assert send(admin_recovery).status_code == 200
    second_token = admin_recovery[1].send.call_args.args[0].text.split("#token=", 1)[1].split()[0]
    service._finish(digest, False, audit_id)
    with SessionLocal() as db:
        assert db.get(PasswordRecoveryAudit, audit_id).outcome == "failed"
        assert db.get(PasswordRecovery, target_id).token_hash == hashlib.sha256(second_token.encode()).hexdigest()
        assert db.get(PasswordRecovery, target_id).delivery_status == "accepted"
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token":second_token,"new_password":"replacement-password","confirm_password":"replacement-password"}).status_code == 200


@pytest.mark.parametrize("http_exception", [False, True])
def test_admin_audit_survives_user_purge_and_sender_exception_is_private(admin_recovery, caplog, http_exception):
    import logging

    client, mail, caller_id, target_id = admin_recovery
    logging.getLogger("app.services.password_recovery").disabled = False
    marker = "PRIVATE_PROVIDER_EXCEPTION_BODY"
    mail.send.side_effect = HTTPException(502, detail=marker) if http_exception else ValueError(marker)
    response = send(admin_recovery)
    assert response.status_code == 503
    assert marker not in response.text and marker not in caplog.text
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(caller_id))}"}
    assert client.delete(f"/api/v1/admin/users/{target_id}", headers=headers).status_code == 200
    with SessionLocal() as db:
        audit = db.query(PasswordRecoveryAudit).one()
        assert audit.target_user_id == target_id and audit.outcome == "failed"
        assert db.get(PasswordRecovery, target_id) is None
