"""Pydantic schemas for mission entities.

Aligned with the Mission model from B16.1 with explicit DeepSearch-compatible fields.
Implements comprehensive validation per B16.3 spec.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Valid mission statuses
MissionStatus = Literal[
    "draft", "queued", "in_progress", "completed", "blocked", "cancelled"
]

# Valid research depth tiers
ResearchDepth = Literal["baseline", "deep", "alpha"]

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
    success_criteria: list[str] = Field(
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
    def validate_success_criteria(cls, v: list[str]) -> list[str]:
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

    project_id: UUID | None = Field(
        None,
        description="Project to associate this mission with",
    )
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional context object for the mission",
    )
    deliverables: list[str] | None = Field(
        default_factory=list,
        description="Array of expected deliverables",
    )
    research_phases: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Research phase configuration",
    )
    tags: list[str] | None = Field(
        default_factory=list,
        description="Array of tags for categorization",
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Arbitrary metadata object",
    )
    research_depth: ResearchDepth | None = Field(
        "baseline",
        description="Research depth tier. BASELINE (8-12 min, 50-60 sources): standard thorough research — use as default. DEEP (20-25 min, 30-40 vetted sources): stricter quality gates, min 5 loops. ALPHA (1+ hour, ~20 scrutinized sources): may reject if evidence insufficient.",
    )
    status: MissionStatus | None = Field(
        "draft",
        description="Initial mission status",
    )
    created_by: str | None = Field(
        None,
        max_length=100,
        description="Agent or user who created this mission",
    )


class MissionUpdate(BaseModel):
    """Payload for updating a mission.

    All fields are optional - only provided fields will be updated.
    """

    title: str | None = Field(
        None,
        min_length=3,
        max_length=255,
        description="Mission title",
    )
    objective: str | None = Field(
        None,
        min_length=10,
        description="What this mission aims to achieve (minimum 10 characters)",
    )
    success_criteria: list[str] | None = Field(
        None,
        min_length=1,
        description="Array of measurable success conditions",
    )
    context: dict[str, Any] | None = Field(
        None,
        description="Additional context object for the mission",
    )
    deliverables: list[str] | None = Field(
        None,
        description="Array of expected deliverables",
    )
    research_phases: dict[str, Any] | None = Field(
        None,
        description="Research phase configuration",
    )
    tags: list[str] | None = Field(
        None,
        description="Array of tags for categorization",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Arbitrary metadata object",
    )
    research_depth: ResearchDepth | None = Field(
        None,
        description="Research depth tier. BASELINE (8-12 min, 50-60 sources): standard thorough research. DEEP (20-25 min, 30-40 vetted sources): stricter quality gates. ALPHA (1+ hour, ~20 scrutinized sources): may reject if evidence insufficient.",
    )
    status: MissionStatus | None = Field(
        None,
        description="Mission status",
    )
    deepsearch_job_id: str | None = Field(
        None,
        max_length=100,
        description="DeepSearch job ID for tracking async execution",
    )
    result_document_ids: list[UUID] | None = Field(
        None,
        description="Array of document UUIDs produced by this mission",
    )
    result_report_id: UUID | None = Field(
        None,
        description="Primary report generated from mission results",
    )
    result_markdown: str | None = Field(
        None,
        description="Raw markdown output from mission execution",
    )
    result_protocol: dict[str, Any] | None = Field(
        None,
        description="Mission Protocol compliant result object",
    )
    error_message: str | None = Field(
        None,
        description="Error details if mission failed",
    )
    execution_metadata: dict[str, Any] | None = Field(
        None,
        description="Execution metrics and debugging info",
    )

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, v: list[str] | None) -> list[str] | None:
        """Validate success_criteria when provided."""
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError(
                "success_criteria must contain at least one item if provided"
            )
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(f"success_criteria[{i}] must be a string")
            if not item.strip():
                raise ValueError(f"success_criteria[{i}] cannot be empty or whitespace")
        return v


class MissionResponse(MissionBase):
    """Full mission representation returned from API."""

    id: UUID
    project_id: UUID | None = None
    project_name: str | None = Field(None, description="Name of the associated project")
    context: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list)
    research_phases: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    research_depth: ResearchDepth | None = Field(
        "baseline",
        description="Research depth tier. BASELINE (8-12 min, 50-60 sources): standard thorough research. DEEP (20-25 min, 30-40 vetted sources): stricter quality gates. ALPHA (1+ hour, ~20 scrutinized sources): may reject if evidence insufficient.",
    )
    status: MissionStatus
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    deepsearch_job_id: str | None = None
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    result_document_ids: list[UUID] = Field(default_factory=list)
    result_report_id: UUID | None = None
    result_markdown: str | None = None
    result_protocol: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("metadata", mode="before")
    @classmethod
    def map_mission_metadata(cls, v: Any, info) -> dict[str, Any]:
        """Map mission_metadata column to metadata field."""
        # Handle case where we get mission_metadata from ORM
        if v is None:
            # Try to get from the source object
            data = info.data if hasattr(info, "data") else {}
            return data.get("mission_metadata", {}) or {}
        return v or {}

    @field_validator("result_document_ids", mode="before")
    @classmethod
    def parse_document_ids(cls, v: Any) -> list[UUID]:
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
    job_id: str | None = Field(None, description="DeepSearch job ID (http mode only)")


class MissionActionableError(BaseModel):
    """Structured error details for agent-facing mission workflows."""

    message: str = Field(..., description="Human-readable error message")
    mission_id: str | None = Field(
        None,
        description="Human-readable mission identifier when available",
    )
    uuid: UUID | None = Field(
        None,
        description="Mission UUID when available",
    )
    suggestion: str | None = Field(
        None,
        description="Concrete follow-up action to resolve the issue",
    )
    current_status: MissionStatus | None = Field(
        None,
        description="Current mission status, when relevant",
    )


class MissionErrorResponse(BaseModel):
    """HTTP error envelope used by mission endpoints."""

    detail: MissionActionableError


class ReportPromotionResponse(BaseModel):
    """Response from promoting a mission report to a document."""

    document_id: UUID = Field(..., description="UUID of the created document")
    document_name: str = Field(..., description="Name of the created document")
    status: str = Field(..., description="Processing status (processing or completed)")
    message: str = Field(..., description="Status message")
    chunk_count: int | None = Field(None, description="Number of chunks created")
