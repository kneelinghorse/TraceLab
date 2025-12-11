"""Schemas for DeepSearch integration (client and ingestion endpoints)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, conint, confloat

from app.models.mission_protocol import MissionProtocolComplete


# =============================================================================
# DeepSearch Client Schemas (TraceLab → DeepSearch)
# =============================================================================


class DeepSearchJobStatus(str, Enum):
    """Status values for DeepSearch job execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeepSearchExecuteRequest(BaseModel):
    """Request payload for POST /missions/execute on DeepSearch."""

    mission_id: str = Field(..., description="Unique mission identifier")
    title: str = Field(..., description="Mission title")
    objective: str = Field(..., description="Primary mission objective")
    success_criteria: List[str] = Field(
        ..., min_length=1, description="Measurable success criteria"
    )
    callback_url: str = Field(..., description="Webhook URL for status updates")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context for mission execution"
    )
    deliverables: Optional[List[str]] = Field(
        default=None, description="Expected deliverables"
    )
    research_phases: Optional[Dict[str, Any]] = Field(
        default=None, description="Research phase configuration"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional metadata"
    )
    research_depth: Optional[str] = Field(
        default="baseline",
        description="Research depth tier: baseline (default), deep, or alpha",
    )


class DeepSearchExecuteResponse(BaseModel):
    """Response from POST /missions/execute on DeepSearch."""

    job_id: str = Field(..., description="Unique job identifier for tracking")
    mission_id: str = Field(..., description="Mission ID that was submitted")
    status: DeepSearchJobStatus = Field(
        default=DeepSearchJobStatus.PENDING, description="Initial job status"
    )
    estimated_duration_seconds: Optional[int] = Field(
        default=None, description="Estimated execution time"
    )
    created_at: datetime = Field(..., description="Job creation timestamp")


class DeepSearchStatusResponse(BaseModel):
    """Response from GET /missions/{job_id}/status on DeepSearch."""

    job_id: str = Field(..., description="Job identifier")
    mission_id: str = Field(..., description="Mission ID")
    status: DeepSearchJobStatus = Field(..., description="Current job status")
    progress_percent: Optional[int] = Field(
        default=None, ge=0, le=100, description="Execution progress percentage"
    )
    current_phase: Optional[str] = Field(
        default=None, description="Current execution phase"
    )
    started_at: Optional[datetime] = Field(
        default=None, description="Execution start time"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="Execution completion time"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Execution result (when completed)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message (when failed)"
    )
    error_code: Optional[str] = Field(
        default=None, description="Error code (when failed)"
    )


class DeepSearchErrorResponse(BaseModel):
    """Error response from DeepSearch API."""

    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(default=None, description="Error code")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional error details"
    )


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
    callback_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for async correction notifications",
    )


class AutoLinkingMatch(BaseModel):
    """Individual evidence auto-linking outcome."""

    evidence_id: str
    chunk_id: Optional[str] = None
    similarity: float = 0.0
    summary_preview: Optional[str] = None
    success: bool = False
    error_type: Optional[str] = Field(default=None, description="Error classification if failed")


class AutoLinkingError(BaseModel):
    """Individual evidence auto-linking error details."""

    evidence_id: str
    error_type: str = Field(..., description="Error classification from AutoLinkErrorType")
    message: str = Field(..., description="Human-readable error message")
    best_similarity: Optional[float] = Field(default=None, description="Best similarity score achieved")
    threshold: Optional[float] = Field(default=None, description="Similarity threshold for linking")


class AutoLinkingSummary(BaseModel):
    """Aggregated evidence auto-linking telemetry."""

    attempted: conint(ge=0) = 0
    linked: conint(ge=0) = 0
    skipped: conint(ge=0) = 0
    failed: conint(ge=0) = Field(default=0, description="Count of failed auto-link attempts")
    threshold: confloat(ge=0.0, le=1.0) = 0.7
    success_rate: confloat(ge=0.0, le=1.0) = 0.0
    failure_rate: confloat(ge=0.0, le=1.0) = Field(default=0.0, description="Ratio of failed items")
    matches: List[AutoLinkingMatch] = Field(default_factory=list)
    errors: List[AutoLinkingError] = Field(default_factory=list, description="Error details for failed items")


class CorrectionQueueInfo(BaseModel):
    """Information about queued corrections for async retry."""

    queued_count: conint(ge=0) = Field(default=0, description="Number of items queued for retry")
    correction_ids: List[UUID] = Field(default_factory=list, description="IDs of queued corrections")
    callback_url: Optional[str] = Field(default=None, description="Webhook URL for notifications")


class DeepSearchIngestResponse(BaseModel):
    """Response returned after DeepSearch mission ingestion."""

    mission_uuid: UUID
    mission_id: str
    project_id: Optional[UUID] = None
    status: str
    quality_gates_passed: bool
    quality_gates: Dict[str, Any]
    auto_linking: AutoLinkingSummary
    corrections: Optional[CorrectionQueueInfo] = Field(
        default=None,
        description="Info about corrections queued for async retry (if any failures)",
    )
