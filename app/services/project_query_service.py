"""Query helpers for project read endpoints."""

from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk as Chunk
from app.models.document import Document
from app.models.project import Project
from app.models.report import Report
from app.schemas.pagination import PaginationMeta
from app.schemas.project import ProjectCreate, ProjectStats, ProjectUpdate
from app.services.ownership import default_workspace_id


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
        search: str | None = None,
        include_deleted: bool = False,
        access_filter=None,
    ) -> tuple[list[Project], PaginationMeta]:
        """Return paginated projects ordered by recency.

        Args:
            db: Database session
            page: Page number (1-indexed)
            page_size: Results per page
            search: Optional name filter
            include_deleted: If True, include soft-deleted projects
            access_filter: Optional RBAC row-filter (authorization.accessible_filter)
                applied BEFORE count + pagination so the page is both correct and
                scoped to rows the caller may read (T47.3). None = no filtering.
        """

        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(Project)

        # Filter out soft-deleted projects by default
        if not include_deleted:
            query = query.filter(Project.deleted_at.is_(None))

        if search:
            like_term = f"%{search.strip()}%"
            query = query.filter(Project.name.ilike(like_term))

        if access_filter is not None:
            query = query.filter(access_filter)

        query = query.order_by(Project.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * clamped_page_size).limit(clamped_page_size).all()

        total_pages = math.ceil(total / clamped_page_size) if total else 0
        meta = PaginationMeta(
            page=page,
            page_size=clamped_page_size,
            total=total,
            pages=total_pages,
        )
        return items, meta

    def get_project(
        self,
        db: Session,
        project_id: UUID,
        include_deleted: bool = False,
    ) -> Project | None:
        """Fetch a single project.

        Args:
            db: Database session
            project_id: Project UUID
            include_deleted: If True, return even if soft-deleted
        """
        query = db.query(Project).filter(Project.id == project_id)
        if not include_deleted:
            query = query.filter(Project.deleted_at.is_(None))
        return query.first()

    def create_project(self, db: Session, data: ProjectCreate, owner_id: UUID | None = None) -> Project:
        """Create a new project.

        owner_id is derived from the authenticated caller by the route (T43.4) and
        recorded as the trustworthy owner; the legacy self-asserted user_id is no
        longer accepted from the request body. workspace_id (the project's Space) is
        likewise derived server-side via ``default_workspace_id`` (T44.4), never
        from the body.
        """
        project = Project(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            workspace_id=default_workspace_id(db),
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

    def update_project(self, db: Session, project_id: UUID, data: ProjectUpdate) -> Project | None:
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
        """Hard delete a project and all associated data (cascading via FK constraints).

        WARNING: This permanently deletes the project. Use soft_delete_project for
        recoverable deletion.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False

        db.delete(project)
        db.commit()
        return True

    def soft_delete_project(
        self,
        db: Session,
        project_id: UUID,
        deleted_by: str = None,
    ) -> bool | None:
        """Soft delete a project.

        Args:
            db: Database session
            project_id: UUID of project to delete
            deleted_by: Identifier of who performed the deletion

        Returns:
            None if project not found
            False if project already deleted
            True if successfully soft deleted
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        if project.is_deleted:
            return False

        project.soft_delete(deleted_by=deleted_by)
        db.commit()
        return True

    def restore_project(
        self,
        db: Session,
        project_id: UUID,
    ) -> bool | None:
        """Restore a soft-deleted project.

        Args:
            db: Database session
            project_id: UUID of project to restore

        Returns:
            None if project not found
            False if project is not deleted
            True if successfully restored
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        if not project.is_deleted:
            return False

        project.restore()
        db.commit()
        return True

    def get_project_stats(self, db: Session, project_id: UUID) -> ProjectStats | None:
        """Get aggregated statistics for a project.

        Only counts non-deleted documents in the statistics.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        # Count documents (exclude soft-deleted)
        document_count = (
            db.query(func.count(Document.id))
            .filter(Document.project_id == project_id)
            .filter(Document.deleted_at.is_(None))
            .scalar()
            or 0
        )

        # Count chunks and sum tokens (via non-deleted documents)
        chunk_stats = (
            db.query(
                func.count(Chunk.id).label("chunk_count"),
                func.coalesce(func.sum(Chunk.token_count), 0).label("total_tokens"),
            )
            .join(Document, Chunk.document_id == Document.id)
            .filter(Document.project_id == project_id)
            .filter(Document.deleted_at.is_(None))
            .first()
        )
        chunk_count = chunk_stats.chunk_count if chunk_stats else 0
        total_tokens = chunk_stats.total_tokens if chunk_stats else 0

        # Count reports
        report_count = db.query(func.count(Report.id)).filter(Report.project_id == project_id).scalar() or 0

        # Get last updated timestamp (most recent non-deleted document or report)
        last_doc_update = (
            db.query(func.max(Document.updated_at))
            .filter(Document.project_id == project_id)
            .filter(Document.deleted_at.is_(None))
            .scalar()
        )
        last_report_update = db.query(func.max(Report.updated_at)).filter(Report.project_id == project_id).scalar()
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
