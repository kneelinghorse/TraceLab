"""Sync state tracking for PEDR delta synchronization."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base
from app.models.types import GUID


class SyncState(Base):
    """Tracks sync state per entity type for delta detection."""

    __tablename__ = "sync_states"
    __table_args__ = (
        UniqueConstraint("entity_type", name="uq_sync_state_entity_type"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(50), nullable=False)  # mission | document | insight
    last_sync_at = Column(DateTime, nullable=True)  # Last successful sync timestamp
    sync_count = Column(Integer, default=0)  # Total entities synced
    last_entity_id = Column(
        String(255), nullable=True
    )  # Last synced entity ID (for cursor)
    sync_metadata = Column(JSON, nullable=True)  # Additional sync metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SyncState(entity_type={self.entity_type}, last_sync_at={self.last_sync_at})>"
