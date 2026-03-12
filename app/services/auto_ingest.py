"""Auto-ingest service for DeepSearch results.

Automatically ingests result_markdown from completed missions as documents,
linking them back to the mission and running through the chunking/embedding pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.mission import Mission
from app.services.document_ingestion import DocumentIngestionService
from app.services.processing_status import ProcessingStatusRecorder

logger = logging.getLogger(__name__)


class AutoIngestError(RuntimeError):
    """Raised when auto-ingestion fails."""


class AutoIngestService:
    """Service for automatically ingesting DeepSearch results as documents."""

    def __init__(
        self,
        ingestion_service: Optional[DocumentIngestionService] = None,
        status_recorder: Optional[ProcessingStatusRecorder] = None,
    ):
        self._ingestion_service = ingestion_service
        self._status_recorder = status_recorder or ProcessingStatusRecorder()

    def _get_ingestion_service(self) -> DocumentIngestionService:
        """Lazily initialize ingestion service."""
        if self._ingestion_service is None:
            self._ingestion_service = DocumentIngestionService()
        return self._ingestion_service

    def auto_ingest_result(
        self,
        db: Session,
        mission: Mission,
        result_markdown: str,
    ) -> Document:
        """Ingest result_markdown as a document and link to mission.

        Creates a new document record with:
        - filename: {mission_id}_report.md
        - project_id: mission.project_id
        - source_type: "deepsearch"
        - metadata: {mission_id, deepsearch_job_id, auto_generated}

        Then runs the document through chunking and embedding.

        Args:
            db: Database session
            mission: The completed mission
            result_markdown: Markdown content to ingest

        Returns:
            The created Document with chunks

        Raises:
            AutoIngestError: If ingestion fails
        """
        if not result_markdown:
            raise AutoIngestError("No result_markdown to ingest")

        if not mission.project_id:
            raise AutoIngestError(f"Mission {mission.mission_id} has no project_id")

        # Create document filename
        filename = f"{mission.mission_id}_report.md"

        logger.info(
            "Auto-ingesting result for mission %s as document %s",
            mission.mission_id,
            filename,
        )

        # Build metadata
        metadata: Dict[str, Any] = {
            "mission_id": mission.mission_id,
            "auto_generated": True,
        }
        if mission.deepsearch_job_id:
            metadata["deepsearch_job_id"] = mission.deepsearch_job_id

        # Create document record
        document = Document(
            project_id=mission.project_id,
            name=filename,
            file_type="report",
            content=result_markdown,  # Store raw content directly
            file_size=len(result_markdown.encode("utf-8")),
            mime_type="text/markdown",
            source_type="deepsearch",
            document_metadata=metadata,
            processed=False,
            chunked=False,
            embedded=False,
            validation_status="pending",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Record document creation
        self._status_recorder.record(
            db,
            document.id,
            stage="uploaded",
            status="succeeded",
            details={
                "file_name": filename,
                "file_size_bytes": document.file_size,
                "mime_type": "text/markdown",
                "source_type": "deepsearch",
                "auto_ingested": True,
                "mission_id": mission.mission_id,
            },
        )

        # Process through ingestion pipeline
        try:
            ingestion_service = self._get_ingestion_service()

            # Pass content as bytes for processing
            result = ingestion_service.process_document(
                db=db,
                document_id=document.id,
                file_content=result_markdown.encode("utf-8"),
            )

            if result.get("status") == "failed":
                error = result.get("error", "Unknown ingestion error")
                logger.error(
                    "Ingestion failed for document %s: %s",
                    document.id,
                    error,
                )
                raise AutoIngestError(f"Ingestion failed: {error}")

            # Refresh document to get updated state
            db.refresh(document)

            logger.info(
                "Successfully auto-ingested document %s with %d chunks",
                document.id,
                len(document.chunks) if document.chunks else 0,
            )

        except AutoIngestError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during auto-ingestion")
            raise AutoIngestError(f"Ingestion error: {str(exc)}") from exc

        # Update mission with document reference
        current_doc_ids = list(mission.result_document_ids or [])
        current_doc_ids.append(str(document.id))
        mission.result_document_ids = current_doc_ids
        db.commit()

        logger.info(
            "Linked document %s to mission %s",
            document.id,
            mission.mission_id,
        )

        return document


# Module-level singleton
_service: Optional[AutoIngestService] = None


def get_auto_ingest_service() -> AutoIngestService:
    """Get or create the auto-ingest service instance."""
    global _service
    if _service is None:
        _service = AutoIngestService()
    return _service


async def auto_ingest_result(
    db: Session,
    mission: Mission,
    result_markdown: str,
) -> Document:
    """Convenience function for auto-ingesting results.

    This is the main entry point for the auto-ingest feature.

    Args:
        db: Database session
        mission: The completed mission
        result_markdown: Markdown content to ingest

    Returns:
        The created Document
    """
    service = get_auto_ingest_service()
    return service.auto_ingest_result(db, mission, result_markdown)
