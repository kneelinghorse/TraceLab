"""Query helpers for project read endpoints."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.document import Document
from app.models.chunk import DocumentChunk as Chunk
from app.models.report import Report
from app.schemas.pagination import PaginationMeta
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectStats


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

    def create_project(self, db: Session, data: ProjectCreate) -> Project:
        """Create a new project."""
        project = Project(
            name=data.name,
            description=data.description,
            user_id=data.user_id,
            mission_protocol_id=data.mission_protocol_id,
            research_type=data.research_type,
            methodology=data.methodology,
            status=data.status or "active",
            quality_score=data.quality_score,
            last_quality_check=data.last_quality_check,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    def update_project(
        self, db: Session, project_id: UUID, data: ProjectUpdate
    ) -> Optional[Project]:
        """Update an existing project."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(project, key, value)

        db.commit()
        db.refresh(project)
        return project

    def delete_project(self, db: Session, project_id: UUID) -> bool:
        """Delete a project and all associated data (cascading via FK constraints)."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False

        db.delete(project)
        db.commit()
        return True

    def get_project_stats(self, db: Session, project_id: UUID) -> Optional[ProjectStats]:
        """Get aggregated statistics for a project."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        # Count documents
        document_count = (
            db.query(func.count(Document.id))
            .filter(Document.project_id == project_id)
            .scalar()
            or 0
        )

        # Count chunks and sum tokens (via documents)
        chunk_stats = (
            db.query(
                func.count(Chunk.id).label("chunk_count"),
                func.coalesce(func.sum(Chunk.token_count), 0).label("total_tokens"),
            )
            .join(Document, Chunk.document_id == Document.id)
            .filter(Document.project_id == project_id)
            .first()
        )
        chunk_count = chunk_stats.chunk_count if chunk_stats else 0
        total_tokens = chunk_stats.total_tokens if chunk_stats else 0

        # Count reports
        report_count = (
            db.query(func.count(Report.id))
            .filter(Report.project_id == project_id)
            .scalar()
            or 0
        )

        # Get last updated timestamp (most recent document or report)
        last_doc_update = (
            db.query(func.max(Document.updated_at))
            .filter(Document.project_id == project_id)
            .scalar()
        )
        last_report_update = (
            db.query(func.max(Report.updated_at))
            .filter(Report.project_id == project_id)
            .scalar()
        )
        last_updated = max(
            filter(None, [project.updated_at, last_doc_update, last_report_update]),
            default=project.updated_at,
        )

        return ProjectStats(
            project_id=project.id,
            name=project.name,
            document_count=document_count,
            chunk_count=chunk_count,
            report_count=report_count,
            total_tokens=total_tokens,
            last_updated=last_updated,
        )
