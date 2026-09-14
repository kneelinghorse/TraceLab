"""Shared SQL predicates for Home attention and paginated mission views."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select

from app.models.mission import Mission
from app.models.mission_review import MissionReview

STALLED_AFTER_SECONDS = 3600


def attention_reason_clauses(user_id: UUID | None, *, now: datetime):
    """Return mutually exclusive reasons in the established attention priority.

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
    return {
        "validation_failed": Mission.status == "validation_failed",
        "blocked": Mission.status == "blocked",
        "stalled": stale,
        "unreviewed": unreviewed,
    }


def attention_predicates(user_id: UUID | None, *, now: datetime):
    """Preserve the established attention membership and priority for every caller."""
    reasons = attention_reason_clauses(user_id, now=now)
    attention = or_(Mission.status.in_(["validation_failed", "blocked"]), reasons["stalled"], reasons["unreviewed"])
    rank = case(*((clause, index) for index, clause in enumerate(reasons.values())), else_=4)
    return attention, rank
