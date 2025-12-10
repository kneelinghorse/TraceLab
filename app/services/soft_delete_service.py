"""Soft delete service for documents.

Includes PEDR cache invalidation on document state changes (B19.2).
"""
from __future__ import annotations

import logging
from typing import Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.pedr.cache import invalidate_pedr_cache

logger = logging.getLogger(__name__)


class DocumentSoftDeleteService:
    """Handles soft delete and restore operations for documents."""

    def soft_delete_document(
        self,
        db: Session,
        document_id: UUID,
        deleted_by: str = None,
    ) -> Optional[bool]:
        """Soft delete a document.

        Args:
            db: Database session
            document_id: UUID of document to delete
            deleted_by: Identifier of who performed the deletion

        Returns:
            None if document not found
            False if document already deleted
            True if successfully soft deleted
        """
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return None
        if document.is_deleted:
            return False

        document.soft_delete(deleted_by=deleted_by)
        db.commit()

        # Invalidate PEDR cache to remove deleted document from search results
        invalidated_count = invalidate_pedr_cache()
        if invalidated_count > 0:
            logger.info(
                "PEDR cache invalidated after document %s soft-delete (%d entries cleared)",
                document_id,
                invalidated_count,
            )

        return True

    def restore_document(
        self,
        db: Session,
        document_id: UUID,
    ) -> Optional[bool]:
        """Restore a soft-deleted document.

        Args:
            db: Database session
            document_id: UUID of document to restore

        Returns:
            None if document not found
            False if document is not deleted
            True if successfully restored
        """
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return None
        if not document.is_deleted:
            return False

        document.restore()
        db.commit()

        # Invalidate PEDR cache to include restored document in search results
        invalidated_count = invalidate_pedr_cache()
        if invalidated_count > 0:
            logger.info(
                "PEDR cache invalidated after document %s restore (%d entries cleared)",
                document_id,
                invalidated_count,
            )

        return True
