"""Mission emails go out once per terminal status, only to opted-in owners, and never block the webhook."""

import asyncio
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.mission import Mission
from app.models.user import User
from app.services import notifications
from app.services.notifications import Email, ResendClient, build_terminal_email, pending_terminal_notification

_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "resend_from_address", "TraceLab <notifications@tracelab.aquex.ai>")
    monkeypatch.setattr(settings, "notification_emails_enabled", True)
    monkeypatch.setattr(settings, "frontend_url", "https://tracelab.aquex.ai/")


def owner(db, **kwargs):
    user = User(email=f"{uuid4().hex}@owners.tracelab.aquex.ai", display_name="Owner", password_hash=_HASH, role="member", **kwargs)
    db.add(user)
    db.flush()
    return user


def mission(db, status="completed", **kwargs):
    row = Mission(
        mission_id=f"NOTIFY-{uuid4().hex[:6]}", title="Research the market", objective="Find the evidence",
        success_criteria=["Cite sources"], status=status, **kwargs,
    )
    db.add(row)
    db.commit()
    return row


def test_email_names_the_mission_status_and_links_to_it(configured, db_session):
    user = owner(db_session)
    row = mission(db_session, "validation_failed", owner_id=user.id, error_message="Two claims lacked sources")
    email = build_terminal_email(row, user.email)
    assert email.subject == "Mission failed validation: Research the market"
    assert f"https://tracelab.aquex.ai/missions/{row.id}" in email.text
    assert "Two claims lacked sources" in email.html and "<script" not in email.html


def test_nothing_is_due_without_config_owner_opt_in_or_terminal_status(configured, db_session, monkeypatch):
    user = owner(db_session)
    row = mission(db_session, "completed", owner_id=user.id)
    assert pending_terminal_notification(db_session, row.id) is not None
    monkeypatch.setattr(settings, "resend_api_key", None)
    assert pending_terminal_notification(db_session, row.id) is None
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    user.email_notifications_enabled = False
    db_session.commit()
    assert pending_terminal_notification(db_session, row.id) is None
    user.email_notifications_enabled = True
    user.is_active = False
    db_session.commit()
    assert pending_terminal_notification(db_session, row.id) is None
    user.is_active = True
    db_session.commit()
    assert pending_terminal_notification(db_session, mission(db_session, "completed").id) is None
    assert pending_terminal_notification(db_session, mission(db_session, "cancelled", owner_id=user.id).id) is None
    assert pending_terminal_notification(db_session, mission(db_session, "in_progress", owner_id=user.id).id) is None
    assert pending_terminal_notification(db_session, uuid4()) is None


@pytest.mark.parametrize(
    ("address", "deliverable"),
    [
        ("owner@tracelab.aquex.ai", True),
        ("Owner.Name@Mail.Aquex.AI", True),
        ("owner@tracelab.local", False),
        ("owner@example.com", False),
        ("owner@lists.example.org", False),
        ("owner@example.test", False),
        ("root@localhost", False),
        ("no-at-sign", False),
        ("@tracelab.aquex.ai", False),
        ("", False),
        (None, False),
    ],
)
def test_reserved_and_local_only_domains_are_not_deliverable(address, deliverable):
    assert notifications.deliverable_address(address) is deliverable


def test_an_owner_at_an_undeliverable_address_gets_no_claim_and_no_request(configured, db_session, httpx_mock, monkeypatch):
    user = owner(db_session)
    user.email = "owner@tracelab.local"
    row = mission(db_session, "completed", owner_id=user.id)
    import app.core.database as database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    assert pending_terminal_notification(db_session, row.id) is None
    assert asyncio.run(notifications.notify_terminal_status(row.id)) is False
    assert httpx_mock.get_requests() == []
    db_session.refresh(row)
    assert "notification" not in (row.execution_metadata or {})


def test_sends_once_per_status_and_again_when_the_status_changes(configured, db_session, httpx_mock, monkeypatch):
    user = owner(db_session)
    row = mission(db_session, "completed", owner_id=user.id, execution_metadata={"loops_executed": 2})
    monkeypatch.setattr(notifications, "SessionLocal", lambda: db_session, raising=False)
    import app.core.database as database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    httpx_mock.add_response(url=notifications.RESEND_ENDPOINT, json={"id": "msg_1"})
    assert asyncio.run(notifications.notify_terminal_status(row.id)) is True
    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer re_test_key"
    body = request.read().decode()
    assert user.email in body and "Research the market" in body
    db_session.refresh(row)
    assert row.execution_metadata["notification"]["status"] == "completed"
    assert row.execution_metadata["notification"]["message_id"] == "msg_1"
    assert row.execution_metadata["loops_executed"] == 2
    # Same status again: nothing due, no request.
    assert asyncio.run(notifications.notify_terminal_status(row.id)) is False
    assert len(httpx_mock.get_requests()) == 1
    row.status = "blocked"
    db_session.commit()
    httpx_mock.add_response(url=notifications.RESEND_ENDPOINT, json={"id": "msg_2"})
    assert asyncio.run(notifications.notify_terminal_status(row.id)) is True
    assert row.execution_metadata["notification"]["status"] == "blocked"


def test_provider_failures_are_logged_and_leave_the_mission_unmarked(configured, httpx_mock):
    client = ResendClient(timeout=1.0)
    email = Email(to="a@example.test", subject="s", text="t", html="<p>t</p>")
    httpx_mock.add_response(url=notifications.RESEND_ENDPOINT, status_code=422, json={"message": "bad from"})
    assert asyncio.run(client.send(email)) is None
    httpx_mock.add_exception(httpx.ConnectError("down"))
    httpx_mock.add_response(url=notifications.RESEND_ENDPOINT, json={"id": "msg_retry"})
    assert asyncio.run(client.send(email)) == "msg_retry"


def test_a_duplicate_webhook_cannot_claim_a_status_already_being_sent(configured, db_session):
    user = owner(db_session)
    row = mission(db_session, "completed", owner_id=user.id)
    first = notifications.claim_terminal_notification(db_session, row.id)
    assert first is not None
    # While the first send is in flight, a second delivery of the same webhook finds the status taken.
    assert notifications.claim_terminal_notification(db_session, row.id) is None
    _, _, claim = first
    notifications.finish_notification(db_session, row, claim, "msg_1")
    db_session.refresh(row)
    assert row.execution_metadata["notification"]["message_id"] == "msg_1"
    assert notifications.claim_terminal_notification(db_session, row.id) is None


def test_a_rejected_send_releases_the_claim_so_the_mission_stays_unmarked(configured, db_session, httpx_mock, monkeypatch):
    user = owner(db_session)
    row = mission(db_session, "validation_failed", owner_id=user.id)
    import app.core.database as database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    httpx_mock.add_response(url=notifications.RESEND_ENDPOINT, status_code=422, json={"message": "domain not verified"})
    assert asyncio.run(notifications.notify_terminal_status(row.id)) is False
    db_session.refresh(row)
    assert "notification" not in (row.execution_metadata or {})
    assert notifications.claim_terminal_notification(db_session, row.id) is not None


def test_webhook_schedules_the_notification_after_responding(configured, db_session, monkeypatch):
    calls = []

    async def fake_notify(mission_id, client=None):
        calls.append(mission_id)
        return True

    monkeypatch.setattr("app.api.v1.webhooks.notify_terminal_status", fake_notify)
    monkeypatch.setattr(settings, "deepsearch_tracelab_service_secret", None, raising=False)
    monkeypatch.setattr(settings, "deepsearch_service_secret", None, raising=False)
    user = owner(db_session)
    row = mission(db_session, "in_progress", owner_id=user.id, deepsearch_job_id="ds-job-1")
    with TestClient(app) as client:
        response = client.post("/api/v1/webhooks/deepsearch", json={
            "job_id": "ds-job-1", "mission_id": row.mission_id, "status": "complete", "result_markdown": "# Done",
        })
    assert response.status_code == 200, response.text
    assert calls == [row.id]


def test_profile_toggle_round_trips(db_session):
    from app.core.security import create_access_token

    user = owner(db_session)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me", headers=headers).json()["email_notifications_enabled"] is True
        updated = client.patch("/api/v1/auth/me", headers=headers, json={"email_notifications_enabled": False})
        assert updated.status_code == 200, updated.text
        assert updated.json()["email_notifications_enabled"] is False
        assert client.get("/api/v1/auth/me", headers=headers).json()["email_notifications_enabled"] is False
    assert datetime.utcnow() is not None
