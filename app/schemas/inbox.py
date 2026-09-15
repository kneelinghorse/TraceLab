"""Priority inbox contract: scoped sections behind one per-user watermark, no per-item rows."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

InboxSection = Literal["failures", "completions", "evidence"]
DEFAULT_LOOKBACK_SECONDS = 7 * 24 * 3600
REFRESH_SECONDS = 30


class InboxCounts(BaseModel):
    failures: int
    completions: int
    evidence: int
    total: int


class InboxSummary(BaseModel):
    generated_at: datetime
    refresh_seconds: int = REFRESH_SECONDS
    seen_through: datetime
    default_lookback_seconds: int = DEFAULT_LOOKBACK_SECONDS
    unread: InboxCounts


class InboxItem(BaseModel):
    section: InboxSection
    id: str
    title: str
    label: str
    status: str | None = None
    occurred_at: datetime
    updated_at: datetime | None = None
    unread: bool
    href: str
    reviewed: bool | None = None
    entry_count: int | None = None
    project_id: UUID | None = None
    mission_id: UUID | None = None
    session_key: str | None = None
    origin: str | None = None


class InboxPage(BaseModel):
    section: InboxSection
    generated_at: datetime
    seen_through: datetime
    total: int
    items: list[InboxItem]


class MarkSeenRequest(BaseModel):
    seen_through: datetime


class InboxSeenResponse(BaseModel):
    seen_through: datetime
