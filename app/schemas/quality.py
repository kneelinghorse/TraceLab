"""Pydantic schemas for quality check entities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QualityCheckBase(BaseModel):
    """Shared attributes for quality check operations."""

    entity_type: str
    entity_id: UUID
    check_type: str
    status: str
    details: dict | None = None
    recommendations: list[str] | None = None
    performed_by: str | None = None


class QualityCheckCreate(QualityCheckBase):
    """Payload for creating a quality check record."""

    pass


class QualityCheckUpdate(BaseModel):
    """Payload for updating a quality check record."""

    check_type: str | None = None
    status: str | None = None
    details: dict | None = None
    recommendations: list[str] | None = None
    performed_by: str | None = None
    performed_at: datetime | None = None


class QualityCheckRead(QualityCheckBase):
    """Representation of a persisted quality check."""

    id: UUID
    performed_at: datetime

    model_config = ConfigDict(from_attributes=True)
