"""A user's inbox watermark; everything that occurred at or before it has been seen."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey

from app.core.database import Base
from app.models.types import GUID


class UserInboxState(Base):
    __tablename__ = "user_inbox_state"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    seen_through = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
