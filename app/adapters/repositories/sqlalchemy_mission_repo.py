# ABOUTME: SQLAlchemy adapter for MissionRepository port.
# ABOUTME: Delegates to MissionService for all mission CRUD and status transitions.

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.mission_service import MissionService


class SQLAlchemyMissionRepository:
    """Adapter bridging MissionService to MissionRepository protocol."""

    def __init__(self, service: MissionService | None = None):
        self._service = service or MissionService()

    def get_mission(self, db: Session, mission_id: UUID):
        return self._service.get_mission(db, mission_id)

    def list_missions(
        self,
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        project_id: UUID | None = None,
    ):
        return self._service.list_missions(
            db,
            page=page,
            page_size=page_size,
            status=status,
            project_id=project_id,
        )

    def create_mission(self, db: Session, data: Any):
        return self._service.create_mission(db, data)

    def update_mission(self, db: Session, mission_id: UUID, data: Any):
        return self._service.update_mission(db, mission_id, data)

    def transition_status(
        self,
        db: Session,
        mission_id: UUID,
        new_status: str,
        error_message: str | None = None,
    ):
        return self._service.transition_status(db, mission_id, new_status, error_message=error_message)
