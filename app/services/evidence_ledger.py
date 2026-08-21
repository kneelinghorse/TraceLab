"""Persistence, search, and promotion operations for the evidence ledger."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import Counter
from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, literal_column, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerNote, LedgerSource
from app.models.report import Report, ReportSource
from app.schemas.evidence_ledger import CaptureRequest, NoteUpsertRequest
from app.services.report_promotion import ReportPromotionService

MCP_AGENT_ORIGIN = "mcp-agent"
logger = logging.getLogger(__name__)
_NOTE_IDENTITY_CONSTRAINT = "uq_ledger_notes_project_session_key"
_SOURCE_IDENTITY_CONSTRAINT = "uq_ledger_sources_project_url_hash"
_SQLITE_NOTE_IDENTITY_ERROR = (
    "UNIQUE constraint failed: ledger_notes.project_id, ledger_notes.session_key, ledger_notes.note_key"
)
_SEARCH_VECTOR_SQL = """
to_tsvector(
    'english'::regconfig,
    COALESCE(ledger_entries.claim, ''::text) || ' '::text ||
    COALESCE(ledger_entries.summary, ''::text) || ' '::text ||
    COALESCE(ledger_entries.source_url, ''::text) || ' '::text ||
    COALESCE(ledger_entries.snippet, ''::text) || ' '::text ||
    COALESCE(ledger_entries.query, ''::text)
)
""".strip()
_DISPOSITION_GROUPS = (
    ("supporting", "Supporting"),
    ("contradicting", "Contradicting"),
    ("background", "Background"),
    ("rejected", "Rejected"),
)


def _is_note_identity_conflict(error: IntegrityError) -> bool:
    """Return whether an integrity failure is the keyed-note insert race."""
    diagnostic = getattr(error.orig, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == _NOTE_IDENTITY_CONSTRAINT:
        return True
    return _SQLITE_NOTE_IDENTITY_ERROR in str(error.orig)


def _apply_access_filter(query: Query, access_filter: Any | None) -> Query:
    if access_filter is not None:
        return query.filter(access_filter)
    return query


def _apply_project_scope(
    query: Query,
    model: type[LedgerEntry] | type[LedgerNote],
    allowed_project_ids: list[UUID] | None,
) -> Query:
    """Compose the request-local project scope without replacing row RBAC."""
    if allowed_project_ids is not None:
        return query.filter(model.project_id.in_(allowed_project_ids))
    return query


def _source_url_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so the keyword is always interpreted literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _append_optional_markdown(
    lines: list[str],
    label: str,
    value: str | None,
) -> None:
    if value:
        lines.extend((f"- **{label}:** {value}",))


def _render_markdown(
    session_key: str,
    entries: Sequence[LedgerEntry],
    notes: Sequence[LedgerNote],
) -> str:
    """Render a stable report that preserves every disposition and note."""
    lines = ["# Evidence Ledger", "", f"**Session:** `{session_key}`", ""]
    ordinal = 1
    for disposition, heading in _DISPOSITION_GROUPS:
        lines.extend((f"## {heading}", ""))
        grouped = [entry for entry in entries if entry.disposition == disposition]
        if not grouped:
            lines.extend(("_No entries._", ""))
            continue
        for entry in grouped:
            lines.extend(
                (
                    f"### Evidence {ordinal}",
                    "",
                    f"- **Claim:** {entry.claim}",
                    f"- **Disposition:** `{entry.disposition}`",
                    f"- **Origin:** `{entry.origin}`",
                    f"- **Source:** {entry.source_url}",
                )
            )
            _append_optional_markdown(lines, "Summary", entry.summary)
            _append_optional_markdown(lines, "Query", entry.query)
            _append_optional_markdown(lines, "Snippet", entry.snippet)
            if entry.mission_id:
                lines.append(f"- **Mission:** `{entry.mission_id}`")
            if entry.tags:
                lines.append("- **Tags:** " + ", ".join(f"`{tag}`" for tag in entry.tags))
            lines.append("")
            ordinal += 1

    lines.extend(("## Working Notes", ""))
    if not notes:
        lines.extend(("_No notes._", ""))
    for note in notes:
        lines.extend(
            (
                f"### {note.note_key}",
                "",
                note.content,
                "",
                f"- **Origin:** `{note.origin}`",
            )
        )
        if note.mission_id:
            lines.append(f"- **Mission:** `{note.mission_id}`")
        if note.tags:
            lines.append("- **Tags:** " + ", ".join(f"`{tag}`" for tag in note.tags))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


class EvidenceLedgerService:
    """Request-session service for evidence ledger operations."""

    def __init__(self, promotion_service: ReportPromotionService | None = None):
        self._promotion_service = promotion_service or ReportPromotionService()

    def capture(
        self,
        db: Session,
        request: CaptureRequest,
        *,
        owner_id: UUID,
        workspace_id: UUID | None,
    ) -> list[LedgerEntry]:
        """Persist a capture batch atomically."""
        source_urls = [str(item.source_url) for item in request.entries]
        try:
            sources = self._upsert_sources(
                db,
                project_id=request.project_id,
                sightings=Counter(source_urls),
            )
            entries = [
                LedgerEntry(
                    project_id=request.project_id,
                    mission_id=request.mission_id,
                    session_key=request.session_key,
                    origin=MCP_AGENT_ORIGIN,
                    claim=item.claim,
                    summary=item.summary,
                    source_url=source_url,
                    source_id=sources[source_url].id,
                    source=sources[source_url],
                    snippet=item.snippet,
                    query=item.query,
                    disposition=item.disposition,
                    tags=list(item.tags),
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                )
                for item, source_url in zip(
                    request.entries,
                    source_urls,
                    strict=True,
                )
            ]
            db.add_all(entries)
            db.commit()
        except Exception:
            db.rollback()
            raise
        for entry in entries:
            db.refresh(entry)
        return entries

    def _upsert_sources(
        self,
        db: Session,
        *,
        project_id: UUID,
        sightings: Counter[str],
    ) -> dict[str, LedgerSource]:
        """Increment project-local source sightings and resolve their rows."""
        urls_by_hash: dict[str, str] = {}
        source_values: list[dict[str, object]] = []
        ordered_sightings = sorted(
            (
                _source_url_hash(source_url),
                source_url,
                sighting_count,
            )
            for source_url, sighting_count in sightings.items()
        )
        for source_url_hash, source_url, sighting_count in ordered_sightings:
            existing_url = urls_by_hash.setdefault(source_url_hash, source_url)
            if existing_url != source_url:
                raise RuntimeError(
                    f"Ledger source hash collision within capture batch: {existing_url!r} and {source_url!r}"
                )
            source_values.append(
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "source_url": source_url,
                    "source_url_hash": source_url_hash,
                    "sighting_count": sighting_count,
                }
            )

        dialect_name = db.get_bind().dialect.name
        if dialect_name == "postgresql":
            pg_statement = postgresql_insert(LedgerSource).values(source_values)
            pg_statement = pg_statement.on_conflict_do_update(
                constraint=_SOURCE_IDENTITY_CONSTRAINT,
                set_={
                    "sighting_count": (LedgerSource.sighting_count + pg_statement.excluded.sighting_count),
                    "last_seen_at": func.greatest(
                        LedgerSource.last_seen_at,
                        func.statement_timestamp(),
                    ),
                },
            )
            db.execute(pg_statement)
        elif dialect_name == "sqlite":
            sqlite_statement = sqlite_insert(LedgerSource).values(source_values)
            sqlite_statement = sqlite_statement.on_conflict_do_update(
                index_elements=[
                    LedgerSource.project_id,
                    LedgerSource.source_url_hash,
                ],
                set_={
                    "sighting_count": (LedgerSource.sighting_count + sqlite_statement.excluded.sighting_count),
                    "last_seen_at": func.max(
                        LedgerSource.last_seen_at,
                        func.current_timestamp(),
                    ),
                },
            )
            db.execute(sqlite_statement)
        else:
            raise RuntimeError(f"Evidence source upsert does not support {dialect_name!r}")

        resolved_sources: list[LedgerSource] = (
            db.query(LedgerSource)
            .filter(
                LedgerSource.project_id == project_id,
                LedgerSource.source_url_hash.in_(urls_by_hash),
            )
            .populate_existing()
            .all()
        )
        sources_by_url: dict[str, LedgerSource] = {}
        sources_by_hash = {cast(str, source.source_url_hash): source for source in resolved_sources}
        for source_url_hash, source_url in urls_by_hash.items():
            source = sources_by_hash.get(source_url_hash)
            if source is None:
                raise RuntimeError(
                    f"Ledger source upsert did not resolve hash {source_url_hash} for project {project_id}"
                )
            if source.source_url != source_url:
                raise RuntimeError(
                    f"Ledger source hash collision for project {project_id}: {source.source_url!r} and {source_url!r}"
                )
            sources_by_url[source_url] = source
        return sources_by_url

    def upsert_note(
        self,
        db: Session,
        note_key: str,
        request: NoteUpsertRequest,
        *,
        owner_id: UUID,
        workspace_id: UUID | None,
    ) -> LedgerNote:
        """Create or replace a note identified by project/session/key."""
        retried_identity_conflict = False
        while True:
            note = (
                db.query(LedgerNote)
                .filter(
                    LedgerNote.project_id == request.project_id,
                    LedgerNote.session_key == request.session_key,
                    LedgerNote.note_key == note_key,
                )
                .first()
            )
            if note is None:
                note = LedgerNote(
                    project_id=request.project_id,
                    session_key=request.session_key,
                    note_key=note_key,
                )
                db.add(note)

            note.mission_id = request.mission_id
            note.origin = MCP_AGENT_ORIGIN
            note.content = request.content
            note.tags = list(request.tags)
            note.owner_id = owner_id
            note.workspace_id = workspace_id
            try:
                db.commit()
            except IntegrityError as error:
                db.rollback()
                if retried_identity_conflict or not _is_note_identity_conflict(error):
                    raise
                retried_identity_conflict = True
                continue
            except Exception:
                db.rollback()
                raise
            db.refresh(note)
            return note

    def list_ledger(
        self,
        db: Session,
        *,
        project_id: UUID,
        session_key: str | None,
        mission_id: UUID | None,
        disposition: str | None,
        page: int,
        page_size: int,
        entry_access_filter: Any | None,
        note_access_filter: Any | None,
        allowed_project_ids: list[UUID] | None = None,
    ) -> tuple[list[LedgerEntry], list[LedgerNote], int, int]:
        """List accessible entries and notes before applying pagination."""
        if allowed_project_ids is not None and project_id not in allowed_project_ids:
            return [], [], 0, 0
        entry_query = _apply_project_scope(
            _apply_access_filter(db.query(LedgerEntry), entry_access_filter),
            LedgerEntry,
            allowed_project_ids,
        ).filter(LedgerEntry.project_id == project_id)
        note_query = _apply_project_scope(
            _apply_access_filter(db.query(LedgerNote), note_access_filter),
            LedgerNote,
            allowed_project_ids,
        ).filter(LedgerNote.project_id == project_id)

        if session_key is not None:
            entry_query = entry_query.filter(LedgerEntry.session_key == session_key)
            note_query = note_query.filter(LedgerNote.session_key == session_key)
        if mission_id is not None:
            entry_query = entry_query.filter(LedgerEntry.mission_id == mission_id)
            note_query = note_query.filter(LedgerNote.mission_id == mission_id)
        if disposition is not None:
            entry_query = entry_query.filter(LedgerEntry.disposition == disposition)
        entry_total = entry_query.count()
        note_total = note_query.count()
        offset = (page - 1) * page_size
        entries = (
            entry_query.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        notes = (
            note_query.order_by(LedgerNote.updated_at.desc(), LedgerNote.id.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return entries, notes, entry_total, note_total

    def search(
        self,
        db: Session,
        *,
        project_id: UUID,
        keyword: str,
        session_key: str | None,
        mission_id: UUID | None,
        disposition: str | None,
        page: int,
        page_size: int,
        access_filter: Any | None,
        allowed_project_ids: list[UUID] | None = None,
    ) -> tuple[list[LedgerEntry], int]:
        """Run ranked PostgreSQL FTS with literal ILIKE fallback."""
        if allowed_project_ids is not None and project_id not in allowed_project_ids:
            return [], 0
        query = _apply_project_scope(
            _apply_access_filter(db.query(LedgerEntry), access_filter),
            LedgerEntry,
            allowed_project_ids,
        ).filter(LedgerEntry.project_id == project_id)
        rank = None
        if db.get_bind().dialect.name == "postgresql" and any(character.isalnum() for character in keyword):
            search_vector: ColumnElement[Any] = literal_column(_SEARCH_VECTOR_SQL)
            ts_query = func.websearch_to_tsquery(
                literal_column("'english'::regconfig"),
                keyword,
            )
            query = query.filter(search_vector.op("@@")(ts_query))
            rank = func.ts_rank_cd(search_vector, ts_query)
        else:
            escaped = _escape_like(keyword)
            pattern = f"%{escaped}%"
            query = query.filter(
                or_(
                    LedgerEntry.claim.ilike(pattern, escape="\\"),
                    LedgerEntry.summary.ilike(pattern, escape="\\"),
                    LedgerEntry.source_url.ilike(pattern, escape="\\"),
                    LedgerEntry.snippet.ilike(pattern, escape="\\"),
                    LedgerEntry.query.ilike(pattern, escape="\\"),
                )
            )
        if session_key is not None:
            query = query.filter(LedgerEntry.session_key == session_key)
        if mission_id is not None:
            query = query.filter(LedgerEntry.mission_id == mission_id)
        if disposition is not None:
            query = query.filter(LedgerEntry.disposition == disposition)
        total = query.count()
        if rank is not None:
            query = query.order_by(
                rank.desc(),
                LedgerEntry.created_at.desc(),
                LedgerEntry.id.desc(),
            )
        else:
            query = query.order_by(
                LedgerEntry.created_at.desc(),
                LedgerEntry.id.desc(),
            )
        entries = query.offset((page - 1) * page_size).limit(page_size).all()
        return entries, total

    def promote(
        self,
        db: Session,
        *,
        project_id: UUID,
        session_key: str,
        title: str | None,
        target: str,
        owner_id: UUID,
        workspace_id: UUID | None,
        created_by: str,
    ) -> tuple[Report, Any | None, int, int]:
        """Promote all session entries and notes to a persisted report artifact."""
        entries = (
            db.query(LedgerEntry)
            .filter(
                LedgerEntry.project_id == project_id,
                LedgerEntry.session_key == session_key,
            )
            .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
            .all()
        )
        notes = (
            db.query(LedgerNote)
            .filter(
                LedgerNote.project_id == project_id,
                LedgerNote.session_key == session_key,
            )
            .order_by(LedgerNote.note_key.asc(), LedgerNote.id.asc())
            .all()
        )
        if not entries and not notes:
            raise ValueError("No evidence or notes found for this session")

        report_title = title or f"Evidence Ledger - {session_key}"[:255]
        content = _render_markdown(session_key, entries, notes)
        report = Report(
            project_id=project_id,
            title=report_title,
            report_type="evidence-ledger",
            content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status="draft",
            created_by=created_by,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        db.add(report)
        db.flush()
        db.add_all(
            [
                ReportSource(
                    report_id=report.id,
                    source_type="ledger_entry",
                    source_id=entry.id,
                )
                for entry in entries
            ]
            + [
                ReportSource(
                    report_id=report.id,
                    source_type="ledger_note",
                    source_id=note.id,
                )
                for note in notes
            ]
        )

        document = None
        if target == "document":
            document_name = report_title if report_title.lower().endswith(".md") else f"{report_title}.md"
            report_id = report.id
            try:
                document = self._promotion_service.promote_project_report(
                    db,
                    report,
                    project_id=project_id,
                    document_name=document_name,
                    document_metadata={
                        "promoted_from": "evidence-ledger",
                        "ledger_session_key": session_key,
                        "entry_count": len(entries),
                        "note_count": len(notes),
                    },
                    status_details={
                        "promoted_from": "evidence-ledger",
                        "ledger_session_key": session_key,
                    },
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                )
            except Exception:
                self._compensate_failed_document_promotion(db, report_id)
                raise
        else:
            db.commit()
            db.refresh(report)

        return report, document, len(entries), len(notes)

    def _compensate_failed_document_promotion(
        self,
        db: Session,
        report_id: UUID,
    ) -> None:
        """Remove ledger artifacts committed before ingestion reported failure.

        The shared ingestion pipeline commits between stages so the document is
        visible to those stages. A failed ledger promotion must still be retryable:
        remove the staged document first, then its report and ReportSource rows.
        """
        db.rollback()
        try:
            documents = db.query(Document).filter(Document.source_report_id == report_id).all()
            for document in documents:
                self._promotion_service.cleanup_document_vectors(document.id)
                db.delete(document)
            persisted_report = db.get(Report, report_id)
            if persisted_report is not None:
                db.delete(persisted_report)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to compensate evidence-ledger document promotion for report %s",
                report_id,
            )
            raise


def get_evidence_ledger_service() -> EvidenceLedgerService:
    """FastAPI dependency factory for the stateless evidence service."""
    return EvidenceLedgerService()
