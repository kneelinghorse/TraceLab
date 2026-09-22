"""Per-user usage records (METER-0, decision #522).

One durable row per DeepSearch run and per Librarian model call, attributed to
the user who caused it. Data only: no limits, no quotas, no billing. The row
exists so that "what did this user consume last month" is a query, and so the
history exists when Derek decides to meter.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.types import GUID, CrossDBJSON

USAGE_KIND_DEEPSEARCH_RUN = "deepsearch_run"
USAGE_KIND_LIBRARIAN_TURN = "librarian_turn"
USAGE_KIND_LIBRARIAN_DRAFT = "librarian_draft"

ATTRIBUTION_SUBMITTER = "submitter"
ATTRIBUTION_PROJECT_OWNER = "project_owner"
ATTRIBUTION_CALLER = "caller"


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    mission_id = Column(GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)

    kind = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    attribution = Column(String(32), nullable=False, default=ATTRIBUTION_SUBMITTER)

    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    requests = Column(Integer, nullable=True)
    steps = Column(Integer, nullable=True)
    tool_calls = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    usage_complete = Column(Boolean, nullable=True)
    # Never asserted for DeepSeek runs: no price is sent and none is hard-coded here.
    cost_usd = Column(Numeric(12, 6), nullable=True)
    details = Column(CrossDBJSON, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("mission_id", "kind", name="uq_usage_records_mission_kind"),
        Index("ix_usage_records_user_recorded", "user_id", "recorded_at"),
        Index("ix_usage_records_recorded_at", "recorded_at"),
    )
