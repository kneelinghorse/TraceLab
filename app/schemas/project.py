"""Pydantic schemas for project entities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    """Shared attributes for project operations."""

    name: str
    description: str | None = None
    mission_protocol_id: UUID | None = None
    research_type: str | None = None
    methodology: str | None = None
    status: str | None = None
    quality_score: int | None = None
    last_quality_check: datetime | None = None


class ProjectCreate(ProjectBase):
    """Payload for creating a project."""

    pass


class ProjectUpdate(BaseModel):
    """Payload for updating a project."""

    name: str | None = None
    description: str | None = None
    mission_protocol_id: UUID | None = None
    research_type: str | None = None
    methodology: str | None = None
    status: str | None = None
    quality_score: int | None = None
    last_quality_check: datetime | None = None


class ProjectRead(ProjectBase):
    """Representation of a persisted project."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    # Legacy self-asserted field, retained in the response for backward compat.
    # No longer client-settable (T43.4); null for projects created after T43.4.
    # The authoritative owner is owner_id (surfaced read-side in a later sprint).
    user_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectStats(BaseModel):
    """Statistics for a project."""

    project_id: UUID
    name: str
    document_count: int
    chunk_count: int
    report_count: int
    total_tokens: int
    last_updated: datetime | None = None
