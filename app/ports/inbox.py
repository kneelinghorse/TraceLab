"""Persistence boundary for the priority inbox and its per-user watermark."""

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.inbox import InboxPage, InboxSection, InboxSummary


class InboxRepository(Protocol):
    def summary(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> InboxSummary: ...

    def list(
        self, db: Session, user: AuthenticatedUser, *, now: datetime, section: InboxSection,
        page: int, page_size: int, unread_only: bool,
    ) -> InboxPage: ...

    def mark_seen(self, db: Session, user: AuthenticatedUser, seen_through: datetime, *, now: datetime) -> datetime: ...
