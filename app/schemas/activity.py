"""Recent activity: one recency-ordered stream; status is a label and never affects order."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ActivityType = Literal["mission", "report", "evidence"]


class ActivityItem(BaseModel):
    type: ActivityType
    id: UUID
    title: str
    subtitle: str | None = None
    status: str | None = None
    occurred_at: datetime
    href: str
    new: bool


class ActivityPage(BaseModel):
    generated_at: datetime
    refresh_seconds: int = 30
    page: int
    page_size: int
    total: int
    new_total: int
    items: list[ActivityItem]


class ActivitySummary(BaseModel):
    generated_at: datetime
    new_total: int
    by_type: dict[str, int]


class ViewedItem(BaseModel):
    type: ActivityType
    id: UUID
    occurred_at: datetime


class MarkViewedRequest(BaseModel):
    items: list[ViewedItem] = Field(min_length=1, max_length=200)


class MarkViewedResponse(BaseModel):
    viewed: int
    new_total: int
