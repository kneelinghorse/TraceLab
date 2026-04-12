"""
Utility to record document processing status events.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.processing_status import DocumentProcessingStatus


class ProcessingStatusRecorder:
    """Helper for persisting ingestion stage audit events."""

    def record(
        self,
        db: Session,
        document_id: UUID,
        stage: str,
        status: str,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> DocumentProcessingStatus:
        """
        Persist a processing status entry to the database.

        Args:
            db: Active database session.
            document_id: Document being processed.
            stage: Processing stage name (uploaded, extracted, redacted, chunked, pipeline).
            status: Status value (in_progress, succeeded, failed).
            message: Optional descriptive message.
            details: Optional structured metadata.
            commit: When True, commits the session after inserting.

        Returns:
            The persisted DocumentProcessingStatus instance.
        """
        entry = DocumentProcessingStatus(
            document_id=document_id,
            stage=stage,
            status=status,
            message=message,
            details=details or {},
        )
        db.add(entry)
        if commit:
            db.commit()
        else:
            db.flush()
        return entry
