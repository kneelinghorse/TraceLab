"""Mail for stage1@aquex.ai reaches its owner, and nothing else gets through (Stage1 s97-m02, decision 1105).

Resend Inbound delivers every message for aquex.ai to one webhook. So the route must prove each call came from
Resend, forward only the support address, keep message bodies and addresses out of the logs, and let Resend's
retries arrive without a second delivery.
"""

import base64
import hashlib
import hmac
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import support_inbox

SECRET = "whsec_" + base64.b64encode(b"s97-m02-synthetic-signing-key").decode()  # secret-scan: allow -- synthetic signing key fixture
URL = "/api/v1/webhooks/resend-inbound"
RECEIVED = f"{support_inbox.RESEND_API}/emails/receiving/rcv-1"
SEND = f"{support_inbox.RESEND_API}/emails"
# No `with`: the app's startup events reach external services, and this route needs none of them.
client = TestClient(app)
OWNER = "owner@owners.tracelab.aquex.ai"
VISITOR = "Visitor <visitor@example.org>"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "resend_inbound_api_key", "re_inbound_test_key")
    monkeypatch.setattr(settings, "support_forward_to", OWNER)
    monkeypatch.setattr(settings, "resend_from_address", "TraceLab <notifications@aquex.ai>")


def signed(event: dict, secret: str = SECRET, timestamp: int | None = None) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    sent_at = str(int(time.time()) if timestamp is None else timestamp)
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signature = base64.b64encode(hmac.new(key, f"msg_1.{sent_at}.".encode() + body, hashlib.sha256).digest()).decode()
    return body, {"svix-id": "msg_1", "svix-timestamp": sent_at, "svix-signature": f"v1,{signature}", "content-type": "application/json"}


def event(to=("stage1@aquex.ai",), kind="email.received", **data) -> dict:
    return {"type": kind, "created_at": "2026-09-29T00:00:00Z",
            "data": {"email_id": "rcv-1", "to": list(to), "from": VISITOR, "subject": "Capture failed", **data}}


def post(payload: dict, **signing):
    body, headers = signed(payload, **signing)
    return client.post(URL, content=body, headers=headers)


def received(**fields) -> dict:
    return {"object": "email", "id": "rcv-1", "from": VISITOR, "to": ["stage1@aquex.ai"], "subject": "Capture failed",
            "text": "The capture stopped at page 3.", "html": "<p>The capture stopped at page 3.</p>", "reply_to": [],
            "attachments": [], "created_at": "2026-09-29T00:00:00Z", **fields}


def test_the_signature_follows_resend_svix_scheme():
    body, headers = signed(event())
    now = int(headers["svix-timestamp"])
    assert support_inbox.signature_valid(SECRET, headers, body, now=now)
    assert not support_inbox.signature_valid(SECRET, headers, body + b" ", now=now), "a changed body fails"
    assert not support_inbox.signature_valid("whsec_" + base64.b64encode(b"another").decode(), headers, body, now=now)
    assert not support_inbox.signature_valid(SECRET, headers, body, now=now + 301), "an old signature cannot be replayed"
    assert not support_inbox.signature_valid(SECRET, {**headers, "svix-signature": ""}, body, now=now)
    rotated = {**headers, "svix-signature": f"v1,bm90LXRoaXMtb25l {headers['svix-signature']}"}
    assert support_inbox.signature_valid(SECRET, rotated, body, now=now), "any one valid v1 signature is enough"


def test_the_route_fails_closed_until_it_is_configured(monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "resend_webhook_secret", None)
    response = post(event())
    assert response.status_code == 503
    assert httpx_mock.get_requests() == []


def test_unsigned_forged_and_stale_calls_are_refused(configured, httpx_mock):
    body, _ = signed(event())
    assert client.post(URL, content=body, headers={"content-type": "application/json"}).status_code == 401
    assert post(event(), secret="whsec_" + base64.b64encode(b"forged").decode()).status_code == 401
    assert post(event(), timestamp=int(time.time()) - 3600).status_code == 401
    assert httpx_mock.get_requests() == [], "nothing is fetched or sent for a call Resend did not sign"


def test_only_mail_for_the_support_address_is_forwarded(configured, httpx_mock):
    assert post(event(to=("hello@aquex.ai",))).json() == {"status": "ignored"}
    assert post(event(kind="email.delivered")).json() == {"status": "ignored"}
    assert httpx_mock.get_requests() == []
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-cc"})
    assert post(event(to=("hello@aquex.ai",), cc=["Stage1 <stage1@aquex.ai>"])).json() == {"status": "forwarded"}


def test_support_mail_reaches_the_owner_with_the_sender_as_reply_to(configured, httpx_mock):
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-1"})
    response = post(event())
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "forwarded"}
    fetch, send = httpx_mock.get_requests()
    assert fetch.headers["Authorization"] == "Bearer re_inbound_test_key"
    sent = json.loads(send.content)
    assert sent["to"] == [OWNER] and sent["from"] == "TraceLab <notifications@aquex.ai>"
    assert sent["reply_to"] == [VISITOR], "a reply goes to the person who wrote in"
    assert sent["subject"] == "[stage1@aquex.ai] Capture failed"
    assert "Forwarded from stage1@aquex.ai" in sent["text"] and "The capture stopped at page 3." in sent["text"]
    assert sent["html"].endswith("<p>The capture stopped at page 3.</p>")
    assert "attachments" not in sent
    assert send.headers["Idempotency-Key"] == "stage1-support-rcv-1", "a Resend retry cannot deliver twice"


def test_attachments_travel_by_signed_url(configured, httpx_mock):
    listing = {"object": "list", "data": [{"id": "att-1", "filename": "trace.har", "size": 2048, "content_type": "application/json",
                                           "download_url": "https://inbound-cdn.resend.com/att-1?signature=s", "expires_at": "2026-10-01T00:00:00Z"}]}
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received(attachments=[{"id": "att-1", "filename": "trace.har"}]))
    httpx_mock.add_response(url=f"{RECEIVED}/attachments", method="GET", json=listing)
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-2"})
    assert post(event()).json() == {"status": "forwarded"}
    sent = json.loads(httpx_mock.get_request(method="POST").content)
    assert sent["attachments"] == [{"filename": "trace.har", "path": "https://inbound-cdn.resend.com/att-1?signature=s"}]


def test_a_refused_fetch_answers_502_so_resend_retries_and_logs_only_the_id(configured, httpx_mock, caplog):
    httpx_mock.add_response(url=RECEIVED, method="GET", status_code=500, json={"message": "unavailable"})
    with caplog.at_level(logging.INFO):
        response = post(event())
    assert response.status_code == 502
    assert "rcv-1" in caplog.text
    for private in ("visitor@example.org", "The capture stopped", OWNER):
        assert private not in caplog.text


def test_a_forward_logs_no_body_or_address(configured, httpx_mock, caplog):
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-3"})
    with caplog.at_level(logging.DEBUG, logger="app"):
        assert post(event()).status_code == 200
    for private in ("visitor@example.org", "The capture stopped", OWNER):
        assert private not in caplog.text
