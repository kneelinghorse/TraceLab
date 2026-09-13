"""Truthful system aggregates with explicit observation scope and unavailable values."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StateCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class WorkerObservation(BaseModel):
    status: str = "unavailable"
    checked_at: datetime
    uptime_seconds: float | None = None
    missions_processed: int | None = None
    missions_completed: int | None = None
    missions_failed: int | None = None
    current_mission_id: str | None = None
    error: str | None = None


class RecentAdminMission(BaseModel):
    id: UUID
    mission_id: str
    title: str
    status: str
    updated_at: datetime


class AdminStatsResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int = 30
    scope: Literal["system"] = "system"
    missions: StateCounts
    projects: int
    documents: int
    chunks: int
    reports: int
    ingestion_jobs: StateCounts
    graph_edges: int
    graph_edges_by_type: dict[str, int]
    evidence_entries: int
    evidence_sources: int
    evidence_notes: int
    recent_missions: list[RecentAdminMission]
    worker: WorkerObservation | None = None
    reconciler: dict[str, Any] = Field(default_factory=dict)
    corrections: dict[str, int] | None = None
    corrections_error: str | None = None
    process_scope: str = "Reconciler and correction queue describe this API process and reset on restart."
