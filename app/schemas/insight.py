"""Pydantic schemas for insight entities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InsightBase(BaseModel):
    """Shared attributes for insight operations."""

    project_id: UUID
    title: str
    content: str
    insight_type: str | None = None
    created_by: str | None = "human"
    validated: bool | None = False
    validation_date: datetime | None = None


class InsightCreate(InsightBase):
    """Payload for creating an insight."""

    pass


class InsightUpdate(BaseModel):
    """Payload for updating an insight."""

    title: str | None = None
    content: str | None = None
    insight_type: str | None = None
    validated: bool | None = None
    validation_date: datetime | None = None


class InsightRead(InsightBase):
    """Representation of a persisted insight."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    sources: list[InsightSourceRead] | None = None

    model_config = ConfigDict(from_attributes=True)


class InsightSourceBase(BaseModel):
    """Shared attributes for insight source junction operations."""

    insight_id: UUID
    chunk_id: UUID
    relevance_score: Decimal | None = None


class InsightSourceCreate(InsightSourceBase):
    """Payload for linking a chunk to an insight."""

    pass


class InsightSourceRead(InsightSourceBase):
    """Representation of a persisted insight source link."""

    model_config = ConfigDict(from_attributes=True)


InsightRead.model_rebuild()
