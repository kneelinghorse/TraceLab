"""Schemas for PEDR pre-flight query endpoint.

Pre-flight queries allow DeepSearch to check TraceLab before launching
new research missions, enabling reuse of existing high-quality research.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, confloat, conint


class PreflightQuery(BaseModel):
    """Request payload for pre-flight existence check."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Research objective or topic to check for existing research.",
    )
    min_quality_gates: conint(ge=0, le=5) = Field(
        default=4,
        description="Minimum passing quality gates for reuse recommendation.",
    )
    status: List[str] = Field(
        default_factory=lambda: ["complete"],
        description="Allowed mission statuses (default: complete only).",
    )
    top_k: conint(ge=1, le=20) = Field(
        default=5,
        description="Maximum number of matches to return.",
    )
    similarity_threshold: confloat(ge=0.0, le=1.0) = Field(
        default=0.70,
        description="Minimum similarity score to consider a match.",
    )


class PreflightMatchInsight(BaseModel):
    """Key insight from a matching mission."""

    text: str = Field(..., description="Insight content (truncated if needed).")
    index: int = Field(..., ge=0, description="Position in original insights list.")


class PreflightMatch(BaseModel):
    """Summary of a mission matching the pre-flight query."""

    mission_id: str = Field(..., description="Mission protocol ID (e.g., DRM.0.5).")
    mission_uuid: str = Field(..., description="Internal UUID for API references.")
    title: str = Field(..., description="Mission title.")
    objective: str = Field(
        ...,
        max_length=200,
        description="Mission objective (truncated to 200 chars).",
    )
    status: str = Field(..., description="Mission status (draft, complete, etc.).")
    quality_gates_passed: int = Field(..., ge=0, description="Number of passing gates.")
    quality_gates_total: int = Field(default=5, description="Total quality gates.")
    quality_score: confloat(ge=0.0, le=2.0) = Field(
        ...,
        description="Combined quality multiplier.",
    )
    similarity_score: confloat(ge=0.0, le=1.0) = Field(
        ...,
        description="Semantic similarity to query.",
    )
    key_insights: List[PreflightMatchInsight] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 key insights from the mission.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the mission was created.",
    )
    tags: List[str] = Field(default_factory=list, description="Mission tags.")


class PreflightRecommendation(BaseModel):
    """Pre-flight response with reuse recommendation."""

    action: Literal["reuse", "review", "proceed"] = Field(
        ...,
        description=(
            "Recommendation: 'reuse' (use existing research), "
            "'review' (check existing before proceeding), "
            "'proceed' (no relevant existing research)."
        ),
    )
    matches: List[PreflightMatch] = Field(
        default_factory=list,
        description="Matching missions ordered by relevance.",
    )
    summary: str = Field(
        ...,
        description="Human-readable summary of the recommendation.",
    )
    top_score: Optional[confloat(ge=0.0, le=1.0)] = Field(
        default=None,
        description="Highest similarity score among matches.",
    )
    match_count: conint(ge=0) = Field(
        default=0,
        description="Total number of matches found.",
    )
    query: str = Field(..., description="Original query for reference.")
    latency_ms: confloat(ge=0.0) = Field(
        default=0.0,
        description="Query execution time in milliseconds.",
    )
    filters_applied: dict = Field(
        default_factory=dict,
        description="Filters used for the query.",
    )


class PreflightTelemetry(BaseModel):
    """Telemetry event for pre-flight query tracking."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    query: str
    action: Literal["reuse", "review", "proceed"]
    top_score: Optional[float] = None
    match_count: int = 0
    latency_ms: float = 0.0
    min_quality_gates: int = 4
    status_filters: List[str] = Field(default_factory=list)
    agent: str = Field(default="unknown", description="Calling agent identifier.")
