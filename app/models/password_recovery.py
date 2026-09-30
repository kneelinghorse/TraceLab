"""One replaceable, hashed recovery credential per human account."""

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base
from app.models.types import GUID


class PasswordRecovery(Base):
    __tablename__ = "password_recoveries"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token_hash = Column(String(64), nullable=True, unique=True)
    credential_version = Column(Integer, nullable=False)
    requested_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    delivery_status = Column(String(24), nullable=False)


class PasswordRecoveryAudit(Base):
    """Historical identity snapshots survive account deletion; never store secrets."""

    __tablename__ = "password_recovery_audits"

    id = Column(GUID(), primary_key=True, default=uuid4)
    # Deliberately no user FKs: these identify the actors at request time, and
    # purging an account must neither erase the audit nor be blocked by it.
    actor_user_id = Column(GUID(), nullable=False)
    target_user_id = Column(GUID(), nullable=False)
    requested_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    outcome = Column(String(24), nullable=False)
