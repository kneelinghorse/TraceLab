"""Pydantic schemas for mission entities."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.mission_protocol import MissionProtocolDraft


class MissionBase(BaseModel):
    """Shared attributes for mission operations."""

    project_id: Optional[UUID] = None
    mission_data: MissionProtocolDraft
    quality_gates: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    completion_percentage: Optional[int] = None


class MissionCreate(MissionBase):
    """Payload for creating a mission."""

    pass


class MissionUpdate(BaseModel):
    """Payload for updating a mission."""

    mission_data: Optional[MissionProtocolDraft] = None
    quality_gates: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    completion_percentage: Optional[int] = None


class MissionRead(MissionBase):
    """Representation of a persisted mission."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
