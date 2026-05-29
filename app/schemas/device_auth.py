"""Pydantic schemas for the RFC 8628 device-authorization endpoints (T42.4).

Wire shape mirrors the cmos-mcp contract verbatim so the MCP-client device-
code module can be ported with a single base-URL swap. See
``cmos/contracts/`` (companion doc) and ``app/api/v1/auth/device.py``.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Public (unauthenticated) endpoints — MCP client side
# ---------------------------------------------------------------------------


class DeviceCodeResponse(BaseModel):
    """Body returned from POST /api/v1/auth/device/code."""

    device_code: str = Field(
        ...,
        description=(
            "Opaque server-issued token the MCP client polls with. Never shown "
            "to the human user."
        ),
    )
    user_code: str = Field(
        ...,
        description=(
            "Short human-readable code (8 chars, ABCD-EFGH form) the user types "
            "into the web /device page."
        ),
    )
    verification_uri: str = Field(
        ...,
        description="URL the human visits in a browser to approve the request.",
    )
    expires_in: int = Field(
        ..., description="Seconds until device_code expires (default 600)."
    )
    interval: int = Field(
        ..., description="Seconds between polls. Server enforces with slow_down."
    )


class DeviceTokenRequest(BaseModel):
    """Polling body for POST /api/v1/auth/device/token."""

    device_code: str = Field(..., description="The device_code from /device/code.")


class DeviceTokenSuccess(BaseModel):
    """200 body when /device/token finds an approved grant.

    `key` is the freshly minted ``tl_*`` API key (only returned once).
    `key_id` and `label` mirror what GET /api-keys would later show.
    """

    access_token: str = Field(
        ...,
        description=(
            "Plaintext API key. The MCP client stores this and sends it as "
            "X-API-Key on subsequent requests."
        ),
    )
    token_type: Literal["api_key"] = Field(default="api_key")
    key: str = Field(
        ...,
        description=(
            "Duplicate of access_token under the cmos-mcp-compatible name so "
            "the ported MCP client works without renaming fields."
        ),
    )
    key_id: UUID = Field(..., description="UUID of the api_keys row.")
    label: str = Field(..., description="Display name for the key.")


class DeviceTokenError(BaseModel):
    """400 body when /device/token has no approved grant yet (RFC 8628)."""

    error: Literal[
        "authorization_pending",
        "slow_down",
        "expired_token",
        "access_denied",
    ]
    error_description: str | None = None


# ---------------------------------------------------------------------------
# Authenticated endpoints — web user side
# ---------------------------------------------------------------------------


class DeviceApproveRequest(BaseModel):
    """Body for POST /api/v1/auth/device/approve.

    The web user types the user_code and optionally overrides the auto-label.
    """

    user_code: str = Field(..., min_length=4, max_length=16)
    label: str | None = Field(
        None,
        max_length=255,
        description=(
            "Override for the API-key display name. Defaults to the parsed "
            "User-Agent the MCP client sent (e.g. 'tracelab-mcp/1.0.0 (darwin; laptop.local)')."
        ),
    )


class DeviceApproveResponse(BaseModel):
    """200 body when a user_code has been approved."""

    user_code: str
    label: str
    key_id: UUID
    client_label: str = Field(
        ...,
        description=(
            "The User-Agent the MCP client originally sent — surfaced so the "
            "approver can confirm what they're approving."
        ),
    )


class DeviceDenyRequest(BaseModel):
    """Body for POST /api/v1/auth/device/deny."""

    user_code: str = Field(..., min_length=4, max_length=16)


class DeviceDenyResponse(BaseModel):
    user_code: str
    status: Literal["denied"] = "denied"


class DeviceGrantPreview(BaseModel):
    """Body returned from GET /api/v1/auth/device/grants/{user_code}.

    Lets the web /device page show the user what they're about to approve
    (the User-Agent the MCP client identified itself with) before they click.
    """

    user_code: str
    client_label: str
    status: Literal["pending", "approved", "denied", "expired"]
    expires_at: str = Field(..., description="ISO-8601 timestamp.")
