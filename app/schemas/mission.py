"""Pydantic schemas for mission entities.

Aligned with the Mission model from B16.1 with explicit DeepSearch-compatible fields.
Implements comprehensive validation per B16.3 spec.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Valid mission statuses
MissionStatus = Literal["draft", "queued", "in_progress", "completed", "blocked", "cancelled"]

# Mission ID pattern: starts with alphanumeric, can contain dots, dashes, underscores
MISSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class MissionBase(BaseModel):
    """Shared attributes for mission operations."""

    mission_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Human-readable mission identifier (e.g., B16.1)",
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Mission title",
    )
    objective: str = Field(
        ...,
        min_length=10,
        description="What this mission aims to achieve (minimum 10 characters)",
    )
    success_criteria: List[str] = Field(
        ...,
        min_length=1,
        description="Array of measurable success conditions",
    )

    @field_validator("mission_id")
    @classmethod
    def validate_mission_id_format(cls, v: str) -> str:
        """Validate mission_id matches required pattern."""
        if not MISSION_ID_PATTERN.match(v):
            raise ValueError(
                "mission_id must start with alphanumeric and contain only "
                "letters, numbers, dots, dashes, or underscores"
            )
        return v

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, v: List[str]) -> List[str]:
        """Validate success_criteria is non-empty and each item is a non-empty string."""
        if not v:
            raise ValueError("success_criteria must contain at least one item")
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(f"success_criteria[{i}] must be a string")
            if not item.strip():
                raise ValueError(f"success_criteria[{i}] cannot be empty or whitespace")
        return v


class MissionCreate(MissionBase):
    """Payload for creating a mission."""

    project_id: Optional[UUID] = Field(
        None,
        description="Project to associate this mission with",
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context object for the mission",
    )
    deliverables: Optional[List[str]] = Field(
        default_factory=list,
        description="Array of expected deliverables",
    )
    research_phases: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Research phase configuration",
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Array of tags for categorization",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arbitrary metadata object",
    )
    status: Optional[MissionStatus] = Field(
        "draft",
        description="Initial mission status",
    )
    created_by: Optional[str] = Field(
        None,
        max_length=100,
        description="Agent or user who created this mission",
    )


class MissionUpdate(BaseModel):
    """Payload for updating a mission.

    All fields are optional - only provided fields will be updated.
    """

    title: Optional[str] = Field(
        None,
        min_length=3,
        max_length=255,
        description="Mission title",
    )
    objective: Optional[str] = Field(
        None,
        min_length=10,
        description="What this mission aims to achieve (minimum 10 characters)",
    )
    success_criteria: Optional[List[str]] = Field(
        None,
        min_length=1,
        description="Array of measurable success conditions",
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context object for the mission",
    )
    deliverables: Optional[List[str]] = Field(
        None,
        description="Array of expected deliverables",
    )
    research_phases: Optional[Dict[str, Any]] = Field(
        None,
        description="Research phase configuration",
    )
    tags: Optional[List[str]] = Field(
        None,
        description="Array of tags for categorization",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Arbitrary metadata object",
    )
    status: Optional[MissionStatus] = Field(
        None,
        description="Mission status",
    )
    deepsearch_job_id: Optional[str] = Field(
        None,
        max_length=100,
        description="DeepSearch job ID for tracking async execution",
    )
    result_document_ids: Optional[List[UUID]] = Field(
        None,
        description="Array of document UUIDs produced by this mission",
    )
    result_report_id: Optional[UUID] = Field(
        None,
        description="Primary report generated from mission results",
    )
    result_markdown: Optional[str] = Field(
        None,
        description="Raw markdown output from mission execution",
    )
    result_protocol: Optional[Dict[str, Any]] = Field(
        None,
        description="Mission Protocol compliant result object",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error details if mission failed",
    )
    execution_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution metrics and debugging info",
    )

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate success_criteria when provided."""
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("success_criteria must contain at least one item if provided")
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(f"success_criteria[{i}] must be a string")
            if not item.strip():
                raise ValueError(f"success_criteria[{i}] cannot be empty or whitespace")
        return v


class MissionResponse(MissionBase):
    """Full mission representation returned from API."""

    id: UUID
    project_id: Optional[UUID] = None
    project_name: Optional[str] = Field(None, description="Name of the associated project")
    context: Dict[str, Any] = Field(default_factory=dict)
    deliverables: List[str] = Field(default_factory=list)
    research_phases: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: MissionStatus
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deepsearch_job_id: Optional[str] = None
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    result_document_ids: List[UUID] = Field(default_factory=list)
    result_report_id: Optional[UUID] = None
    result_markdown: Optional[str] = None
    result_protocol: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("metadata", mode="before")
    @classmethod
    def map_mission_metadata(cls, v: Any, info) -> Dict[str, Any]:
        """Map mission_metadata column to metadata field."""
        # Handle case where we get mission_metadata from ORM
        if v is None:
            # Try to get from the source object
            data = info.data if hasattr(info, "data") else {}
            return data.get("mission_metadata", {}) or {}
        return v or {}

    @field_validator("result_document_ids", mode="before")
    @classmethod
    def parse_document_ids(cls, v: Any) -> List[UUID]:
        """Parse document IDs from JSON storage."""
        if v is None:
            return []
        if isinstance(v, list):
            return [UUID(str(x)) if not isinstance(x, UUID) else x for x in v]
        return []


# Alias for backwards compatibility
MissionRead = MissionResponse


class MissionSubmitResponse(BaseModel):
    """Response from submitting a mission for execution."""

    status: str = Field(..., description="Current mission status (queued)")
    mode: str = Field(..., description="Execution mode (worker or http)")
    mission_id: str = Field(..., description="Human-readable mission ID")
    uuid: UUID = Field(..., description="Mission UUID")
    message: str = Field(..., description="Status message")
    job_id: Optional[str] = Field(None, description="DeepSearch job ID (http mode only)")


class ReportPromotionResponse(BaseModel):
    """Response from promoting a mission report to a document."""

    document_id: UUID = Field(..., description="UUID of the created document")
    document_name: str = Field(..., description="Name of the created document")
    status: str = Field(..., description="Processing status (processing or completed)")
    message: str = Field(..., description="Status message")
    chunk_count: Optional[int] = Field(None, description="Number of chunks created")
