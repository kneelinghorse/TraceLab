"""Pydantic schemas for project entities."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    """Shared attributes for project operations."""

    name: str
    description: Optional[str] = None
    user_id: Optional[UUID] = None
    mission_protocol_id: Optional[UUID] = None
    research_type: Optional[str] = None
    methodology: Optional[str] = None
    status: Optional[str] = None
    quality_score: Optional[int] = None
    last_quality_check: Optional[datetime] = None


class ProjectCreate(ProjectBase):
    """Payload for creating a project."""

    pass


class ProjectUpdate(BaseModel):
    """Payload for updating a project."""

    name: Optional[str] = None
    description: Optional[str] = None
    user_id: Optional[UUID] = None
    mission_protocol_id: Optional[UUID] = None
    research_type: Optional[str] = None
    methodology: Optional[str] = None
    status: Optional[str] = None
    quality_score: Optional[int] = None
    last_quality_check: Optional[datetime] = None


class ProjectRead(ProjectBase):
    """Representation of a persisted project."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectStats(BaseModel):
    """Statistics for a project."""

    project_id: UUID
    name: str
    document_count: int
    chunk_count: int
    report_count: int
    total_tokens: int
    last_updated: Optional[datetime] = None
