"""Schemas for DeepSearch ingestion endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, conint, confloat

from app.models.mission_protocol import MissionProtocolComplete


class DeepSearchIngestRequest(BaseModel):
    """Request payload for DeepSearch JSON ingestion."""

    mission: MissionProtocolComplete = Field(..., description="MissionProtocolComplete JSON payload")
    project_id: Optional[UUID] = Field(default=None, description="Existing TraceLab project UUID")
    auto_create_project: bool = Field(
        default=False,
        description="Create a new project when project_id is omitted",
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Name for an auto-created project",
    )
    similarity_threshold: Optional[confloat(ge=0.0, le=1.0)] = Field(
        default=None,
        description="Override for evidence auto-linking similarity threshold",
    )


class AutoLinkingMatch(BaseModel):
    """Individual evidence auto-linking outcome."""

    evidence_id: str
    chunk_id: Optional[str] = None
    similarity: float = 0.0
    summary_preview: Optional[str] = None


class AutoLinkingSummary(BaseModel):
    """Aggregated evidence auto-linking telemetry."""

    attempted: conint(ge=0) = 0
    linked: conint(ge=0) = 0
    skipped: conint(ge=0) = 0
    threshold: confloat(ge=0.0, le=1.0) = 0.7
    success_rate: confloat(ge=0.0, le=1.0) = 0.0
    matches: List[AutoLinkingMatch] = Field(default_factory=list)


class DeepSearchIngestResponse(BaseModel):
    """Response returned after DeepSearch mission ingestion."""

    mission_uuid: UUID
    mission_id: str
    project_id: Optional[UUID] = None
    status: str
    quality_gates_passed: bool
    quality_gates: Dict[str, Any]
    auto_linking: AutoLinkingSummary
