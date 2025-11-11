"""Query helpers for project read endpoints."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.pagination import PaginationMeta


class ProjectQueryService:
    """Encapsulates pagination, filtering, and ordering for projects."""

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def list_projects(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
    ) -> Tuple[List[Project], PaginationMeta]:
        """Return paginated projects ordered by recency."""

        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(Project)

        if search:
            like_term = f"%{search.strip()}%"
            query = query.filter(Project.name.ilike(like_term))

        query = query.order_by(Project.created_at.desc())
        total = query.count()
        items = (
            query.offset((page - 1) * clamped_page_size)
            .limit(clamped_page_size)
            .all()
        )

        total_pages = math.ceil(total / clamped_page_size) if total else 0
        meta = PaginationMeta(
            page=page,
            page_size=clamped_page_size,
            total=total,
            pages=total_pages,
        )
        return items, meta

    def get_project(self, db: Session, project_id: UUID) -> Optional[Project]:
        """Fetch a single project."""

        return db.query(Project).filter(Project.id == project_id).first()
