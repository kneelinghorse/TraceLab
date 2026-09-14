"""Home orchestration and conservative projection of worker progress."""

import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.ports.home import HomeRepository
from app.schemas.home import HomeAttention, HomeProgress, HomeRecent, HomeResponse, HomeSection


def observed_progress(metadata: object) -> HomeProgress:
    """Show explicit worker observations; never estimate progress from old loops."""
    if not isinstance(metadata, dict):
        return HomeProgress()
    phase = metadata.get("current_phase")
    percent = metadata.get("progress_percent")
    if (
        isinstance(percent, bool)
        or not isinstance(percent, int | float)
        or not math.isfinite(percent)
        or not 0 <= percent <= 100
    ):
        percent = None
    step, total = metadata.get("current_step"), metadata.get("total_steps")
    if type(step) is not int or type(total) is not int or not 0 <= step <= total or total <= 0:
        step, total = None, None
    return HomeProgress(
        phase=phase.strip() if isinstance(phase, str) and phase.strip() else None,
        percent=percent,
        current_step=step,
        total_steps=total,
    )


class HomeService:
    def __init__(self, repository: HomeRepository):
        self.repository = repository

    def attention(self, db: Session, user: AuthenticatedUser, *, project_id: UUID | None = None) -> HomeAttention:
        return self.repository.attention(db, user, now=datetime.now(UTC).replace(tzinfo=None), project_id=project_id)

    def snapshot(self, db: Session, user: AuthenticatedUser) -> HomeResponse:
        return self.repository.snapshot(db, user, now=datetime.now(UTC).replace(tzinfo=None))

    def favorites(
        self, db: Session, user: AuthenticatedUser, *, page: int = 1, page_size: int = 6, project_id: UUID | None = None
    ) -> HomeSection[HomeRecent]:
        return self.repository.favorites(db, user, page=page, page_size=page_size, project_id=project_id)

    def set_favorite(self, db: Session, user: AuthenticatedUser, project_id: UUID, *, favorite: bool) -> None:
        self.repository.set_favorite(db, user, project_id, favorite=favorite)

    def review_completion(self, db: Session, user: AuthenticatedUser, mission_id: UUID, updated_at: datetime) -> None:
        if updated_at.tzinfo is not None:
            updated_at = updated_at.astimezone(UTC).replace(tzinfo=None)
        self.repository.review_completion(db, user, mission_id, updated_at)
