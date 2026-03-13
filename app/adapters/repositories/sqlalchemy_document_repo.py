# ABOUTME: SQLAlchemy adapter for DocumentRepository port.
# ABOUTME: Delegates to DocumentQueryService and DocumentSoftDeleteService.

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.services.document_query_service import DocumentQueryService
from app.services.soft_delete_service import DocumentSoftDeleteService


class SQLAlchemyDocumentRepository:
    """Adapter bridging DocumentQueryService + DocumentSoftDeleteService to DocumentRepository protocol."""

    def __init__(
        self,
        query_service: DocumentQueryService | None = None,
        delete_service: DocumentSoftDeleteService | None = None,
    ):
        self._query = query_service or DocumentQueryService()
        self._delete = delete_service or DocumentSoftDeleteService()

    def get_document(
        self,
        db: Session,
        document_id: UUID,
        include_deleted: bool = False,
    ):
        return self._query.get_document(db, document_id, include_deleted=include_deleted)

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
    ):
        return self._query.list_documents(
            db,
            page=page,
            page_size=page_size,
            project_id=project_id,
            processed=processed,
            search=search,
            include_deleted=include_deleted,
        )

    def soft_delete_document(
        self,
        db: Session,
        document_id: UUID,
        deleted_by: str | None = None,
    ):
        return self._delete.soft_delete_document(db, document_id, deleted_by=deleted_by)

    def restore_document(self, db: Session, document_id: UUID):
        return self._delete.restore_document(db, document_id)
