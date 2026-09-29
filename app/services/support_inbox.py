"""Forward mail for Stage1's support address to its owner (Stage1 s97-m02, decision 1105).

Resend Inbound receives every message for aquex.ai and calls the webhook with metadata only. A message addressed
to stage1@aquex.ai is fetched and re-sent to SUPPORT_FORWARD_TO, with the original sender as reply-to, so a reply
reaches the person who wrote in. Bodies and addresses are never logged. The received message id is the send's
idempotency key, so a Resend retry cannot deliver the same message twice.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import time
from collections.abc import Mapping

import httpx

from app.core.config import settings

SUPPORT_ADDRESS = "stage1@aquex.ai"
RESEND_API = "https://api.resend.com"
SIGNATURE_TOLERANCE_SECONDS = 300


def signature_valid(secret: str, headers: Mapping[str, str], body: bytes, now: float | None = None) -> bool:
    """Resend signs webhooks with the Svix scheme: base64 HMAC-SHA256 of "id.timestamp.body" under the whsec_ key."""
    message_id, timestamp, signatures = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (message_id and timestamp and signatures):
        return False
    try:
        if abs((time.time() if now is None else now) - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except ValueError:  # includes binascii.Error from a malformed key
        return False
    digest = hmac.new(key, f"{message_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return any(hmac.compare_digest(expected, part[3:]) for part in signatures.split() if part.startswith("v1,"))


def addressed_to_support(data: Mapping[str, object]) -> bool:
    """True when the support address is among the message's recipients, as it is also for a cc or bcc."""
    recipients = [*(data.get("to") or []), *(data.get("cc") or []), *(data.get("bcc") or [])]
    return any(SUPPORT_ADDRESS in str(address).lower() for address in recipients)


async def forward(email_id: str) -> str:
    """Fetch a received message and re-send it to the owner; return the provider id.

    Raises httpx.HTTPError when Resend refuses a call, so the webhook answers 5xx and Resend retries.
    """
    auth = {"Authorization": f"Bearer {settings.resend_inbound_api_key}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{RESEND_API}/emails/receiving/{email_id}", headers=auth)
        response.raise_for_status()
        received = response.json()
        attachments = []
        if received.get("attachments"):
            # Resend fetches each file itself from the signed URL, so the bytes never pass through TraceLab.
            response = await client.get(f"{RESEND_API}/emails/receiving/{email_id}/attachments", headers=auth)
            response.raise_for_status()
            attachments = [{"filename": item["filename"], "path": item["download_url"]} for item in response.json().get("data", [])]
        sender = received.get("from") or "an unknown sender"
        intro = f"Forwarded from {SUPPORT_ADDRESS}. From: {sender}. Received: {received.get('created_at')}."
        payload = {
            "from": settings.resend_from_address,
            "to": [settings.support_forward_to],
            "reply_to": received.get("reply_to") or [sender],
            "subject": f"[{SUPPORT_ADDRESS}] {received.get('subject') or '(no subject)'}",
            "text": f"{intro}\n\n{received.get('text') or ''}",
        }
        if received.get("html"):
            payload["html"] = f"<p>{html.escape(intro)}</p>{received['html']}"
        if attachments:
            payload["attachments"] = attachments
        response = await client.post(
            f"{RESEND_API}/emails", json=payload, headers={**auth, "Idempotency-Key": f"stage1-support-{email_id}"}
        )
        response.raise_for_status()
        return str(response.json().get("id", ""))
