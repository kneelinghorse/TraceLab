"""Saved search ORM model for reusable queries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.types import GUID


class SavedSearch(Base):
    """Represents a persisted search configuration owned by a specific user."""

    __tablename__ = "saved_searches"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    query_text = Column(Text, nullable=False)
    search_mode = Column(String(32), nullable=False, default="semantic")
    filters = Column(JSON, nullable=False, default=dict)
    top_k = Column(Integer, nullable=False, default=5)
    owner = Column(String(128), nullable=False)
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_saved_searches_owner_created_at", "owner", "created_at"),
        UniqueConstraint("owner", "name", name="uq_saved_search_owner_name"),
    )
