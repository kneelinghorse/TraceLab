"""Mail for Stage1 and hello reaches the owner, and nothing else gets through (Stage1 s97-m02, decision 1105).

Resend Inbound delivers every message for aquex.ai to one webhook. So the route must prove each call came from
Resend, forward only the two support addresses, keep message bodies and addresses out of the logs, and let Resend's
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
            "data": {"email_id": "rcv-1", "to": to if isinstance(to, str) else list(to), "from": VISITOR, "subject": "Capture failed", **data}}


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


@pytest.mark.parametrize("setting", ["resend_webhook_secret", "resend_inbound_api_key", "support_forward_to", "resend_from_address"])
def test_the_route_fails_closed_until_it_is_configured(configured, monkeypatch, httpx_mock, setting):
    monkeypatch.setattr(settings, setting, None)
    response = post(event())
    assert response.status_code == 503
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("recipient", ["stage1@aquex.ai", "hello@aquex.ai"])
def test_unsigned_forged_and_stale_calls_are_refused(configured, httpx_mock, recipient):
    payload = event(to=(recipient,))
    body, _ = signed(payload)
    assert client.post(URL, content=body, headers={"content-type": "application/json"}).status_code == 401
    assert post(payload, secret="whsec_" + base64.b64encode(b"forged").decode()).status_code == 401
    assert post(payload, timestamp=int(time.time()) - 3600).status_code == 401
    assert httpx_mock.get_requests() == [], "nothing is fetched or sent for a call Resend did not sign"


@pytest.mark.parametrize("recipients,labels", [
    ({"to": ("hello@aquex.ai",)}, "hello@aquex.ai"),
    ({"to": "Hello <HELLO@AQUEX.AI>"}, "hello@aquex.ai"),
    ({"to": ("Stage1 <STAGE1@AQUEX.AI>",)}, "stage1@aquex.ai"),
    ({"to": ("other@example.org",), "cc": ["Hello <hello@aquex.ai>"]}, "hello@aquex.ai"),
    ({"to": (), "bcc": "hello@aquex.ai"}, "hello@aquex.ai"),
    ({"to": ("hello@aquex.ai", "stage1@aquex.ai", "HELLO@AQUEX.AI"), "cc": ["stage1@aquex.ai"]}, "stage1@aquex.ai, hello@aquex.ai"),
    ({"to": ("hello@aquex.ai",), "bcc": ["Stage1 <stage1@aquex.ai>"]}, "stage1@aquex.ai, hello@aquex.ai"),
])
def test_verified_recipients_label_one_forward_even_when_fetched_mail_omits_bcc(configured, httpx_mock, recipients, labels):
    # The fetched content intentionally omits bcc and reports only Stage1. Labels
    # must come from the signed envelope, not from this incomplete body fetch.
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-cc"})
    assert post(event(**recipients)).json() == {"status": "forwarded"}
    sends = httpx_mock.get_requests(method="POST")
    assert len(sends) == 1, "one forward per email, even when both addresses match"
    payload = json.loads(sends[0].content)
    assert payload["subject"] == f"[{labels}] Capture failed"
    assert payload["text"].startswith(f"Forwarded from {labels}.")
    assert payload["html"].startswith(f"<p>Forwarded from {labels}.")
    assert sends[0].headers["Idempotency-Key"] == "stage1-support-rcv-1"


@pytest.mark.parametrize("recipients", [
    {"to": ("other@aquex.ai",)},
    {"to": ("nothello@aquex.ai",)},
    {"to": ("stage1@aquex.ai.attacker.example",)},
    {"to": ('"stage1@aquex.ai" <other@example.org>',)},
    {"to": ('"hello@aquex.ai" <other@example.org>',)},
    {"to": (), "cc": ["hello@aquex.ai.evil.example"], "bcc": ["notstage1@aquex.ai"]},
    {"to": (), "cc": None, "bcc": None},
])
def test_unrelated_lookalike_and_display_name_recipients_never_fetch_or_send(configured, httpx_mock, recipients):
    assert post(event(**recipients)).json() == {"status": "ignored"}
    assert httpx_mock.get_requests() == []


def test_non_received_events_are_ignored(configured, httpx_mock):
    assert post(event(kind="email.delivered")).json() == {"status": "ignored"}
    assert httpx_mock.get_requests() == []


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


@pytest.mark.parametrize("recipient", ["stage1@aquex.ai", "hello@aquex.ai"])
def test_attachments_travel_by_signed_url(configured, httpx_mock, recipient):
    listing = {"object": "list", "data": [{"id": "att-1", "filename": "trace.har", "size": 2048, "content_type": "application/json",
                                           "download_url": "https://inbound-cdn.resend.com/att-1?signature=s", "expires_at": "2026-10-01T00:00:00Z"}]}
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received(attachments=[{"id": "att-1", "filename": "trace.har"}]))
    httpx_mock.add_response(url=f"{RECEIVED}/attachments", method="GET", json=listing)
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-2"})
    assert post(event(to=(recipient,))).json() == {"status": "forwarded"}
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


@pytest.mark.parametrize("reply_to", [[], ["replies@example.org"]])
@pytest.mark.parametrize("html_body", [None, "<p>Original message</p>"])
def test_plain_html_and_explicit_reply_destination_survive_forwarding(configured, httpx_mock, reply_to, html_body):
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received(reply_to=reply_to, html=html_body, subject=None))
    httpx_mock.add_response(url=SEND, method="POST", json={"id": "fwd-content"})
    assert post(event(to=("hello@aquex.ai",))).status_code == 200
    payload = json.loads(httpx_mock.get_request(method="POST").content)
    assert payload["reply_to"] == (reply_to or [VISITOR])
    assert payload["subject"] == "[hello@aquex.ai] (no subject)"
    assert "The capture stopped at page 3." in payload["text"]
    if html_body:
        assert payload["html"].endswith(html_body)
        assert "&lt;visitor@example.org&gt;" in payload["html"], "the generated intro escapes sender markup"
    else:
        assert "html" not in payload


def test_dual_address_redelivery_keeps_the_pre_rollout_idempotency_namespace(configured, httpx_mock):
    for _ in range(2):
        httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
        httpx_mock.add_response(url=SEND, method="POST", json={"id": "same-forward"})
        assert post(event(to=("hello@aquex.ai", "stage1@aquex.ai"))).status_code == 200
    sends = httpx_mock.get_requests(method="POST")
    assert len(sends) == 2, "one send attempt per delivery, never one per recipient"
    assert {request.headers["Idempotency-Key"] for request in sends} == {"stage1-support-rcv-1"}
    assert sends[0].content == sends[1].content, "provider deduplication requires the same key and payload"


def test_failed_send_is_retryable_without_changing_idempotency_or_leaking_content(configured, httpx_mock, caplog):
    for status in [500, 200]:
        httpx_mock.add_response(url=RECEIVED, method="GET", json=received())
        httpx_mock.add_response(url=SEND, method="POST", status_code=status, json={"id": "fwd-retry"})
        with caplog.at_level(logging.INFO, logger="app"):
            assert post(event(to=("hello@aquex.ai",))).status_code == (502 if status == 500 else 200)
    assert {request.headers["Idempotency-Key"] for request in httpx_mock.get_requests(method="POST")} == {"stage1-support-rcv-1"}
    for private in ("visitor@example.org", "hello@aquex.ai", "The capture stopped", OWNER, "re_inbound_test_key", SECRET):
        assert private not in caplog.text


def test_failed_attachment_listing_retries_without_sending_an_incomplete_forward(configured, httpx_mock):
    httpx_mock.add_response(url=RECEIVED, method="GET", json=received(attachments=[{"id": "att-1"}]))
    httpx_mock.add_response(url=f"{RECEIVED}/attachments", method="GET", status_code=503)
    assert post(event(to=("hello@aquex.ai",))).status_code == 502
    assert httpx_mock.get_requests(method="POST") == [], "retry the complete message rather than silently lose an attachment"
