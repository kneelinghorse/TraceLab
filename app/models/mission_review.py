"""A user's explicit acknowledgement of a particular mission result revision."""

from sqlalchemy import Column, DateTime, ForeignKey

from app.core.database import Base
from app.models.types import GUID


class MissionReview(Base):
    __tablename__ = "user_mission_reviews"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    mission_id = Column(GUID(), ForeignKey("missions.id", ondelete="CASCADE"), primary_key=True)
    mission_updated_at = Column(DateTime, nullable=False)
    reviewed_at = Column(DateTime, nullable=False)
