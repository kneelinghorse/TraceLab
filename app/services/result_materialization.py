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
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Integer,
    and_,
    case,
    func,
    literal,
    literal_column,
    or_,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.document import Document
from app.models.mission import Mission
from app.models.report import Report
from app.services.auto_ingest import (
    AUTO_INGEST_ERROR_CATEGORIES,
    AutoIngestError,
    AutoIngestService,
    is_document_search_ready,
)
from app.services.auto_report import (
    AUTO_REPORT_ERROR_CATEGORIES,
    AUTO_REPORT_PROMPT_PREFIX,
    LEGACY_AUTO_REPORT_CHECKPOINT_LINE,
    LEGACY_AUTO_REPORT_FOOTER_PREFIX,
    LEGACY_AUTO_REPORT_FOOTER_SUFFIX,
    LEGACY_AUTO_REPORT_HEADER_PREFIX,
    AutoReportError,
    AutoReportService,
    is_legacy_auto_generated_draft,
    protocol_uses_current_report_shape,
)

logger = logging.getLogger(__name__)

MAX_RECONCILE_BATCH = 500
MAX_RECONCILE_SCAN = 5000
MATERIALIZATION_INCOMPLETE = "materialization_incomplete"
UNEXPECTED_MATERIALIZATION_ERROR = "unexpected_materialization_error"
MATERIALIZATION_ERROR_CATEGORIES = frozenset(
    AUTO_INGEST_ERROR_CATEGORIES
    | AUTO_REPORT_ERROR_CATEGORIES
    | {MATERIALIZATION_INCOMPLETE, UNEXPECTED_MATERIALIZATION_ERROR}
)


def normalize_materialization_error_categories(errors: list[str]) -> list[str]:
    """Return bounded public categories for any materialization error list."""
    return [
        error
        if isinstance(error, str) and error in MATERIALIZATION_ERROR_CATEGORIES
        else UNEXPECTED_MATERIALIZATION_ERROR
        for error in errors
    ]


class DocumentMaterializationState(StrEnum):
    """Live document-side disposition for a stored mission result."""

    NEEDS = "needs"
    BLOCKED_TOMBSTONE = "blocked_tombstone"
    SATISFIED = "satisfied"


@dataclass
class MaterializationResult:
    """Outcome of one mission result materialization attempt."""

    document_id: UUID | None = None
    report_id: UUID | None = None
    document_blocked: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Return whether this attempt created or repaired a result artifact."""
        return self.document_id is not None or self.report_id is not None


@dataclass(frozen=True)
class ReconciliationSummary:
    """Bounded completed-mission reconciliation counts."""

    scanned: int
    eligible: int
    repaired: int
    failed: int
    skipped_soft_deleted: int


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
    def _unlinked_result_documents(
        db: Session,
        mission: Mission,
        linked_ids: set[UUID],
    ) -> list[Document]:
        """Return deleted DeepSearch results attributable but unlinked to a mission."""
        candidates = (
            db.query(Document)
            .filter(
                Document.project_id == mission.project_id,
                Document.source_type == "deepsearch",
                Document.deleted_at.is_not(None),
            )
            .all()
        )
        matches: list[Document] = []
        for document in candidates:
            if document.id in linked_ids:
                continue
            raw_metadata = document.document_metadata
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if (
                document.source_mission_id == mission.id
                or metadata.get("mission_id") == mission.mission_id
            ):
                matches.append(document)
        return matches

    @classmethod
    def document_materialization_state(
        cls,
        db: Session,
        mission: Mission,
    ) -> DocumentMaterializationState:
        """Classify the document side from live rows, never persisted retry state."""
        if not mission.result_markdown:
            return DocumentMaterializationState.SATISFIED
        if not mission.project_id:
            return DocumentMaterializationState.NEEDS

        needs_document = not bool(mission.result_document_ids)
        blocked_by_tombstone = False
        linked_ids: set[UUID] = set()
        for document_id in mission.result_document_ids or []:
            try:
                parsed_id = UUID(str(document_id))
            except (TypeError, ValueError):
                needs_document = True
                continue
            linked_ids.add(parsed_id)
            document = db.query(Document).filter(Document.id == parsed_id).first()
            if document is None:
                needs_document = True
            elif document.deleted_at is not None:
                blocked_by_tombstone = True
            elif not is_document_search_ready(document):
                needs_document = True

        unlinked_documents = cls._unlinked_result_documents(db, mission, linked_ids)
        if any(document.deleted_at is not None for document in unlinked_documents):
            blocked_by_tombstone = True

        if blocked_by_tombstone:
            return DocumentMaterializationState.BLOCKED_TOMBSTONE
        if needs_document:
            return DocumentMaterializationState.NEEDS
        return DocumentMaterializationState.SATISFIED

    @classmethod
    def needs_materialization(cls, db: Session, mission: Mission) -> bool:
        """Return whether stored results imply a missing document or report."""
        if not mission.project_id:
            return False
        needs_document = (
            cls.document_materialization_state(db, mission)
            is DocumentMaterializationState.NEEDS
        )
        needs_report = cls.report_needs_materialization(db, mission)
        return needs_document or needs_report

    @staticmethod
    def report_needs_materialization(db: Session, mission: Mission) -> bool:
        """Return whether a report is missing or an eligible v1 draft needs repair."""
        if not mission.result_protocol:
            return False
        if mission.result_report_id is None:
            return True

        report = db.get(Report, mission.result_report_id)
        if report is None:
            return True
        return protocol_uses_current_report_shape(
            mission.result_protocol
        ) and is_legacy_auto_generated_draft(report, mission)

    @staticmethod
    def report_repair_candidate_expression():
        """Return the SQL candidate matching the live v1 report predicate."""
        current_protocol_shape = or_(
            Mission.result_protocol["synthesis"]["key_insights"]
            .as_string()
            .is_not(None),
            Mission.result_protocol["synthesis"]["recommendations"]
            .as_string()
            .is_not(None),
        )
        expected_header = (
            literal(LEGACY_AUTO_REPORT_HEADER_PREFIX)
            + Mission.title
            + literal("\n\n")
        )
        legacy_auto_report = Mission.result_report.has(
            and_(
                Report.project_id == Mission.project_id,
                Report.report_type == "markdown",
                Report.status == "draft",
                Report.prompt
                == literal(AUTO_REPORT_PROMPT_PREFIX) + Mission.mission_id,
                func.substr(Report.content, 1, func.length(expected_header))
                == expected_header,
                Report.content.contains(LEGACY_AUTO_REPORT_CHECKPOINT_LINE),
                Report.content.contains(LEGACY_AUTO_REPORT_FOOTER_PREFIX),
                Report.content.endswith(LEGACY_AUTO_REPORT_FOOTER_SUFFIX),
            )
        )
        return and_(
            Mission.result_report_id.is_not(None),
            current_protocol_shape,
            legacy_auto_report,
        )

    @staticmethod
    def _advisory_lock_key(mission_id: UUID) -> int:
        """Map a mission UUID to PostgreSQL's signed 64-bit advisory key."""
        raw = int.from_bytes(mission_id.bytes[:8], "big") ^ int.from_bytes(
            mission_id.bytes[8:], "big"
        )
        return raw - (1 << 64) if raw >= (1 << 63) else raw

    @staticmethod
    def _invalidate_lock_connection(lock_connection: Connection) -> None:
        """Ensure a possibly advisory-locked physical session cannot be pooled."""
        try:
            lock_connection.rollback()
        except Exception:
            logger.exception("Failed to roll back materialization lock connection")
        try:
            lock_connection.invalidate()
            return
        except Exception:
            logger.exception("Failed to invalidate materialization lock connection")
        try:
            lock_connection.connection.driver_connection.close()
        except Exception:
            logger.exception("Failed to hard-close materialization lock connection")

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
        mission_id = mission.id
        lock_key = self._advisory_lock_key(mission_id)
        locked_db: Session | None = None
        lock_acquired = False
        unlock_failed = False
        mission_disappeared = False
        try:
            lock_connection.execute(text("SET lock_timeout = '5s'"))
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            lock_acquired = True
            lock_connection.commit()
            locked_db = Session(bind=lock_connection)
            locked_mission = (
                locked_db.query(Mission)
                .filter(Mission.id == mission_id)
                .one_or_none()
            )
            if locked_mission is None:
                mission_disappeared = True
                result = MaterializationResult()
            else:
                try:
                    result = self._materialize_locked(locked_db, locked_mission)
                except (InvalidRequestError, StaleDataError):
                    disappeared_after_reload = False
                    try:
                        locked_db.rollback()
                        disappeared_after_reload = (
                            locked_db.query(Mission.id)
                            .filter(Mission.id == mission_id)
                            .one_or_none()
                            is None
                        )
                    except Exception:
                        logger.exception(
                            "Failed to verify mission existence after materialization error"
                        )
                    if not disappeared_after_reload:
                        raise
                    mission_disappeared = True
                    result = MaterializationResult()
        finally:
            try:
                if locked_db is not None:
                    locked_db.close()
            except Exception:
                logger.exception("Failed to close mission materialization session")
            finally:
                try:
                    if lock_acquired:
                        unlocked = lock_connection.execute(
                            text("SELECT pg_advisory_unlock(:lock_key)"),
                            {"lock_key": lock_key},
                        ).scalar_one()
                        if unlocked is not True:
                            raise RuntimeError(
                                "Mission materialization advisory lock was not held"
                            )
                        lock_connection.commit()
                except Exception:
                    unlock_failed = True
                    logger.exception(
                        "Failed to release mission materialization advisory lock"
                    )
                finally:
                    try:
                        if unlock_failed:
                            self._invalidate_lock_connection(lock_connection)
                        else:
                            try:
                                lock_connection.rollback()
                                lock_connection.execute(text("RESET lock_timeout"))
                                lock_connection.commit()
                            except Exception:
                                logger.exception(
                                    "Failed to reset mission materialization lock timeout"
                                )
                                self._invalidate_lock_connection(lock_connection)
                    finally:
                        try:
                            lock_connection.close()
                        except Exception:
                            logger.exception(
                                "Failed to close mission materialization lock connection"
                            )

        if mission_disappeared:
            return result
        db.expire_all()
        if db.get(Mission, mission_id, populate_existing=True) is None:
            return MaterializationResult()
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

        document_state = self.document_materialization_state(db, mission)
        if document_state is DocumentMaterializationState.NEEDS:
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
                result.errors.append(exc.category)
                logger.warning(
                    "Result document materialization failed for mission %s: %s",
                    mission.mission_id,
                    exc,
                )
            except Exception:  # pragma: no cover - defensive service boundary
                db.rollback()
                result.errors.append("unexpected_ingest_error")
                logger.exception(
                    "Unexpected result document materialization error for mission %s",
                    mission.mission_id,
                )

        # Auto-ingest commits the mission link. Refresh so report source linking
        # observes it, including when this is a repair of a prior partial attempt.
        db.refresh(mission)
        if mission.result_protocol and self.report_needs_materialization(db, mission):
            try:
                if mission.result_report_id is None:
                    report = self._auto_report_service.create_report_from_protocol(
                        db=db,
                        mission=mission,
                        protocol=mission.result_protocol,
                    )
                else:
                    report = self._auto_report_service.repair_report_from_protocol(
                        db=db,
                        mission=mission,
                        protocol=mission.result_protocol,
                    )
                result.report_id = report.id
            except AutoReportError as exc:
                db.rollback()
                result.errors.append(exc.category)
                logger.warning(
                    "Result report materialization failed for mission %s: %s",
                    mission.mission_id,
                    exc,
                )
            except Exception:  # pragma: no cover - defensive service boundary
                db.rollback()
                result.errors.append("unexpected_report_error")
                logger.exception(
                    "Unexpected result report materialization error for mission %s",
                    mission.mission_id,
                )

        db.refresh(mission)
        document_state = self.document_materialization_state(db, mission)
        result.document_blocked = (
            document_state is DocumentMaterializationState.BLOCKED_TOMBSTONE
        )
        if not result.errors and self.needs_materialization(db, mission):
            result.errors.append(MATERIALIZATION_INCOMPLETE)
        result.errors = normalize_materialization_error_categories(result.errors)
        self._record_state(db, mission, result, document_state=document_state)
        return result

    @classmethod
    def _record_state(
        cls,
        db: Session,
        mission: Mission,
        result: MaterializationResult,
        *,
        document_state: DocumentMaterializationState | None = None,
    ) -> bool:
        """Persist category-only retry state, avoiding no-op mission commits."""
        metadata = dict(mission.execution_metadata or {})
        previous = metadata.get("result_materialization")
        previous_state = previous if isinstance(previous, dict) else {}
        raw_prior_attempts = previous_state.get("attempt_count", 0)
        prior_attempts = (
            raw_prior_attempts
            if isinstance(raw_prior_attempts, int)
            and not isinstance(raw_prior_attempts, bool)
            and raw_prior_attempts >= 0
            else 0
        )
        live_document_state = document_state or cls.document_materialization_state(
            db, mission
        )
        pending = (
            live_document_state is DocumentMaterializationState.NEEDS
            or cls.report_needs_materialization(db, mission)
        )
        if result.errors:
            status = "failed"
        elif live_document_state is DocumentMaterializationState.BLOCKED_TOMBSTONE:
            status = "blocked_soft_deleted"
        elif pending:
            status = "pending"
        else:
            status = "ready"

        error_categories = list(result.errors)
        expected_keys = {
            "status",
            "attempt_count",
            "attempted_at",
            "error_categories",
        }
        if (
            not result.changed
            and not result.errors
            and set(previous_state) == expected_keys
            and previous_state.get("status") == status
            and previous_state.get("error_categories") == error_categories
        ):
            return False

        metadata["result_materialization"] = {
            "status": status,
            "attempt_count": int(prior_attempts) + 1,
            "attempted_at": datetime.now(UTC).isoformat(),
            "error_categories": error_categories,
        }
        mission.execution_metadata = metadata
        db.commit()
        db.refresh(mission)
        return True

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
        skipped_soft_deleted = 0
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
            result_protocol_truthy = literal_column(
                """
                (
                    CASE jsonb_typeof(missions.result_protocol)
                        WHEN 'object' THEN missions.result_protocol <> '{}'::jsonb
                        WHEN 'array' THEN missions.result_protocol <> '[]'::jsonb
                        WHEN 'string' THEN missions.result_protocol <> '\"\"'::jsonb
                        WHEN 'boolean' THEN missions.result_protocol = 'true'::jsonb
                        WHEN 'number' THEN
                            (missions.result_protocol #>> '{}')::numeric <> 0
                        ELSE FALSE
                    END
                )
                """,
                type_=Boolean(),
            )
            settled_linked_documents = literal_column(
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
                    WHERE documents.deleted_at IS NOT NULL
                       OR (
                            documents.deleted_at IS NULL
                        AND documents.processed IS TRUE
                        AND documents.chunked IS TRUE
                        AND documents.embedded IS TRUE
                       )
                )
                """,
                type_=Integer(),
            )
            deleted_linked_documents = literal_column(
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
                    WHERE documents.deleted_at IS NOT NULL
                )
                """,
                type_=Integer(),
            )
            unlinked_deleted_documents = literal_column(
                """
                (
                    SELECT count(*)
                    FROM documents
                    WHERE documents.project_id = missions.project_id
                      AND documents.source_type = 'deepsearch'
                      AND documents.deleted_at IS NOT NULL
                      AND (
                            documents.source_mission_id = missions.id
                         OR documents.document_metadata ->> 'mission_id' = missions.mission_id
                      )
                      AND NOT EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(
                                CASE
                                    WHEN jsonb_typeof(missions.result_document_ids) = 'array'
                                    THEN missions.result_document_ids
                                    ELSE '[]'::jsonb
                                END
                            ) AS linked_result_id(value)
                            WHERE linked_result_id.value = documents.id::text
                      )
                )
                """,
                type_=Integer(),
            )
        else:
            result_ids_kind = func.json_type(Mission.result_document_ids)
            result_ids_array_length = func.json_array_length(
                Mission.result_document_ids
            )
            result_protocol_truthy = literal_column(
                """
                (
                    CASE json_type(missions.result_protocol)
                        WHEN 'object' THEN EXISTS (
                            SELECT 1 FROM json_each(missions.result_protocol)
                        )
                        WHEN 'array' THEN EXISTS (
                            SELECT 1 FROM json_each(missions.result_protocol)
                        )
                        WHEN 'text' THEN
                            json_extract(missions.result_protocol, '$') <> ''
                        WHEN 'integer' THEN
                            json_extract(missions.result_protocol, '$') <> 0
                        WHEN 'real' THEN
                            json_extract(missions.result_protocol, '$') <> 0
                        WHEN 'true' THEN 1
                        ELSE 0
                    END
                )
                """,
                type_=Boolean(),
            )
            settled_linked_documents = literal_column(
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
                    WHERE documents.deleted_at IS NOT NULL
                       OR (
                            documents.deleted_at IS NULL
                        AND documents.processed = 1
                        AND documents.chunked = 1
                        AND documents.embedded = 1
                       )
                )
                """,
                type_=Integer(),
            )
            deleted_linked_documents = literal_column(
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
                    WHERE documents.deleted_at IS NOT NULL
                )
                """,
                type_=Integer(),
            )
            unlinked_deleted_documents = literal_column(
                """
                (
                    SELECT count(*)
                    FROM documents
                    WHERE CAST(documents.project_id AS TEXT) = CAST(missions.project_id AS TEXT)
                      AND documents.source_type = 'deepsearch'
                      AND documents.deleted_at IS NOT NULL
                      AND (
                            CAST(documents.source_mission_id AS TEXT) = CAST(missions.id AS TEXT)
                         OR json_extract(documents.document_metadata, '$.mission_id') = missions.mission_id
                      )
                      AND NOT EXISTS (
                            SELECT 1
                            FROM json_each(
                                CASE
                                    WHEN json_type(missions.result_document_ids) = 'array'
                                    THEN missions.result_document_ids
                                    ELSE '[]'
                                END
                            ) AS linked_result_id
                            WHERE CAST(linked_result_id.value AS TEXT) = CAST(documents.id AS TEXT)
                      )
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
        has_linked_tombstone = deleted_linked_documents > 0
        has_unlinked_tombstone = unlinked_deleted_documents > 0
        has_tombstone = or_(has_linked_tombstone, has_unlinked_tombstone)
        no_tombstone = and_(
            deleted_linked_documents == 0,
            unlinked_deleted_documents == 0,
        )
        tombstone_disposition_candidate = and_(
            Mission.result_markdown.is_not(None),
            Mission.result_markdown != "",
            has_tombstone,
            or_(
                materialization_status.is_(None),
                materialization_status != "blocked_soft_deleted",
            ),
        )
        restored_disposition_candidate = and_(
            materialization_status == "blocked_soft_deleted",
            no_tombstone,
        )
        document_repair_candidate = and_(
            Mission.result_markdown.is_not(None),
            Mission.result_markdown != "",
            no_tombstone,
            or_(
                result_ids_length <= 0,
                result_ids_length != settled_linked_documents,
            ),
        )
        structural_candidate = or_(
            document_repair_candidate,
            tombstone_disposition_candidate,
            restored_disposition_candidate,
            and_(
                result_protocol_truthy,
                Mission.result_report_id.is_(None),
            ),
            self.report_repair_candidate_expression(),
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
                mission = (
                    db.query(Mission)
                    .filter(Mission.id == mission_id)
                    .one_or_none()
                )
                if mission is None:
                    continue
                outcome = self.materialize(db, mission)
                if (
                    outcome.document_blocked
                    and not outcome.changed
                    and not outcome.errors
                ):
                    skipped_soft_deleted += 1
                elif outcome.changed or outcome.errors:
                    eligible += 1
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
            skipped_soft_deleted=skipped_soft_deleted,
        )


def reconcile_completed_mission_results(
    db: Session,
    *,
    limit: int = 100,
) -> ReconciliationSummary:
    """CLI-callable convenience entry point for bounded result repair."""
    return MissionResultMaterializationService().reconcile_completed(db, limit=limit)
