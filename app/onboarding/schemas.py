"""Pydantic schemas for onboarding API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.onboarding.jobs import JobStatus


class JobRead(BaseModel):
    """Representation of an ingestion job."""

    id: UUID
    project_id: UUID
    document_id: UUID
    status: JobStatus
    status_detail: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
