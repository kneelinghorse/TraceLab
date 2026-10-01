"""Forward mail for the fixed Stage1 and Aquex support addresses to their owner.

Resend Inbound receives every message for aquex.ai and calls the webhook with metadata only. A message addressed
to stage1@aquex.ai or hello@aquex.ai is fetched and re-sent to SUPPORT_FORWARD_TO, with the original sender as reply-to, so a reply
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
from email.utils import getaddresses

import httpx

from app.core.config import settings

SUPPORT_ADDRESSES = ("stage1@aquex.ai", "hello@aquex.ai")
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


def matched_support_addresses(data: Mapping[str, object]) -> tuple[str, ...]:
    """Parse signed envelope mailboxes, returning unique matches in configured order."""
    recipients = []
    for field in ("to", "cc", "bcc"):
        value = data.get(field)
        if isinstance(value, str):
            recipients.append(value)
        elif isinstance(value, list):
            recipients.extend(address for address in value if isinstance(address, str))
    mailboxes = {address.casefold() for _, address in getaddresses(recipients)}
    return tuple(address for address in SUPPORT_ADDRESSES if address in mailboxes)


async def forward(email_id: str, matched_addresses: tuple[str, ...]) -> str:
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
        # Use the verified envelope: fetched content may omit bcc recipients.
        labels = ", ".join(matched_addresses)
        intro = f"Forwarded from {labels}. From: {sender}. Received: {received.get('created_at')}."
        payload = {
            "from": settings.resend_from_address,
            "to": [settings.support_forward_to],
            "reply_to": received.get("reply_to") or [sender],
            "subject": f"[{labels}] {received.get('subject') or '(no subject)'}",
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
