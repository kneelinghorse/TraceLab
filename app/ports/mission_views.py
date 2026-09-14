"""Persistence boundary for personal saved mission filters."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.mission_views import MissionViewCreate, MissionViewResponse, MissionViewUpdate


class MissionViewRepository(Protocol):
    def list(self, db: Session, user: AuthenticatedUser) -> list[MissionViewResponse]: ...
    def create(self, db: Session, user: AuthenticatedUser, data: MissionViewCreate) -> MissionViewResponse: ...
    def update(self, db: Session, user: AuthenticatedUser, view_id: UUID, data: MissionViewUpdate) -> MissionViewResponse: ...
    def delete(self, db: Session, user: AuthenticatedUser, view_id: UUID) -> None: ...
