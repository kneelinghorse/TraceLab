"""Persistence boundary for the operator's Home."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.home import HomeRecent, HomeResponse, HomeSection


class HomeRepository(Protocol):
    def favorites(
        self, db: Session, user: AuthenticatedUser, *, page: int = 1, page_size: int = 6, project_id: UUID | None = None
    ) -> HomeSection[HomeRecent]: ...

    def set_favorite(self, db: Session, user: AuthenticatedUser, project_id: UUID, *, favorite: bool) -> None: ...

    def snapshot(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> HomeResponse: ...
