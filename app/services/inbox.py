"""Inbox orchestration: UTC normalization and the explicit, monotonic watermark rule."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.ports.inbox import InboxRepository
from app.schemas.inbox import InboxPage, InboxSection, InboxSummary


def _server_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class InboxService:
    def __init__(self, repository: InboxRepository):
        self.repository = repository

    def summary(self, db: Session, user: AuthenticatedUser) -> InboxSummary:
        return self.repository.summary(db, user, now=_server_now())

    def list(
        self, db: Session, user: AuthenticatedUser, *, section: InboxSection, page: int = 1, page_size: int = 20,
        unread_only: bool = False,
    ) -> InboxPage:
        return self.repository.list(
            db, user, now=_server_now(), section=section, page=page, page_size=page_size, unread_only=unread_only,
        )

    def mark_seen(self, db: Session, user: AuthenticatedUser, seen_through: datetime) -> datetime:
        """Advance the watermark only forward; opening a page never marks anything (decision #395)."""
        if seen_through.tzinfo is not None:
            seen_through = seen_through.astimezone(UTC).replace(tzinfo=None)
        now = _server_now()
        if seen_through > now:
            raise ValueError("seen_through cannot be later than the server clock.")
        return self.repository.mark_seen(db, user, seen_through, now=now)
