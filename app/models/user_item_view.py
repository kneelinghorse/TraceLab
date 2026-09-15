"""A user's record of having opened an activity item at a given revision."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String

from app.core.database import Base
from app.models.types import GUID

ITEM_TYPES = ("mission", "report", "evidence")


class UserItemView(Base):
    __tablename__ = "user_item_views"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    item_type = Column(String(32), primary_key=True)
    item_id = Column(GUID(), primary_key=True)
    occurred_at = Column(DateTime, nullable=False)
    viewed_at = Column(DateTime, nullable=False)
    __table_args__ = (
        CheckConstraint("item_type IN ('mission', 'report', 'evidence')", name="ck_user_item_views_type"),
    )
