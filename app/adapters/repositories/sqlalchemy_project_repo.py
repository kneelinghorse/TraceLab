# ABOUTME: SQLAlchemy adapter for ProjectRepository port.
# ABOUTME: Delegates to ProjectQueryService for all project operations.

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.project_query_service import ProjectQueryService


class SQLAlchemyProjectRepository:
    """Adapter bridging ProjectQueryService to ProjectRepository protocol."""

    def __init__(self, query_service: ProjectQueryService | None = None):
        self._query = query_service or ProjectQueryService()

    def get_project(
        self,
        db: Session,
        project_id: UUID,
        include_deleted: bool = False,
    ):
        return self._query.get_project(db, project_id, include_deleted=include_deleted)

    def list_projects(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        include_deleted: bool = False,
    ):
        return self._query.list_projects(
            db,
            page=page,
            page_size=page_size,
            search=search,
            include_deleted=include_deleted,
        )

    def create_project(self, db: Session, data: Any):
        return self._query.create_project(db, data)

    def update_project(self, db: Session, project_id: UUID, data: Any):
        return self._query.update_project(db, project_id, data)

    def soft_delete_project(
        self,
        db: Session,
        project_id: UUID,
        deleted_by: str | None = None,
    ):
        return self._query.soft_delete_project(db, project_id, deleted_by=deleted_by)
