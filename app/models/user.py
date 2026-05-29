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
    role = Column(String(50), nullable=False, default="admin")
    # Admin soft-disable (Sprint 43 T43.5). Set via the admin API; login-enforcement
    # of disabled users is deferred to Sprint C. Default active.
    is_active = Column(Boolean, nullable=False, default=True)
    invite_code_used = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_users_email", "email", unique=True),)
