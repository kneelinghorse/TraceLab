"""Report promotion service for promoting reports to searchable documents.

Promotes synthesized reports to full documents, closing the knowledge loop
so research findings feed back into future searches.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.mission import Mission
from app.models.report import Report
from app.services.document_ingestion import DocumentIngestionService
from app.services.processing_status import ProcessingStatusRecorder

logger = logging.getLogger(__name__)


class ReportPromotionError(RuntimeError):
    """Raised when report promotion fails."""


class ReportAlreadyPromotedError(ReportPromotionError):
    """Raised when a report has already been promoted to a document."""

    def __init__(self, report_id: UUID, document_id: UUID):
        self.report_id = report_id
        self.document_id = document_id
        super().__init__(f"Report {report_id} already promoted to document {document_id}")


class ReportPromotionService:
    """Service for promoting reports to searchable documents."""

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

    def check_already_promoted(self, db: Session, report_id: UUID) -> Optional[Document]:
        """Check if a report has already been promoted to a document.

        Args:
            db: Database session
            report_id: UUID of the report to check

        Returns:
            The existing Document if already promoted, None otherwise
        """
        return (
            db.query(Document)
            .filter(Document.source_report_id == report_id)
            .first()
        )

    def promote_report(
        self,
        db: Session,
        mission: Mission,
        report: Report,
    ) -> Document:
        """Promote a report to a searchable document.

        Creates a new document record from the report content and runs it
        through the chunking/embedding pipeline.

        Args:
            db: Database session
            mission: The mission that owns the report
            report: The report to promote

        Returns:
            The created Document with chunks

        Raises:
            ReportAlreadyPromotedError: If report was already promoted
            ReportPromotionError: If promotion fails
        """
        # Check for existing promotion
        existing = self.check_already_promoted(db, report.id)
        if existing:
            raise ReportAlreadyPromotedError(report.id, existing.id)

        if not report.content:
            raise ReportPromotionError("Report has no content to promote")

        if not mission.project_id:
            raise ReportPromotionError(f"Mission {mission.mission_id} has no project_id")

        # Create document name from report title
        doc_name = f"{report.title}.md"

        logger.info(
            "Promoting report %s from mission %s as document %s",
            report.id,
            mission.mission_id,
            doc_name,
        )

        # Build metadata
        metadata: Dict[str, Any] = {
            "mission_id": mission.mission_id,
            "report_id": str(report.id),
            "report_title": report.title,
            "report_type": report.report_type,
            "promoted_from_report": True,
        }
        if mission.deepsearch_job_id:
            metadata["deepsearch_job_id"] = mission.deepsearch_job_id

        # Create document record with provenance
        document = Document(
            project_id=mission.project_id,
            name=doc_name,
            file_type="report",
            content=report.content,
            file_size=len(report.content.encode("utf-8")),
            mime_type="text/markdown",
            source_type="analysis",
            document_metadata=metadata,
            # Provenance tracking
            source_report_id=report.id,
            source_mission_id=mission.id,
            source_origin="synthesized",
            # Processing status
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
                "file_name": doc_name,
                "file_size_bytes": document.file_size,
                "mime_type": "text/markdown",
                "source_origin": "synthesized",
                "promoted_from_report": True,
                "report_id": str(report.id),
                "mission_id": mission.mission_id,
            },
        )

        # Process through ingestion pipeline (chunking + embedding)
        try:
            ingestion_service = self._get_ingestion_service()

            result = ingestion_service.process_document(
                db=db,
                document_id=document.id,
                file_content=report.content.encode("utf-8"),
            )

            if result.get("status") == "failed":
                error = result.get("error", "Unknown ingestion error")
                logger.error(
                    "Ingestion failed for promoted document %s: %s",
                    document.id,
                    error,
                )
                raise ReportPromotionError(f"Document processing failed: {error}")

            db.refresh(document)

            logger.info(
                "Successfully promoted report %s to document %s with %d chunks",
                report.id,
                document.id,
                len(document.chunks) if document.chunks else 0,
            )

        except ReportPromotionError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during report promotion")
            raise ReportPromotionError(f"Promotion error: {str(exc)}") from exc

        # Update mission with document reference if not already present
        current_doc_ids = mission.result_document_ids or []
        doc_id_str = str(document.id)
        if doc_id_str not in current_doc_ids:
            current_doc_ids.append(doc_id_str)
            mission.result_document_ids = current_doc_ids
            db.commit()

            logger.info(
                "Linked promoted document %s to mission %s",
                document.id,
                mission.mission_id,
            )

        return document


# Module-level singleton
_service: Optional[ReportPromotionService] = None


def get_report_promotion_service() -> ReportPromotionService:
    """Get or create the report promotion service instance."""
    global _service
    if _service is None:
        _service = ReportPromotionService()
    return _service


def promote_report(
    db: Session,
    mission: Mission,
    report: Report,
) -> Document:
    """Convenience function for promoting a report to a document.

    This is the main entry point for the report promotion feature.

    Args:
        db: Database session
        mission: The mission that owns the report
        report: The report to promote

    Returns:
        The created Document
    """
    service = get_report_promotion_service()
    return service.promote_report(db, mission, report)
