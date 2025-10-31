"""Pydantic schemas for quality check entities."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QualityCheckBase(BaseModel):
    """Shared attributes for quality check operations."""

    entity_type: str
    entity_id: UUID
    check_type: str
    status: str
    details: Optional[dict] = None
    recommendations: Optional[List[str]] = None
    performed_by: Optional[str] = None


class QualityCheckCreate(QualityCheckBase):
    """Payload for creating a quality check record."""

    pass


class QualityCheckUpdate(BaseModel):
    """Payload for updating a quality check record."""

    check_type: Optional[str] = None
    status: Optional[str] = None
    details: Optional[dict] = None
    recommendations: Optional[List[str]] = None
    performed_by: Optional[str] = None
    performed_at: Optional[datetime] = None


class QualityCheckRead(QualityCheckBase):
    """Representation of a persisted quality check."""

    id: UUID
    performed_at: datetime

    model_config = ConfigDict(from_attributes=True)
