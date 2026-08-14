"""Idempotent materialization of persisted DeepSearch mission results.

DeepSearch may persist terminal mission results directly in PostgreSQL before
TraceLab receives the completion webhook.  This service makes the webhook and
an operator-invoked reconciliation scan converge on the same document/report
materialization path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Integer, and_, case, func, literal_column, or_, text
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.mission import Mission
from app.services.auto_ingest import (
    AutoIngestError,
    AutoIngestService,
    is_document_search_ready,
)
from app.services.auto_report import AutoReportError, AutoReportService

logger = logging.getLogger(__name__)

MAX_RECONCILE_BATCH = 500
MAX_RECONCILE_SCAN = 5000


@dataclass
class MaterializationResult:
    """Outcome of one mission result materialization attempt."""

    document_id: UUID | None = None
    report_id: UUID | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Return whether this attempt linked a missing result artifact."""
        return self.document_id is not None or self.report_id is not None


@dataclass(frozen=True)
class ReconciliationSummary:
    """Bounded completed-mission reconciliation counts."""

    scanned: int
    eligible: int
    repaired: int
    failed: int


class MissionResultMaterializationService:
    """Create missing TraceLab artifacts from results already on a mission."""

    def __init__(
        self,
        auto_ingest_service: AutoIngestService | None = None,
        auto_report_service: AutoReportService | None = None,
    ) -> None:
        self._auto_ingest_service = auto_ingest_service or AutoIngestService()
        self._auto_report_service = auto_report_service or AutoReportService()

    @staticmethod
    def _document_needs_materialization(db: Session, mission: Mission) -> bool:
        """Return whether the mission lacks a linked, search-ready document."""
        if not mission.result_markdown:
            return False
        if not mission.result_document_ids:
            return True
        for document_id in mission.result_document_ids:
            try:
                parsed_id = UUID(str(document_id))
            except (TypeError, ValueError):
                return True
            document = db.query(Document).filter(Document.id == parsed_id).first()
            if document is None or not is_document_search_ready(document):
                return True
        return False

    @classmethod
    def needs_materialization(cls, db: Session, mission: Mission) -> bool:
        """Return whether stored results imply a missing document or report."""
        if not mission.project_id:
            return False
        needs_document = cls._document_needs_materialization(db, mission)
        needs_report = bool(mission.result_protocol) and mission.result_report_id is None
        return needs_document or needs_report

    @staticmethod
    def _advisory_lock_key(mission_id: UUID) -> int:
        """Map a mission UUID to PostgreSQL's signed 64-bit advisory key."""
        raw = int.from_bytes(mission_id.bytes[:8], "big") ^ int.from_bytes(
            mission_id.bytes[8:], "big"
        )
        return raw - (1 << 64) if raw >= (1 << 63) else raw

    def materialize(self, db: Session, mission: Mission) -> MaterializationResult:
        """Serialize and materialize one mission's stored terminal result.

        PostgreSQL uses a session advisory lock held on a dedicated connection.
        That lock survives the ingestion/report services' internal commits, so a
        receipt and reconciler cannot both create artifacts for the same mission.
        """
        bind = db.get_bind()
        if bind.dialect.name != "postgresql":
            return self._materialize_locked(db, mission)

        engine = bind.engine
        lock_connection = engine.connect()
        lock_key = self._advisory_lock_key(mission.id)
        locked_db: Session | None = None
        try:
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            lock_connection.commit()
            locked_db = Session(bind=lock_connection)
            locked_mission = (
                locked_db.query(Mission).filter(Mission.id == mission.id).one()
            )
            result = self._materialize_locked(locked_db, locked_mission)
        finally:
            if locked_db is not None:
                locked_db.close()
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            )
            lock_connection.commit()
            lock_connection.close()

        db.expire_all()
        db.refresh(mission)
        return result

    def _materialize_locked(
        self,
        db: Session,
        mission: Mission,
    ) -> MaterializationResult:
        """Materialize only artifacts not already linked to ``mission``.

        Stored mission fields are authoritative.  Callers may safely replay this
        method because an existing result_document_ids/result_report_id link is
        never promoted a second time.
        """
        result = MaterializationResult()
        if not mission.project_id:
            return result

        if self._document_needs_materialization(db, mission):
            try:
                document = self._auto_ingest_service.auto_ingest_result(
                    db=db,
                    mission=mission,
                    result_markdown=mission.result_markdown,
                    require_embedded=True,
                )
                result.document_id = document.id
            except AutoIngestError as exc:
                db.rollback()
                result.errors.append(f"document: {exc}")
                logger.warning(
                    "Result document materialization failed for mission %s: %s",
                    mission.mission_id,
                    exc,
                )
            except Exception as exc:  # pragma: no cover - defensive service boundary
                db.rollback()
                result.errors.append(f"document: {exc}")
                logger.exception(
                    "Unexpected result document materialization error for mission %s",
                    mission.mission_id,
                )

        # Auto-ingest commits the mission link. Refresh so report source linking
        # observes it, including when this is a repair of a prior partial attempt.
        db.refresh(mission)
        if mission.result_protocol and mission.result_report_id is None:
            try:
                report = self._auto_report_service.create_report_from_protocol(
                    db=db,
                    mission=mission,
                    protocol=mission.result_protocol,
                )
                result.report_id = report.id
            except AutoReportError as exc:
                db.rollback()
                result.errors.append(f"report: {exc}")
                logger.warning(
                    "Result report materialization failed for mission %s: %s",
                    mission.mission_id,
                    exc,
                )
            except Exception as exc:  # pragma: no cover - defensive service boundary
                db.rollback()
                result.errors.append(f"report: {exc}")
                logger.exception(
                    "Unexpected result report materialization error for mission %s",
                    mission.mission_id,
                )

        db.refresh(mission)
        if not result.errors and self.needs_materialization(db, mission):
            result.errors.append(
                "result materialization remains pending after the attempt; "
                "inspect linked document and report readiness"
            )
        self._record_state(db, mission, result)
        return result

    @classmethod
    def _record_state(
        cls,
        db: Session,
        mission: Mission,
        result: MaterializationResult,
    ) -> None:
        """Persist retry-visible state without adding another schema boundary."""
        metadata = dict(mission.execution_metadata or {})
        previous = metadata.get("result_materialization")
        prior_attempts = (
            previous.get("attempt_count", 0) if isinstance(previous, dict) else 0
        )
        pending = cls.needs_materialization(db, mission)
        metadata["result_materialization"] = {
            "status": "failed" if result.errors else "pending" if pending else "ready",
            "attempt_count": int(prior_attempts) + 1,
            "attempted_at": datetime.now(UTC).isoformat(),
            "errors": list(result.errors),
        }
        mission.execution_metadata = metadata
        db.commit()
        db.refresh(mission)

    def reconcile_completed(
        self,
        db: Session,
        *,
        limit: int = 100,
    ) -> ReconciliationSummary:
        """Repair a bounded batch of recently updated terminal-result missions.

        The operator CLI calls this without adding another HTTP/authentication
        surface. Repeated invocations are safe and artifact attempts are bounded
        to ``MAX_RECONCILE_BATCH``. Healthy rows do not consume that limit.
        """
        if not 1 <= limit <= MAX_RECONCILE_BATCH:
            raise ValueError(
                f"limit must be between 1 and {MAX_RECONCILE_BATCH}, got {limit}"
            )

        scanned = 0
        eligible = 0
        repaired = 0
        failed = 0
        page_size = min(max(limit, 25), MAX_RECONCILE_BATCH)
        scan_limit = min(MAX_RECONCILE_SCAN, max(limit * 10, page_size))
        scan_cutoff = datetime.now(UTC).replace(tzinfo=None)
        cursor_updated_at: datetime | None = None
        cursor_id: UUID | None = None
        dialect_name = db.get_bind().dialect.name
        if dialect_name == "postgresql":
            result_ids_kind = func.jsonb_typeof(Mission.result_document_ids)
            result_ids_array_length = func.jsonb_array_length(
                Mission.result_document_ids
            )
            result_protocol_kind = func.jsonb_typeof(Mission.result_protocol)
            ready_linked_documents = literal_column(
                """
                (
                    SELECT count(*)
                    FROM jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(missions.result_document_ids) = 'array'
                            THEN missions.result_document_ids
                            ELSE '[]'::jsonb
                        END
                    ) AS linked_result_id(value)
                    JOIN documents
                      ON documents.id::text = linked_result_id.value
                    WHERE documents.deleted_at IS NULL
                      AND documents.processed IS TRUE
                      AND documents.chunked IS TRUE
                      AND documents.embedded IS TRUE
                )
                """,
                type_=Integer(),
            )
        else:
            result_ids_kind = func.json_type(Mission.result_document_ids)
            result_ids_array_length = func.json_array_length(
                Mission.result_document_ids
            )
            result_protocol_kind = func.json_type(Mission.result_protocol)
            ready_linked_documents = literal_column(
                """
                (
                    SELECT count(*)
                    FROM json_each(
                        CASE
                            WHEN json_type(missions.result_document_ids) = 'array'
                            THEN missions.result_document_ids
                            ELSE '[]'
                        END
                    ) AS linked_result_id
                    JOIN documents
                      ON CAST(documents.id AS TEXT) = CAST(linked_result_id.value AS TEXT)
                    WHERE documents.deleted_at IS NULL
                      AND documents.processed = 1
                      AND documents.chunked = 1
                      AND documents.embedded = 1
                )
                """,
                type_=Integer(),
            )

        result_ids_length = case(
            (result_ids_kind == "array", result_ids_array_length),
            else_=-1,
        )
        materialization_status = Mission.execution_metadata[
            "result_materialization"
        ]["status"].as_string()
        structural_candidate = or_(
            and_(
                Mission.result_markdown.is_not(None),
                Mission.result_markdown != "",
                or_(
                    result_ids_length <= 0,
                    result_ids_length != ready_linked_documents,
                ),
            ),
            and_(
                result_protocol_kind.is_not(None),
                result_protocol_kind != "null",
                Mission.result_report_id.is_(None),
            ),
            materialization_status.in_(("pending", "failed")),
        )

        while eligible < limit and scanned < scan_limit:
            query = db.query(Mission.id, Mission.updated_at).filter(
                Mission.status.in_(("completed", "validation_failed")),
                Mission.project_id.is_not(None),
                Mission.updated_at <= scan_cutoff,
                structural_candidate,
            )
            if cursor_updated_at is not None and cursor_id is not None:
                query = query.filter(
                    or_(
                        Mission.updated_at > cursor_updated_at,
                        and_(
                            Mission.updated_at == cursor_updated_at,
                            Mission.id > cursor_id,
                        ),
                    )
                )
            mission_ids = (
                query.order_by(Mission.updated_at.asc(), Mission.id.asc())
                .limit(min(page_size, scan_limit - scanned))
                .all()
            )
            if not mission_ids:
                break
            for mission_id, observed_updated_at in mission_ids:
                cursor_updated_at = observed_updated_at
                cursor_id = mission_id
                scanned += 1
                mission = db.query(Mission).filter(Mission.id == mission_id).one()
                if not self.needs_materialization(db, mission):
                    continue
                eligible += 1
                outcome = self.materialize(db, mission)
                if outcome.changed and not outcome.errors:
                    repaired += 1
                if outcome.errors:
                    failed += 1
                if eligible >= limit:
                    break

        return ReconciliationSummary(
            scanned=scanned,
            eligible=eligible,
            repaired=repaired,
            failed=failed,
        )


def reconcile_completed_mission_results(
    db: Session,
    *,
    limit: int = 100,
) -> ReconciliationSummary:
    """CLI-callable convenience entry point for bounded result repair."""
    return MissionResultMaterializationService().reconcile_completed(db, limit=limit)
