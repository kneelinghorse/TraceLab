"""Personal mission filters; saved preferences never confer resource access."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from app.core.database import Base
from app.models.types import GUID


class UserSavedView(Base):
    __tablename__ = "user_saved_views"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    entity_type = Column(String(32), nullable=False, default="missions")
    filters = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("entity_type = 'missions'", name="ck_user_saved_views_missions"),
        UniqueConstraint("user_id", "name", name="uq_user_saved_views_user_name"),
        Index("ix_user_saved_views_user_updated", "user_id", "updated_at"),
    )
