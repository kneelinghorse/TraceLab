"""Device-authorization grant model (RFC 8628 device-code flow, T42.4).

A row tracks one device-code request from the MCP client through approval/
denial/expiry. On approval the row also records which API key was minted on
behalf of the approving user so we can revoke the grant by revoking the key.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.core.database import Base
from app.models.types import GUID

DeviceGrantStatus = Literal["pending", "approved", "denied", "expired"]


class DeviceAuthorizationGrant(Base):
    """One in-flight RFC 8628 device-authorization grant.

    `device_code` is the random 256-bit token the MCP client polls with —
    never shown to the human user. `user_code` is the short, human-readable
    code (8 chars, ABCD-EFGH form) the user types into the web /device page.
    """

    __tablename__ = "device_authorization_grants"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    device_code = Column(String(64), nullable=False, unique=True)
    user_code = Column(String(16), nullable=False, unique=True)

    client_label = Column(
        String(255),
        nullable=False,
        comment="Parsed User-Agent string the dashboard surfaces alongside the code so the user knows what they're approving.",
    )

    status = Column(
        String(16),
        default="pending",
        nullable=False,
        comment="pending | approved | denied | expired",
    )

    # Polling cadence (seconds). The MCP client receives this from /device/code
    # and uses it as the baseline. Server enforces by returning slow_down if
    # polls arrive faster.
    interval_seconds = Column(Integer, default=5, nullable=False)

    # Filled on approval — links the grant to the authorizing user and the
    # specific API key minted on their behalf.
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    api_key_id = Column(GUID(), ForeignKey("api_keys.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_polled_at = Column(
        DateTime,
        nullable=True,
        comment="Last time /device/token was hit with this device_code; used to enforce the polling interval.",
    )
    approved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_device_grants_user_code", "user_code"),
        Index("ix_device_grants_device_code", "device_code"),
        Index("ix_device_grants_status", "status"),
    )
