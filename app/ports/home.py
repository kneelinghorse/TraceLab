"""Persistence boundary for the operator's Home."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.home import HomeResponse


class HomeRepository(Protocol):
    def snapshot(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> HomeResponse: ...

    def review_completion(
        self, db: Session, user: AuthenticatedUser, mission_id: UUID, updated_at: datetime
    ) -> None: ...
