"""Report promotion service for converting reports to searchable documents.

Promotes mission reports to documents, running them through the chunking/embedding
pipeline so synthesized research feeds back into future searches.
"""
from __future__ import annotations

import logging
from typing import Optional
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
    """Raised when attempting to promote an already-promoted report."""


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

    def promote_report(
        self,
        db: Session,
        mission: Mission,
        report: Report,
    ) -> Document:
        """Promote a report to a searchable document.

        Creates a new document from the report's content and runs it through
        the chunking and embedding pipeline.

        Args:
            db: Database session
            mission: The completed mission with the report
            report: The report to promote

        Returns:
            The created Document with chunks

        Raises:
            ReportPromotionError: If promotion fails
            ReportAlreadyPromotedError: If report was already promoted
        """
        if not report.content:
            raise ReportPromotionError("Report has no content to promote")

        if not mission.project_id:
            raise ReportPromotionError(
                f"Mission {mission.mission_id} has no project_id"
            )

        # Check if report has already been promoted
        existing_doc = (
            db.query(Document)
            .filter(Document.source_report_id == report.id)
            .first()
        )
        if existing_doc:
            raise ReportAlreadyPromotedError(
                f"Report {report.id} has already been promoted to document {existing_doc.id}"
            )

        # Create document name from mission title and report (must end in .md for parser)
        document_name = f"{mission.title} - Report.md"

        logger.info(
            "Promoting report %s from mission %s as document '%s'",
            report.id,
            mission.mission_id,
            document_name,
        )

        # Create document record with provenance fields
        document = Document(
            project_id=mission.project_id,
            name=document_name,
            file_type="report",
            content=report.content,
            file_size=len(report.content.encode("utf-8")),
            mime_type="text/markdown",
            source_type="analysis",
            source_origin="synthesized",
            source_report_id=report.id,
            source_mission_id=mission.id,
            document_metadata={
                "mission_id": mission.mission_id,
                "report_id": str(report.id),
                "report_title": report.title,
                "promoted": True,
            },
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
                "file_name": document_name,
                "file_size_bytes": document.file_size,
                "mime_type": "text/markdown",
                "source_type": "analysis",
                "source_origin": "synthesized",
                "promoted_from_report": str(report.id),
                "mission_id": mission.mission_id,
            },
        )

        # Process through ingestion pipeline
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
                raise ReportPromotionError(f"Ingestion failed: {error}")

            db.refresh(document)

            # Update mission with promoted document ID
            current_doc_ids = mission.result_document_ids or []
            if str(document.id) not in current_doc_ids:
                current_doc_ids.append(str(document.id))
                mission.result_document_ids = current_doc_ids
                db.commit()

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
            raise ReportPromotionError(
                f"Promotion error: {str(exc)}"
            ) from exc

        return document

    def promote_markdown(
        self,
        db: Session,
        mission: Mission,
    ) -> Document:
        """Promote a mission's result_markdown directly to a searchable document.

        Creates a new document from the mission's result_markdown and runs it through
        the chunking and embedding pipeline.

        Args:
            db: Database session
            mission: The completed mission with result_markdown

        Returns:
            The created Document with chunks

        Raises:
            ReportPromotionError: If promotion fails
            ReportAlreadyPromotedError: If markdown was already promoted
        """
        if not mission.result_markdown:
            raise ReportPromotionError("Mission has no result_markdown to promote")

        if not mission.project_id:
            raise ReportPromotionError(
                f"Mission {mission.mission_id} has no project_id"
            )

        # Check if mission markdown has already been promoted
        existing_doc = (
            db.query(Document)
            .filter(Document.source_mission_id == mission.id)
            .first()
        )
        if existing_doc:
            raise ReportAlreadyPromotedError(
                f"Mission {mission.mission_id} has already been promoted to document {existing_doc.id}"
            )

        # Create document name from mission title (must end in .md for parser)
        document_name = f"{mission.title} - DeepSearch Results.md"

        logger.info(
            "Promoting result_markdown from mission %s as document '%s'",
            mission.mission_id,
            document_name,
        )

        # Create document record with provenance fields
        document = Document(
            project_id=mission.project_id,
            name=document_name,
            file_type="markdown",
            content=mission.result_markdown,
            file_size=len(mission.result_markdown.encode("utf-8")),
            mime_type="text/markdown",
            source_type="analysis",
            source_origin="synthesized",
            source_mission_id=mission.id,
            document_metadata={
                "mission_id": mission.mission_id,
                "promoted_from": "result_markdown",
                "promoted": True,
            },
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
                "file_name": document_name,
                "file_size_bytes": document.file_size,
                "mime_type": "text/markdown",
                "source_type": "analysis",
                "source_origin": "synthesized",
                "promoted_from": "result_markdown",
                "mission_id": mission.mission_id,
            },
        )

        # Process through ingestion pipeline
        try:
            ingestion_service = self._get_ingestion_service()

            result = ingestion_service.process_document(
                db=db,
                document_id=document.id,
                file_content=mission.result_markdown.encode("utf-8"),
            )

            if result.get("status") == "failed":
                error = result.get("error", "Unknown ingestion error")
                logger.error(
                    "Ingestion failed for promoted document %s: %s",
                    document.id,
                    error,
                )
                raise ReportPromotionError(f"Ingestion failed: {error}")

            db.refresh(document)

            # Update mission with promoted document ID
            current_doc_ids = mission.result_document_ids or []
            if str(document.id) not in current_doc_ids:
                current_doc_ids.append(str(document.id))
                mission.result_document_ids = current_doc_ids
                db.commit()

            logger.info(
                "Successfully promoted result_markdown from mission %s to document %s with %d chunks",
                mission.mission_id,
                document.id,
                len(document.chunks) if document.chunks else 0,
            )

        except ReportPromotionError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during markdown promotion")
            raise ReportPromotionError(
                f"Promotion error: {str(exc)}"
            ) from exc

        return document


# Module-level singleton
_service: Optional[ReportPromotionService] = None


def get_report_promotion_service() -> ReportPromotionService:
    """Get or create the report promotion service instance."""
    global _service
    if _service is None:
        _service = ReportPromotionService()
    return _service


def promote_mission_report(
    db: Session,
    mission: Mission,
    report: Report,
) -> Document:
    """Convenience function for promoting a mission report.

    Args:
        db: Database session
        mission: The completed mission
        report: The report to promote

    Returns:
        The created Document
    """
    service = get_report_promotion_service()
    return service.promote_report(db, mission, report)
