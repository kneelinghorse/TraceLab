"""Shared SQL predicates for Home attention and paginated mission views."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select

from app.models.mission import Mission
from app.models.mission_review import MissionReview

STALLED_AFTER_SECONDS = 3600


def attention_predicates(user_id: UUID | None, *, now: datetime):
    """Return the attention filter and its priority, before count/pagination.

    A review only covers this user's exact result version. Missing worker
    progress never implies failure; only queued age defines the stalled group.
    """
    reviewed = select(MissionReview.mission_id).where(
        MissionReview.user_id == user_id,
        MissionReview.mission_id == Mission.id,
        MissionReview.mission_updated_at == Mission.updated_at,
    ).exists()
    stale = and_(
        Mission.status == "queued",
        func.coalesce(Mission.queued_at, Mission.created_at) <= now - timedelta(seconds=STALLED_AFTER_SECONDS),
    )
    unreviewed = and_(Mission.status == "completed", ~reviewed)
    attention = or_(Mission.status.in_(["validation_failed", "blocked"]), stale, unreviewed)
    rank = case(
        (Mission.status == "validation_failed", 0),
        (Mission.status == "blocked", 1),
        (stale, 2),
        (unreviewed, 3),
        else_=4,
    )
    return attention, rank
