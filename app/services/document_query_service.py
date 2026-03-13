"""Query helpers for document read endpoints."""

from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy.orm import Session, load_only, selectinload

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.schemas.pagination import PaginationMeta


class DocumentQueryService:
    """Encapsulates filtering and pagination for documents."""

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def list_documents(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        project_id: UUID | None = None,
        processed: bool | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[Document], PaginationMeta]:
        """Return paginated documents ordered by upload time.

        Args:
            db: Database session
            page: Page number (1-indexed)
            page_size: Results per page
            project_id: Optional project filter
            processed: Optional processing state filter
            search: Optional name filter
            include_deleted: If True, include soft-deleted documents
        """

        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(Document).options(
            load_only(
                Document.id,
                Document.project_id,
                Document.name,
                Document.file_type,
                Document.file_size,
                Document.mime_type,
                Document.source_type,
                Document.uploaded_at,
                Document.processed,
                Document.chunked,
                Document.embedded,
                Document.validation_status,
                Document.deleted_at,
                Document.deleted_by,
            )
        )

        # Filter out soft-deleted documents by default
        if not include_deleted:
            query = query.filter(Document.deleted_at.is_(None))

        if project_id:
            query = query.filter(Document.project_id == project_id)
        if processed is not None:
            query = query.filter(Document.processed == processed)
        if search:
            like_term = f"%{search.strip()}%"
            query = query.filter(Document.name.ilike(like_term))

        query = query.order_by(Document.uploaded_at.desc())
        total = query.count()
        items = (
            query.offset((page - 1) * clamped_page_size).limit(clamped_page_size).all()
        )

        total_pages = math.ceil(total / clamped_page_size) if total else 0
        meta = PaginationMeta(
            page=page,
            page_size=clamped_page_size,
            total=total,
            pages=total_pages,
        )
        return items, meta

    def get_document(
        self,
        db: Session,
        document_id: UUID,
        include_deleted: bool = False,
    ) -> Document | None:
        """Fetch a single document by identifier.

        Args:
            db: Database session
            document_id: Document UUID
            include_deleted: If True, return even if soft-deleted
        """
        query = (
            db.query(Document)
            .options(
                selectinload(Document.processing_events),
                selectinload(Document.tags),
                selectinload(Document.chunks),
            )
            .filter(Document.id == document_id)
        )
        if not include_deleted:
            query = query.filter(Document.deleted_at.is_(None))
        return query.first()

    def list_chunks_by_document(
        self,
        db: Session,
        document_id: UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[DocumentChunk], PaginationMeta]:
        """Return paginated chunks for a document, ordered by chunk_index."""

        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)

        query = query.order_by(DocumentChunk.chunk_index.asc())
        total = query.count()
        items = (
            query.offset((page - 1) * clamped_page_size).limit(clamped_page_size).all()
        )

        total_pages = math.ceil(total / clamped_page_size) if total else 0
        meta = PaginationMeta(
            page=page,
            page_size=clamped_page_size,
            total=total,
            pages=total_pages,
        )
        return items, meta
