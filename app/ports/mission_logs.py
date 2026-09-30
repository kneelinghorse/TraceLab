"""Persistence boundary for append/replay under the mission ownership lock."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


class MissionLogRepository(Protocol):
    def lock_mission(self, db: Session, mission_id: UUID) -> tuple[Any | None, datetime]:
        """First operation in a fresh transaction; retain lock until caller commits."""
        ...

    def find_events(self, db: Session, mission_id: UUID, attempt: int, event_ids: list[UUID], sequences: list[int]) -> list[Any]: ...

    def has_versioned_logs(self, db: Session, mission_id: UUID) -> bool: ...

    def append(self, db: Session, rows: list[dict[str, Any]]) -> None: ...
