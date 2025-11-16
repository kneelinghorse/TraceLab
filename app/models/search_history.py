"""Search history persistence model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text

from app.core.database import Base
from app.models.types import GUID


class SearchHistory(Base):
    """Record past search queries plus metadata for replay."""

    __tablename__ = "search_history"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    query_text = Column(Text, nullable=False)
    search_mode = Column(String(32), nullable=False, default="semantic")
    filters = Column(JSON, nullable=False, default=dict)
    result_count = Column(Integer, nullable=False, default=0)
    top_k = Column(Integer, nullable=False, default=5)
    duration_ms = Column(Integer, nullable=True)
    cache_hit = Column(Boolean, nullable=False, default=False)
    user_label = Column(String(255), nullable=True)
    metadata_payload = Column(JSON, nullable=False, default=dict)
    top_chunks = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_search_history_created_at", "created_at"),
        Index("ix_search_history_query_mode", "search_mode"),
    )
