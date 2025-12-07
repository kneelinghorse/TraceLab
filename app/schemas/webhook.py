"""Pydantic schemas for webhook payloads.

Handles incoming webhooks from DeepSearch and other external services.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DeepSearchWebhookStatus(str, Enum):
    """Status values in DeepSearch webhook payloads."""

    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionMetadata(BaseModel):
    """Execution metadata from DeepSearch job completion."""

    loops_executed: Optional[int] = Field(default=None, description="Number of research loops executed")
    sources_found: Optional[int] = Field(default=None, description="Total sources discovered")
    duration_seconds: Optional[float] = Field(default=None, description="Total execution time")
    model_used: Optional[str] = Field(default=None, description="AI model used for execution")
    pedr_checked: Optional[bool] = Field(default=None, description="Whether PEDR was checked")
    pedr_reused: Optional[bool] = Field(default=None, description="Whether PEDR cache was reused")

    class Config:
        extra = "allow"


class DeepSearchWebhookPayload(BaseModel):
    """Payload received from DeepSearch webhook callback.

    Sent by DeepSearch when a job completes (success or failure).
    """

    job_id: str = Field(..., description="DeepSearch job identifier")
    mission_id: str = Field(..., description="Human-readable mission identifier (e.g., B16.1)")
    status: DeepSearchWebhookStatus = Field(..., description="Job completion status")
    execution_metadata: Optional[ExecutionMetadata] = Field(
        default=None, description="Execution metrics and telemetry"
    )
    result_markdown: Optional[str] = Field(
        default=None, description="Raw markdown output from research"
    )
    result_protocol: Optional[Dict[str, Any]] = Field(
        default=None, description="Mission Protocol compliant result object"
    )
    error: Optional[str] = Field(default=None, description="Error message if status is failed")


class WebhookResponse(BaseModel):
    """Standard response for webhook endpoints."""

    received: bool = Field(default=True, description="Acknowledgment of webhook receipt")
    mission_id: Optional[str] = Field(default=None, description="Mission ID that was updated")
    status: Optional[str] = Field(default=None, description="New mission status")
    message: Optional[str] = Field(default=None, description="Additional info or error message")


class WebhookErrorResponse(BaseModel):
    """Error response for webhook failures."""

    received: bool = Field(default=False)
    error: str = Field(..., description="Error description")
    error_code: Optional[str] = Field(default=None, description="Error classification")
