"""HMAC-SHA256 signer for outbound calls to DeepSearch (T40.4).

This module is the outbound inverse of
:meth:`app.services.webhook_handler.WebhookHandler.validate_signature`:
wherever TraceLab sends a service-to-service request to DeepSearch, it signs
the body here with the shared service secret; DeepSearch validates with the
same secret on the other end.

Signing envelope mirrors the receiver's expectations:

* Header:  ``X-TraceLab-Signature: sha256=<hex_digest>``
* Optional ``X-TraceLab-Timestamp`` header (ISO-8601 or unix seconds); when
  present, the signed message is ``"{timestamp}.{body}"``. When absent, the
  signed message is ``body`` alone. The receiver uses whichever form the
  sender picked — they must agree.

The signer uses :func:`settings.effective_deepsearch_service_secret`, which
prefers the new ``deepsearch_tracelab_service_secret`` env and falls back to
the legacy ``deepsearch_webhook_secret`` during the T40.4 transition.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


class HmacSigningError(RuntimeError):
    """Raised when the signer cannot produce a signed envelope.

    The primary reason is a missing shared secret in production; dev-fallback
    behavior (skipping signing) is intentionally opt-in, not default.
    """


@dataclass(frozen=True)
class SignedPayload:
    """Outbound body + HMAC headers ready for an httpx / requests call."""

    body: bytes
    headers: dict[str, str]


def sign_payload(
    body: bytes,
    *,
    include_timestamp: bool = True,
    secret: str | None = None,
) -> SignedPayload:
    """Sign ``body`` with HMAC-SHA256 and return the body + headers.

    Args:
        body: Raw request body bytes — pass the exact bytes that will go on
            the wire. Callers must serialize their JSON once and pass the
            same bytes through both :func:`sign_payload` and the HTTP client;
            re-serializing changes whitespace and invalidates the signature.
        include_timestamp: When ``True`` (default), the signer emits
            ``X-TraceLab-Timestamp`` with a unix-seconds value and signs
            ``"{timestamp}.{body}"``. When ``False``, signs ``body`` alone.
            Both forms are recognized by the receiver.
        secret: Optional explicit secret; when ``None`` (default) the signer
            reads ``settings.effective_deepsearch_service_secret``. Tests use
            the explicit form so they don't depend on env state.

    Returns:
        :class:`SignedPayload` with the (unchanged) body bytes plus the
        headers to merge into the outbound request.

    Raises:
        HmacSigningError: When no secret is configured and no explicit
            secret was supplied.
    """
    resolved_secret = secret if secret is not None else settings.effective_deepsearch_service_secret
    if not resolved_secret:
        raise HmacSigningError(
            "Cannot sign outbound DeepSearch request: no secret configured. "
            "Set TRACELAB_DEEPSEARCH_SERVICE_SECRET (preferred) or "
            "DEEPSEARCH_WEBHOOK_SECRET (transitional fallback)."
        )

    headers: dict[str, str] = {}
    if include_timestamp:
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{body.decode('utf-8')}"
        headers["X-TraceLab-Timestamp"] = timestamp
    else:
        message = body.decode("utf-8")

    digest = hmac.new(
        resolved_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers["X-TraceLab-Signature"] = f"sha256={digest}"

    return SignedPayload(body=body, headers=headers)


def verify_signature(
    body: bytes,
    signature_header: str | None,
    timestamp_header: str | None = None,
    *,
    secret: str | None = None,
) -> bool:
    """Verify an inbound signature produced by :func:`sign_payload`.

    Primarily used by tests (the production inbound path lives in
    :class:`app.services.webhook_handler.WebhookHandler`). Having both
    directions in one module makes round-trip tests obvious.

    Raises :class:`HmacSigningError` for malformed input or mismatch so tests
    can distinguish "didn't verify" from "had no way to check."
    """
    resolved_secret = secret if secret is not None else settings.effective_deepsearch_service_secret
    if not resolved_secret:
        raise HmacSigningError(
            "Cannot verify signature: no secret configured."
        )
    if not signature_header or not signature_header.startswith("sha256="):
        raise HmacSigningError(
            f"Invalid or missing signature header: {signature_header!r}"
        )

    provided = signature_header[len("sha256="):]
    if timestamp_header:
        message = f"{timestamp_header}.{body.decode('utf-8')}"
    else:
        message = body.decode("utf-8")

    expected = hmac.new(
        resolved_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(provided, expected)
