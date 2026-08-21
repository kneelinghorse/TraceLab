"""Report service for CRUD operations and synthesis integration."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.collection import CollectionItem
from app.models.report import Report, ReportSource
from app.services.synthesis import SynthesisService, get_synthesis_service

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class ReportService:
    """Service for creating, reading, updating, and deleting reports."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        synthesis_service: SynthesisService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._synthesis_service = synthesis_service

    @property
    def synthesis_service(self) -> SynthesisService:
        """Lazy-load synthesis service."""
        if self._synthesis_service is None:
            self._synthesis_service = get_synthesis_service()
        return self._synthesis_service

    def create_report(
        self,
        *,
        title: str,
        collection_id: UUID | None = None,
        chunk_ids: list[UUID] | None = None,
        project_id: UUID | None = None,
        prompt: str | None = None,
        output_format: Literal["summary", "report", "bullets", "markdown"] = "summary",
        owner_id: UUID | None = None,
        workspace_id: UUID | None = None,
        accessible_project_ids: list[UUID] | None = None,
    ) -> tuple[Report, list[dict[str, Any]]]:
        """Create a new report by synthesizing content.

        Args:
            title: Report title
            collection_id: UUID of collection to synthesize
            chunk_ids: List of chunk UUIDs to synthesize
            project_id: Optional project association
            prompt: Custom synthesis prompt
            output_format: Output format for synthesis
            owner_id: Creator (the caller) — resolved by the route and passed as a
                scalar UUID since this service opens its own session (T48.4 parity).
            workspace_id: Default Space — same rationale.
            accessible_project_ids: Projects the caller may read. ``None`` keeps
                the legacy unrestricted synthesis and source-snapshot path; an
                empty list produces an empty report without provider or cache use.

        Returns:
            Tuple of (Report object, list of citation dicts)

        Raises:
            ValueError: If neither collection_id nor chunk_ids provided
        """
        if not collection_id and not chunk_ids:
            raise ValueError("Either collection_id or chunk_ids must be provided.")

        # Perform synthesis. Omit the scope keyword on the unrestricted path so
        # legacy collaborators and cache identities retain their exact call shape.
        if accessible_project_ids == []:
            synthesis_result = SynthesisService._empty_result(
                include_effective_chunk_ids=True
            )
        elif accessible_project_ids is None:
            synthesis_result = self.synthesis_service.synthesize(
                collection_id=collection_id,
                chunk_ids=chunk_ids,
                prompt=prompt,
                output_format=output_format,
            )
        else:
            synthesis_result = self.synthesis_service.synthesize(
                collection_id=collection_id,
                chunk_ids=chunk_ids,
                prompt=prompt,
                output_format=output_format,
                accessible_project_ids=accessible_project_ids,
            )

        content = synthesis_result.get("content", "")
        citations = synthesis_result.get("citations", [])
        tokens_used = synthesis_result.get("tokens_used", 0)
        chunk_count = synthesis_result.get("chunk_count", 0)
        effective_chunk_ids = (
            [
                chunk_id if isinstance(chunk_id, UUID) else UUID(str(chunk_id))
                for chunk_id in synthesis_result.get("effective_chunk_ids", [])
            ]
            if accessible_project_ids is not None
            else None
        )

        # Compute content hash for dedup
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        session = self.session_factory()
        try:
            # Create report
            report = Report(
                project_id=str(project_id) if project_id else None,
                title=title,
                report_type=output_format,
                prompt=prompt,
                content=content,
                content_hash=content_hash,
                status="draft",
                tokens_used=tokens_used,
                chunk_count=chunk_count,
                owner_id=owner_id,
                workspace_id=workspace_id,
            )
            session.add(report)
            session.flush()

            # Record sources
            if collection_id:
                source = ReportSource(
                    report_id=report.id,
                    source_type="collection",
                    source_id=str(collection_id),
                )
                session.add(source)

                # Scoped synthesis has already resolved the authoritative subset.
                # Re-expanding the collection here would reintroduce foreign chunks.
                collection_chunks = (
                    self._get_collection_chunk_ids(session, collection_id)
                    if effective_chunk_ids is None
                    else effective_chunk_ids
                )
                for chunk_id in collection_chunks:
                    chunk_source = ReportSource(
                        report_id=report.id,
                        source_type="chunk",
                        source_id=str(chunk_id),
                    )
                    session.add(chunk_source)

            if chunk_ids:
                source_chunk_ids = (
                    chunk_ids if effective_chunk_ids is None else effective_chunk_ids
                )
                for chunk_id in source_chunk_ids:
                    source = ReportSource(
                        report_id=report.id,
                        source_type="chunk",
                        source_id=str(chunk_id),
                    )
                    session.add(source)

            session.commit()
            session.refresh(report)
            return report, citations

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_collection_chunk_ids(
        self, session: Session, collection_id: UUID
    ) -> list[UUID]:
        """Get all chunk IDs from a collection."""
        items = (
            session.query(CollectionItem)
            .filter(CollectionItem.collection_id == str(collection_id))
            .all()
        )
        return [UUID(str(item.chunk_id)) for item in items if item.chunk_id]

    def get_report(self, report_id: UUID) -> Report | None:
        """Get a report by ID with sources loaded."""
        session = self.session_factory()
        try:
            report = (
                session.query(Report).filter(Report.id == str(report_id)).one_or_none()
            )
            if report:
                # Force load sources relationship
                _ = report.sources
                session.expunge(report)
            return report
        finally:
            session.close()

    def list_reports(
        self,
        *,
        project_id: UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        access_filter=None,
    ) -> tuple[list[Report], int]:
        """List reports with optional filtering and pagination.

        ``access_filter`` (authorization.accessible_filter) is an optional RBAC
        row-filter applied before count + pagination (T47.3); it is a session-agnostic
        SQLAlchemy expression, so it is built from the request session in the route and
        applied here on this service's own session. None = no filtering.

        Returns:
            Tuple of (list of reports, total count)
        """
        session = self.session_factory()
        try:
            query = session.query(Report)

            if project_id:
                query = query.filter(Report.project_id == str(project_id))
            if status:
                query = query.filter(Report.status == status)
            if access_filter is not None:
                query = query.filter(access_filter)

            # Get total count
            total = query.count()

            # Apply ordering and pagination
            query = query.order_by(Report.created_at.desc())
            offset = (page - 1) * page_size
            reports = query.offset(offset).limit(page_size).all()

            # Expunge for use outside session
            for report in reports:
                session.expunge(report)

            return reports, total
        finally:
            session.close()

    def update_report(
        self,
        report_id: UUID,
        *,
        updates: dict[str, Any],
    ) -> Report | None:
        """Update report metadata.

        Args:
            report_id: Report UUID
            updates: Dict with title and/or status

        Returns:
            Updated report or None if not found
        """
        session = self.session_factory()
        try:
            report = (
                session.query(Report).filter(Report.id == str(report_id)).one_or_none()
            )
            if not report:
                return None

            if "title" in updates and updates["title"] is not None:
                report.title = updates["title"]
            if "status" in updates and updates["status"] is not None:
                report.status = updates["status"]

            report.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(report)
            session.expunge(report)
            return report

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_report(self, report_id: UUID) -> bool:
        """Delete a report and its sources.

        Returns:
            True if deleted, False if not found
        """
        session = self.session_factory()
        try:
            report = (
                session.query(Report).filter(Report.id == str(report_id)).one_or_none()
            )
            if not report:
                return False

            session.delete(report)
            session.commit()
            return True

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_report_service: ReportService | None = None


def get_report_service() -> ReportService:
    """Return the singleton report service instance."""
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service
