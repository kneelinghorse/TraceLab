"""SynthesisCache model for caching synthesis results by content hash."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.models.types import GUID


class SynthesisCache(Base):
    """Cache for synthesis results to avoid redundant LLM calls."""

    __tablename__ = "synthesis_cache"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    input_hash = Column(String(64), nullable=False, unique=True)
    content = Column(Text, nullable=False)
    citations = Column(JSONB, nullable=True)
    model_used = Column(String(50), nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    hit_count = Column(Integer, nullable=False, default=0)
    last_hit_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_synthesis_cache_input_hash", "input_hash"),
        {"extend_existing": True},
    )
