"""Auto-ingest service for DeepSearch results.

Automatically ingests result_markdown from completed missions as documents,
linking them back to the mission and running through the chunking/embedding pipeline.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.mission import Mission
from app.services.document_ingestion import DocumentIngestionService
from app.services.ownership import project_owner_workspace
from app.services.processing_status import ProcessingStatusRecorder

logger = logging.getLogger(__name__)


class AutoIngestError(RuntimeError):
    """Raised when auto-ingestion fails."""


def is_document_search_ready(document: Document) -> bool:
    """Return the shared database-level readiness invariant for result search."""
    return bool(
        document.deleted_at is None
        and document.processed
        and document.chunked
        and document.embedded
    )


class AutoIngestService:
    """Service for automatically ingesting DeepSearch results as documents."""

    def __init__(
        self,
        ingestion_service: DocumentIngestionService | None = None,
        status_recorder: ProcessingStatusRecorder | None = None,
    ):
        self._ingestion_service = ingestion_service
        self._status_recorder = status_recorder or ProcessingStatusRecorder()

    def _get_ingestion_service(self) -> DocumentIngestionService:
        """Lazily initialize ingestion service."""
        if self._ingestion_service is None:
            self._ingestion_service = DocumentIngestionService()
        return self._ingestion_service

    @staticmethod
    def _document_for_id(db: Session, document_id: str) -> Document | None:
        """Resolve a linked result document, tolerating legacy invalid IDs."""
        try:
            parsed_id = UUID(str(document_id))
        except (TypeError, ValueError):
            return None
        return db.query(Document).filter(Document.id == parsed_id).first()

    def _find_existing_mission_document(
        self,
        db: Session,
        mission: Mission,
        filename: str,
    ) -> Document | None:
        """Find a linked or partially-created document for this mission/job."""
        for document_id in mission.result_document_ids or []:
            linked = self._document_for_id(db, document_id)
            if linked is not None:
                return linked

        candidates = (
            db.query(Document)
            .filter(
                Document.project_id == mission.project_id,
                Document.name == filename,
                Document.source_type == "deepsearch",
                Document.deleted_at.is_(None),
            )
            .order_by(Document.uploaded_at.desc())
            .all()
        )
        for document in candidates:
            metadata = document.document_metadata or {}
            same_mission = document.source_mission_id == mission.id or metadata.get(
                "mission_id"
            ) == mission.mission_id
            if not same_mission:
                continue
            recorded_job = metadata.get("deepsearch_job_id")
            if (
                recorded_job
                and mission.deepsearch_job_id
                and recorded_job != mission.deepsearch_job_id
            ):
                continue
            return document
        return None

    def auto_ingest_result(
        self,
        db: Session,
        mission: Mission,
        result_markdown: str,
        *,
        require_embedded: bool = False,
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
            require_embedded: Fail unless the returned document is search-ready.
                Result convergence enables this; legacy/manual callers may still
                accept a document when embeddings are intentionally disabled.

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

        existing_document = self._find_existing_mission_document(
            db, mission, filename
        )
        if mission.result_document_ids and existing_document is None:
            raise AutoIngestError(
                f"Mission {mission.mission_id} links a missing result document"
            )
        if existing_document is not None and existing_document.deleted_at is not None:
            raise AutoIngestError(
                f"Result document {existing_document.id} is soft-deleted and must be restored"
            )
        if (
            existing_document is not None
            and mission.result_document_ids
            and (not require_embedded or is_document_search_ready(existing_document))
        ):
            logger.info(
                "Result document %s is already linked to mission %s",
                existing_document.id,
                mission.mission_id,
            )
            return existing_document

        # Build metadata
        metadata: dict[str, Any] = {
            "mission_id": mission.mission_id,
            "auto_generated": True,
        }
        if mission.deepsearch_job_id:
            metadata["deepsearch_job_id"] = mission.deepsearch_job_id

        # Inherit owner/Space from the parent project (no human caller here) so the
        # auto-ingested doc is visible to the same principals as its project once
        # rbac_enabled flips (T48.4).
        owner_id, workspace_id = project_owner_workspace(db, mission.project_id)

        document = existing_document
        if document is None:
            # Create document record. source_mission_id gives retries a stable,
            # queryable identity even when the first pipeline attempt fails
            # before result_document_ids can be linked.
            document = Document(
                project_id=mission.project_id,
                name=filename,
                file_type="report",
                content=result_markdown,  # Store raw content directly
                file_size=len(result_markdown.encode("utf-8")),
                mime_type="text/markdown",
                source_type="deepsearch",
                document_metadata=metadata,
                source_mission_id=mission.id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                processed=False,
                chunked=False,
                embedded=False,
                validation_status="pending",
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            # Record document creation once. A retry resumes this same record.
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
        else:
            logger.info(
                "Resuming partial auto-ingest for mission %s with document %s",
                mission.mission_id,
                document.id,
            )

        # Process through ingestion pipeline
        try:
            ingestion_service = self._get_ingestion_service()

            # A fully chunked document only needs its missing mission link. This
            # avoids duplicating chunks when a prior attempt succeeded but died
            # between pipeline completion and the final mission update.
            if require_embedded and is_document_search_ready(document):
                result = {"status": "completed"}
            elif document.processed and document.chunked:
                if require_embedded:
                    result = ingestion_service.embed_existing_document(
                        db=db,
                        document_id=document.id,
                    )
                else:
                    result = {"status": "completed"}
            elif document.chunks:
                raise AutoIngestError(
                    f"Result document {document.id} has partial chunks; refusing "
                    "a replay that could duplicate them"
                )
            else:
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

            if require_embedded and not is_document_search_ready(document):
                raise AutoIngestError(
                    f"Result document {document.id} is not search-ready"
                )

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
        if str(document.id) not in current_doc_ids:
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
_service: AutoIngestService | None = None


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
