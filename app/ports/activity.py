"""Persistence boundary for the recent activity stream and per-item viewed marks."""

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.activity import ActivityPage, ActivitySummary, ViewedItem


class ActivityRepository(Protocol):
    def page(
        self, db: Session, user: AuthenticatedUser, *, now: datetime, page: int = 1, page_size: int = 20
    ) -> ActivityPage: ...

    def summary(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> ActivitySummary: ...

    def mark_viewed(self, db: Session, user: AuthenticatedUser, items: list[ViewedItem], *, now: datetime) -> int: ...
