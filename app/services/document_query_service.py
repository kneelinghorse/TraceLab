"""Query helpers for document read endpoints."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

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
        project_id: Optional[UUID] = None,
        processed: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Document], PaginationMeta]:
        """Return paginated documents ordered by upload time."""

        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(Document)

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

    def get_document(self, db: Session, document_id: UUID) -> Optional[Document]:
        """Fetch a single document by identifier."""

        return db.query(Document).filter(Document.id == document_id).first()
