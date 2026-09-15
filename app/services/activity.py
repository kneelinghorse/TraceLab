"""Recent activity orchestration: newest first, new until opened or marked viewed."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.ports.activity import ActivityRepository
from app.schemas.activity import ActivityPage, ActivitySummary, MarkViewedResponse, ViewedItem


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value


class ActivityService:
    def __init__(self, repository: ActivityRepository):
        self.repository = repository

    def page(self, db: Session, user: AuthenticatedUser, *, page: int = 1, page_size: int = 20) -> ActivityPage:
        return self.repository.page(db, user, now=_now(), page=page, page_size=page_size)

    def summary(self, db: Session, user: AuthenticatedUser) -> ActivitySummary:
        return self.repository.summary(db, user, now=_now())

    def mark_viewed(self, db: Session, user: AuthenticatedUser, items: list[ViewedItem]) -> MarkViewedResponse:
        now = _now()
        normalized = [ViewedItem(type=i.type, id=i.id, occurred_at=naive_utc(i.occurred_at)) for i in items]
        viewed = self.repository.mark_viewed(db, user, normalized, now=now)
        return MarkViewedResponse(viewed=viewed, new_total=self.repository.summary(db, user, now=now).new_total)
