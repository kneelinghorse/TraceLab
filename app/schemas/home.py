"""Bounded Home sections with database totals independent of their item limits."""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.activity import ActivityPage

T = TypeVar("T")


class HomeSection(BaseModel, Generic[T]):
    total: int
    items: list[T]


class HomeProgress(BaseModel):
    phase: str | None = None
    percent: float | None = Field(default=None, ge=0, le=100)
    current_step: int | None = None
    total_steps: int | None = None


class HomeMission(BaseModel):
    id: UUID
    mission_id: str
    title: str
    status: str
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    progress: HomeProgress
    report_id: UUID | None
    evidence_count: int
    evidence_href: str | None


class HomeRecent(BaseModel):
    id: UUID
    title: str
    updated_at: datetime | None
    href: str


class HomeEvidenceActivity(BaseModel):
    project_id: UUID
    mission_id: UUID | None
    session_key: str
    origin: str
    entry_count: int
    last_created_at: datetime
    href: str


class HomeMissionTotals(BaseModel):
    total: int
    by_status: dict[str, int]


class HomeResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int = 30
    missions: HomeMissionTotals
    activity: ActivityPage
    active_runs: HomeSection[HomeMission]
    recent_reports: HomeSection[HomeRecent]
    recent_projects: HomeSection[HomeRecent]
    favorites: HomeSection[HomeRecent]
    evidence_activity: HomeSection[HomeEvidenceActivity]

