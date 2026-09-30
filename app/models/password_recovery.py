"""One replaceable, hashed recovery credential per human account."""

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
