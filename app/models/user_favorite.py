"""Personal project shortcuts; visibility is checked again whenever they are read."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String

from app.core.database import Base
from app.models.types import GUID


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    entity_type = Column(String(32), primary_key=True)
    entity_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("entity_type = 'project'", name="ck_user_favorites_project"),)
