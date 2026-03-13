"""Invite code model for user registration."""

import secrets
import string
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base
from app.models.types import GUID

# 8-char uppercase alphanumeric codes
_CODE_CHARS = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8


def generate_invite_code() -> str:
    """Generate an 8-character uppercase alphanumeric invite code."""
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(_CODE_LENGTH))


class InviteCode(Base):
    """Single-use invite code for user registration."""

    __tablename__ = "invite_codes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(8), unique=True, nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    used_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
