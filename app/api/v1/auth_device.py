"""Device-authorization (RFC 8628) endpoints — T42.4.

Lets the TraceLab MCP client log in interactively without the installer
hand-pasting an API key into env. Flow:

1. ``POST /api/v1/auth/device/code`` — MCP client requests a grant.
   Server mints ``device_code`` (random, never shown to user) and
   ``user_code`` (short, human-readable) and returns the verification URL.
2. MCP client prints ``Open <verification_uri>`` + ``Code: <user_code>`` to
   stderr and starts polling ``POST /api/v1/auth/device/token``.
3. Human visits the URL on a normal browser session, logs in (existing TL
   web auth), and approves the user_code via
   ``POST /api/v1/auth/device/approve``.
4. Approval mints a ``tl_*`` API key on the user's behalf via the existing
   ``api_keys`` table. Next ``/device/token`` poll returns 200 with the key.

Wire shape mirrors the cmos-mcp client contract verbatim so the
already-tested device-code module can be ported with a base-URL swap.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    AuthenticatedUser,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
    require_authenticated_user,
)
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from app.schemas.device_auth import (
    DeviceApproveRequest,
    DeviceApproveResponse,
    DeviceCodeResponse,
    DeviceDenyRequest,
    DeviceDenyResponse,
    DeviceGrantPreview,
    DeviceTokenError,
    DeviceTokenRequest,
    DeviceTokenSuccess,
)

router = APIRouter(tags=["auth-device"])


# RFC 8628 tunables. Set once here so MCP-client tests and server tests stay
# in lockstep — the cmos-mcp port reads these via the /device/code response.
DEVICE_CODE_TTL_SECONDS = 600  # 10 min — gives the user time to context-switch
DEVICE_CODE_POLL_INTERVAL_SECONDS = 5
DEVICE_CODE_BYTES = 32  # 256-bit opaque
USER_CODE_GROUP_LEN = 4  # ABCD-EFGH form
USER_CODE_GROUPS = 2

# user_code charset — capital letters only, drop confusable chars (0/O, 1/I, etc.)
# and digits entirely so the human can type it without ambiguity.
USER_CODE_CHARSET = "BCDFGHJKLMNPQRSTVWXZ"


def _generate_user_code() -> str:
    """Mint a short, human-readable, unambiguous code (e.g. ``WDJB-MJHT``)."""
    groups = [
        "".join(secrets.choice(USER_CODE_CHARSET) for _ in range(USER_CODE_GROUP_LEN))
        for _ in range(USER_CODE_GROUPS)
    ]
    return "-".join(groups)


def _normalize_user_code(raw: str) -> str:
    """Uppercase, strip, and drop all non-charset chars before lookup."""
    cleaned = "".join(ch for ch in raw.upper() if ch in USER_CODE_CHARSET)
    if len(cleaned) != USER_CODE_GROUP_LEN * USER_CODE_GROUPS:
        return ""
    return f"{cleaned[:USER_CODE_GROUP_LEN]}-{cleaned[USER_CODE_GROUP_LEN:]}"


def _expire_if_overdue(grant: DeviceAuthorizationGrant) -> bool:
    """Lazily flip the row to ``expired`` when read past its deadline.

    Returns True if the grant is now in a terminal expired state. Callers
    that mutate must commit themselves; this helper only sets the field.
    """
    if grant.status == "pending" and grant.expires_at <= datetime.utcnow():
        grant.status = "expired"
        return True
    return grant.status == "expired"


# ---------------------------------------------------------------------------
# Public (unauthenticated) — MCP client side
# ---------------------------------------------------------------------------


@router.post("/code", response_model=DeviceCodeResponse)
def request_device_code(
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    db: Session = Depends(get_db),
) -> DeviceCodeResponse:
    """Mint a new device-code grant.

    No authentication — the MCP client calls this before it has a key. The
    grant sits in ``pending`` status until the human approves or denies via
    the web UI, or until ``DEVICE_CODE_TTL_SECONDS`` elapses.
    """
    # Generate device_code + user_code with a uniqueness check. Collisions
    # are astronomically unlikely (256-bit) but the user_code space is small
    # (~6.5M combos) so a busy installation could theoretically clash.
    for _ in range(8):
        device_code = secrets.token_urlsafe(DEVICE_CODE_BYTES)[:64]
        user_code = _generate_user_code()
        existing_user = (
            db.query(DeviceAuthorizationGrant)
            .filter(DeviceAuthorizationGrant.user_code == user_code)
            .filter(DeviceAuthorizationGrant.status == "pending")
            .first()
        )
        if existing_user is None:
            break
    else:  # pragma: no cover — only fires under sustained collision
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not allocate a unique user_code; retry shortly.",
        )

    label = (user_agent or "tracelab-mcp/unknown").strip()[:255]

    now = datetime.utcnow()
    grant = DeviceAuthorizationGrant(
        device_code=device_code,
        user_code=user_code,
        client_label=label,
        status="pending",
        interval_seconds=DEVICE_CODE_POLL_INTERVAL_SECONDS,
        created_at=now,
        expires_at=now + timedelta(seconds=DEVICE_CODE_TTL_SECONDS),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    verification_uri = f"{settings.frontend_url.rstrip('/')}/device"
    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        expires_in=DEVICE_CODE_TTL_SECONDS,
        interval=DEVICE_CODE_POLL_INTERVAL_SECONDS,
    )


def _device_token_400(
    error: str, description: str | None = None
) -> HTTPException:
    """Build a 400 response in the RFC 8628 envelope.

    All polling errors share one HTTP status so the MCP client can branch
    on the ``error`` field alone — matches the cmos-mcp client's existing
    test fixtures verbatim.
    """
    payload = DeviceTokenError(
        error=error,  # type: ignore[arg-type]
        error_description=description,
    ).model_dump(exclude_none=True)
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=payload)


@router.post("/token", response_model=DeviceTokenSuccess)
def poll_device_token(
    payload: DeviceTokenRequest,
    db: Session = Depends(get_db),
) -> DeviceTokenSuccess:
    """Polled by the MCP client. Returns the minted key on approval.

    Unauthenticated — the ``device_code`` itself is the bearer secret.
    """
    grant = (
        db.query(DeviceAuthorizationGrant)
        .filter(DeviceAuthorizationGrant.device_code == payload.device_code)
        .first()
    )
    if grant is None:
        raise _device_token_400("expired_token", "device_code not recognized")

    expired_now = _expire_if_overdue(grant)

    # Enforce the polling interval. If the client comes back faster than
    # ``interval_seconds`` since the last poll, return slow_down so it
    # extends its sleep — matches RFC 8628 + cmos-mcp's test expectations.
    now = datetime.utcnow()
    if grant.last_polled_at is not None:
        gap = (now - grant.last_polled_at).total_seconds()
        if gap < grant.interval_seconds - 0.5:  # half-second tolerance
            raise _device_token_400(
                "slow_down",
                f"Wait at least {grant.interval_seconds}s between polls.",
            )
    grant.last_polled_at = now
    db.commit()

    if expired_now:
        raise _device_token_400("expired_token")

    if grant.status == "denied":
        raise _device_token_400("access_denied", "User denied the device code.")

    if grant.status == "pending":
        raise _device_token_400("authorization_pending")

    # Approved — the api_key was minted at approve time; resurface it.
    if grant.api_key_id is None:
        # Defensive: shouldn't happen because approve() persists both atomically
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Approved grant has no api_key linked",
        )
    api_key = db.query(APIKey).filter(APIKey.id == grant.api_key_id).first()
    if api_key is None:
        raise _device_token_400(
            "access_denied", "API key associated with this grant has been revoked."
        )

    # The plaintext key was returned at approve-time and is no longer
    # retrievable — we look it up by the cached value persisted on the grant.
    # Approval stores the plaintext on the grant for one-time delivery here.
    plaintext = _consume_pending_plaintext(grant)
    if plaintext is None:
        raise _device_token_400(
            "access_denied",
            "Token already retrieved by another poller. Re-run device login.",
        )

    db.commit()
    return DeviceTokenSuccess(
        access_token=plaintext,
        key=plaintext,
        key_id=api_key.id,
        label=api_key.name,
    )


# ---------------------------------------------------------------------------
# One-time plaintext delivery
# ---------------------------------------------------------------------------
#
# Approve mints the api_keys row (which only stores the bcrypt hash) and
# stashes the plaintext on a process-local map keyed by grant.id. The first
# /device/token poll after approval pops it, returns it, and the slot goes
# empty. This keeps the plaintext OFF disk while still allowing async
# delivery between the user clicking Approve in the browser and the MCP
# client's next poll.
#
# Single-process; if/when TL scales horizontally we promote this to redis
# with TTL == DEVICE_CODE_TTL_SECONDS. For Railway-single-instance today
# this is enough.

_PENDING_PLAINTEXT: dict[UUID, str] = {}


def _stash_pending_plaintext(grant_id: UUID, plaintext: str) -> None:
    _PENDING_PLAINTEXT[grant_id] = plaintext


def _consume_pending_plaintext(grant: DeviceAuthorizationGrant) -> str | None:
    return _PENDING_PLAINTEXT.pop(grant.id, None)


# ---------------------------------------------------------------------------
# Authenticated — web user side
# ---------------------------------------------------------------------------


def _resolve_pending_grant_or_404(
    db: Session, raw_user_code: str
) -> DeviceAuthorizationGrant:
    normalized = _normalize_user_code(raw_user_code)
    if not normalized:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="user_code not found or malformed",
        )
    grant = (
        db.query(DeviceAuthorizationGrant)
        .filter(DeviceAuthorizationGrant.user_code == normalized)
        .first()
    )
    if grant is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="user_code not found"
        )
    _expire_if_overdue(grant)
    return grant


@router.get("/grants/{user_code}", response_model=DeviceGrantPreview)
def preview_device_grant(
    user_code: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> DeviceGrantPreview:
    """Show the authenticated user what they're about to approve.

    The web /device page calls this before rendering the Approve/Deny
    buttons so the human sees the User-Agent that requested the code.
    """
    grant = _resolve_pending_grant_or_404(db, user_code)
    db.commit()  # persist the lazy expiry flip if any
    return DeviceGrantPreview(
        user_code=grant.user_code,
        client_label=grant.client_label,
        status=grant.status,  # type: ignore[arg-type]
        expires_at=grant.expires_at.isoformat(),
    )


@router.post("/approve", response_model=DeviceApproveResponse)
def approve_device_grant(
    payload: DeviceApproveRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> DeviceApproveResponse:
    """Approve a pending device grant on behalf of the authenticated user.

    Mints a ``tl_*`` API key under the user's account, links it to the grant,
    and stashes the plaintext for one-time pickup by the next /device/token
    poll. The MCP client persists the key locally and uses it for subsequent
    requests.
    """
    grant = _resolve_pending_grant_or_404(db, payload.user_code)

    if grant.status == "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This code has already been approved.",
        )
    if grant.status == "denied":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This code was denied. Re-run device login on the MCP client.",
        )
    if grant.status == "expired":
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="This code has expired. Re-run device login on the MCP client.",
        )

    # Enforce the same per-user 10-key cap the web /api-keys endpoint does
    # so device-flow can't be used to bypass the rate limit.
    existing = db.query(APIKey).filter(APIKey.user_id == user.user_id).count()
    if existing >= 10:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum of 10 API keys allowed per user. Delete one first.",
        )

    # Mint the key.
    plaintext = generate_api_key()
    label = (payload.label or grant.client_label).strip()[:255] or "tracelab-mcp"
    api_key = APIKey(
        user_id=user.user_id,
        name=label,
        key_hash=hash_api_key(plaintext),
        key_prefix=get_key_prefix(plaintext),
    )
    db.add(api_key)
    db.flush()  # assign api_key.id

    grant.status = "approved"
    grant.user_id = user.user_id
    grant.api_key_id = api_key.id
    grant.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(grant)

    _stash_pending_plaintext(grant.id, plaintext)

    return DeviceApproveResponse(
        user_code=grant.user_code,
        label=label,
        key_id=api_key.id,
        client_label=grant.client_label,
    )


@router.post("/deny", response_model=DeviceDenyResponse)
def deny_device_grant(
    payload: DeviceDenyRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> DeviceDenyResponse:
    """Mark a pending grant denied so the polling MCP client gets immediate feedback."""
    grant = _resolve_pending_grant_or_404(db, payload.user_code)

    if grant.status in ("approved", "denied", "expired"):
        # Idempotent — already terminal
        return DeviceDenyResponse(user_code=grant.user_code)

    grant.status = "denied"
    db.commit()
    return DeviceDenyResponse(user_code=grant.user_code)
