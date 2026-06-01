"""User model for multi-user authentication."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String

from app.core.database import Base
from app.models.types import GUID


class User(Base):
    """User entity for authentication and identity."""

    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    # Least-privilege default (Sprint 47 T47.1). Was "admin", which silently minted
    # an admin for every User() without an explicit role — every invite registration
    # became an admin. "member" == ROLE_MEMBER (kept as a literal to avoid importing
    # app.core.security into the model layer); owner/admin are assigned explicitly.
    role = Column(String(50), nullable=False, default="member")
    # Admin soft-disable (Sprint 43 T43.5). Set via the admin API; enforced at every
    # auth path as of Sprint C (T46.3) — a disabled user cannot log in or be resolved
    # as a request principal. Default active.
    is_active = Column(Boolean, nullable=False, default=True)
    invite_code_used = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_users_email", "email", unique=True),)
