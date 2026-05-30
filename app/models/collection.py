"""Collection and CollectionItem models for grouping chunks."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


class Collection(Base):
    """A named collection of document chunks for export or analysis."""

    __tablename__ = "collections"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Ownership + tenancy (Sprint 43 RBAC foundation; additive, nullable, unread until Sprint C)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    workspace_id = Column(GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    items = relationship(
        "CollectionItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_collections_created_at", "created_at"),
        Index("ix_collections_workspace_owner_created_at", "workspace_id", "owner_id", "created_at"),
        {"extend_existing": True},
    )


class CollectionItem(Base):
    """Join table linking collections to document chunks."""

    __tablename__ = "collection_items"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    collection_id = Column(
        GUID(), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id = Column(
        GUID(), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    collection = relationship("Collection", back_populates="items")
    chunk = relationship("DocumentChunk", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "collection_id", "chunk_id", name="uq_collection_item_collection_chunk"
        ),
        Index("ix_collection_items_collection_id", "collection_id"),
        Index("ix_collection_items_chunk_id", "chunk_id"),
        {"extend_existing": True},
    )
