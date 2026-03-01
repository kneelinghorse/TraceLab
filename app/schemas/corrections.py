"""Schemas for correction loop endpoints and webhook payloads."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, conint, confloat


class CorrectionStatus(str, Enum):
    """Status of a correction item in the queue."""

    PENDING = "pending"
    """Waiting for retry attempt."""

    IN_PROGRESS = "in_progress"
    """Currently being processed."""

    COMPLETED = "completed"
    """Successfully linked after retry."""

    FAILED = "failed"
    """All retry attempts exhausted."""

    SKIPPED = "skipped"
    """Marked as non-retryable (e.g., validation error)."""


class CorrectionErrorType(str, Enum):
    """Error taxonomy for auto-linking failures (mirrors AutoLinkErrorType)."""

    NO_EMBEDDING = "no_embedding"
    LOW_SIMILARITY = "low_similarity"
    NO_CHUNKS = "no_chunks"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    EMPTY_CONTENT = "empty_content"
    DATABASE_ERROR = "database_error"
    EMBEDDING_FAILED = "embedding_failed"
    QDRANT_ERROR = "qdrant_error"


class CorrectionItem(BaseModel):
    """Individual evidence correction item."""

    correction_id: UUID = Field(..., description="Unique correction identifier")
    mission_uuid: UUID = Field(..., description="Parent mission UUID")
    evidence_id: str = Field(..., description="Original evidence ID from payload")
    status: CorrectionStatus = Field(default=CorrectionStatus.PENDING)
    error_type: CorrectionErrorType = Field(..., description="Classification of the failure")
    retry_count: conint(ge=0) = Field(default=0, description="Number of retry attempts made")
    max_retries: conint(ge=0) = Field(default=2, description="Maximum retry attempts allowed")
    last_error: Optional[str] = Field(default=None, description="Most recent error message")
    best_similarity: Optional[confloat(ge=0.0, le=1.0)] = Field(
        default=None, description="Best similarity score achieved"
    )
    similarity_threshold: confloat(ge=0.0, le=1.0) = Field(
        default=0.7, description="Threshold required for linking"
    )
    chunk_id: Optional[str] = Field(default=None, description="Linked chunk ID if successful")
    created_at: datetime = Field(..., description="When correction was queued")
    updated_at: datetime = Field(..., description="Last update timestamp")
    next_retry_at: Optional[datetime] = Field(
        default=None, description="Scheduled time for next retry"
    )
    callback_url: Optional[str] = Field(
        default=None, description="DeepSearch webhook URL for notifications"
    )


class CorrectionQueueStats(BaseModel):
    """Aggregated correction queue statistics."""

    pending: conint(ge=0) = Field(default=0, description="Items waiting for retry")
    in_progress: conint(ge=0) = Field(default=0, description="Items currently processing")
    completed: conint(ge=0) = Field(default=0, description="Successfully corrected items")
    failed: conint(ge=0) = Field(default=0, description="Items that exhausted retries")
    skipped: conint(ge=0) = Field(default=0, description="Non-retryable items")
    total: conint(ge=0) = Field(default=0, description="Total items in queue")

    @property
    def success_rate(self) -> float:
        """Calculate success rate of processed items."""
        processed = self.completed + self.failed
        if processed == 0:
            return 0.0
        return round(self.completed / processed, 3)


class CorrectionStatusResponse(BaseModel):
    """Response for GET /api/v1/deepsearch/corrections."""

    stats: CorrectionQueueStats = Field(..., description="Queue statistics")
    error_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Count by error type"
    )
    recent_items: List[CorrectionItem] = Field(
        default_factory=list, description="Most recent correction items"
    )
    last_updated: datetime = Field(..., description="When stats were computed")


class CorrectionTriggerRequest(BaseModel):
    """Request to trigger corrections for a mission."""

    mission_uuid: Optional[UUID] = Field(
        default=None, description="Specific mission to retry (None = all pending)"
    )
    evidence_ids: Optional[List[str]] = Field(
        default=None, description="Specific evidence IDs to retry"
    )
    force_retry: bool = Field(
        default=False, description="Retry even if max attempts exceeded"
    )
    callback_url: Optional[str] = Field(
        default=None, description="Override webhook URL for notifications"
    )


class CorrectionTriggerResponse(BaseModel):
    """Response for POST /api/v1/deepsearch/corrections."""

    triggered: conint(ge=0) = Field(default=0, description="Number of items queued for retry")
    skipped: conint(ge=0) = Field(default=0, description="Items skipped (max retries, etc.)")
    correction_ids: List[UUID] = Field(
        default_factory=list, description="IDs of triggered corrections"
    )
    message: str = Field(..., description="Summary message")


class WebhookNotificationType(str, Enum):
    """Type of webhook notification."""

    CORRECTION_SUCCESS = "correction_success"
    CORRECTION_FAILURE = "correction_failure"
    BATCH_COMPLETE = "batch_complete"


class WebhookPayload(BaseModel):
    """Payload sent to DeepSearch webhook callbacks."""

    notification_type: WebhookNotificationType = Field(..., description="Event type")
    mission_uuid: UUID = Field(..., description="Mission UUID")
    mission_id: str = Field(..., description="Original mission ID")
    evidence_id: str = Field(..., description="Evidence item identifier")
    timestamp: datetime = Field(..., description="When notification was generated")
    success: bool = Field(..., description="Whether correction succeeded")
    chunk_id: Optional[str] = Field(default=None, description="Linked chunk if successful")
    similarity: Optional[float] = Field(default=None, description="Final similarity score")
    error_type: Optional[str] = Field(default=None, description="Error type if failed")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")
    retry_count: conint(ge=0) = Field(default=0, description="Total retry attempts made")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class BatchWebhookPayload(BaseModel):
    """Batch webhook notification for mission completion."""

    notification_type: WebhookNotificationType = Field(
        default=WebhookNotificationType.BATCH_COMPLETE
    )
    mission_uuid: UUID = Field(..., description="Mission UUID")
    mission_id: str = Field(..., description="Original mission ID")
    timestamp: datetime = Field(..., description="When batch completed")
    total_items: conint(ge=0) = Field(..., description="Total evidence items processed")
    successful: conint(ge=0) = Field(..., description="Successfully linked items")
    failed: conint(ge=0) = Field(..., description="Failed items after retries")
    success_rate: confloat(ge=0.0, le=1.0) = Field(..., description="Overall success rate")
    items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Individual item summaries"
    )


class TelemetryRecord(BaseModel):
    """Grafana-ready telemetry record for dashboards."""

    ts: datetime = Field(..., description="Timestamp (ISO 8601)")
    event: str = Field(..., description="Event type (correction_attempt, correction_success, etc.)")
    mission_id: str = Field(..., description="Mission identifier")
    evidence_id: Optional[str] = Field(default=None, description="Evidence identifier")
    error_type: Optional[str] = Field(default=None, description="Error classification")
    retry_count: conint(ge=0) = Field(default=0, description="Retry attempt number")
    similarity: Optional[float] = Field(default=None, description="Similarity score")
    success: bool = Field(default=False, description="Whether operation succeeded")
    duration_ms: Optional[int] = Field(default=None, description="Processing duration")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional fields")
