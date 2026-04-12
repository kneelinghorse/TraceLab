"""MissionLog model for storing DeepSearch runner log records."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.core.database import Base
from app.models.types import GUID


class MissionLog(Base):
    """A single log record emitted by the DeepSearch runner for a mission."""

    __tablename__ = "mission_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    mission_id = Column(
        GUID(),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level = Column(String(20), nullable=False, default="INFO")
    message = Column(Text, nullable=False)
    source = Column(String(100), nullable=True)
    logged_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_mission_logs_mission_logged", "mission_id", "logged_at"),
    )
