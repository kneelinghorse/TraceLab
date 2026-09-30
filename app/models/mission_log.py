"""MissionLog model for storing DeepSearch runner log records."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

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

    attempt_count = Column(Integer, nullable=True)
    event_id = Column(GUID(), nullable=True)
    sequence = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("mission_id", "attempt_count", "event_id", name="uq_mission_log_event"),
        UniqueConstraint("mission_id", "attempt_count", "sequence", name="uq_mission_log_sequence"),
        CheckConstraint("(attempt_count IS NULL AND event_id IS NULL AND sequence IS NULL) OR (attempt_count IS NOT NULL AND attempt_count > 0 AND event_id IS NOT NULL AND sequence IS NOT NULL AND sequence > 0)", name="ck_mission_log_identity"),
        Index("ix_mission_logs_mission_logged", "mission_id", "logged_at"),
    )
