"""Pydantic schemas for insight entities."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InsightBase(BaseModel):
    """Shared attributes for insight operations."""

    project_id: UUID
    title: str
    content: str
    insight_type: Optional[str] = None
    created_by: Optional[str] = "human"
    validated: Optional[bool] = False
    validation_date: Optional[datetime] = None


class InsightCreate(InsightBase):
    """Payload for creating an insight."""

    pass


class InsightUpdate(BaseModel):
    """Payload for updating an insight."""

    title: Optional[str] = None
    content: Optional[str] = None
    insight_type: Optional[str] = None
    validated: Optional[bool] = None
    validation_date: Optional[datetime] = None


class InsightRead(InsightBase):
    """Representation of a persisted insight."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    sources: Optional[List["InsightSourceRead"]] = None

    model_config = ConfigDict(from_attributes=True)


class InsightSourceBase(BaseModel):
    """Shared attributes for insight source junction operations."""

    insight_id: UUID
    chunk_id: UUID
    relevance_score: Optional[Decimal] = None


class InsightSourceCreate(InsightSourceBase):
    """Payload for linking a chunk to an insight."""

    pass


class InsightSourceRead(InsightSourceBase):
    """Representation of a persisted insight source link."""

    model_config = ConfigDict(from_attributes=True)


InsightRead.model_rebuild()
