"""Persistence, search, and promotion operations for the evidence ledger."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import AnyHttpUrl, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, literal_column, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.document import Document
from app.models.evidence_ledger import (
    DeepSearchLedgerBatch,
    LedgerEntry,
    LedgerNote,
    LedgerSource,
)
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.schemas.evidence_ledger import CaptureItem, CaptureRequest, NoteUpsertRequest
from app.services.report_promotion import ReportPromotionService

MCP_AGENT_ORIGIN = "mcp-agent"
DEEPSEARCH_WORKER_ORIGIN = "deepsearch-worker"
logger = logging.getLogger(__name__)
_NOTE_IDENTITY_CONSTRAINT = "uq_ledger_notes_project_session_key"
_SOURCE_IDENTITY_CONSTRAINT = "uq_ledger_sources_project_url_hash"
_DEEPSEARCH_BATCH_IDENTITY_CONSTRAINT = "uq_deepsearch_ledger_batches_mission_job"
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
_DEEPSEARCH_LEDGER_MAX_ENTRIES = 1_000
_DEEPSEARCH_LEDGER_OUTCOME_FIELDS = {
    "tool",
    "url",
    "status",
    "status_code",
    "error_category",
    "alive",
}
_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


class DeepSearchEvidenceValidationError(ValueError):
    """Persisted DeepSearch evidence is malformed or cannot be projected."""


class DeepSearchEvidenceConflictError(RuntimeError):
    """The trigger conflicts with persisted mission or replay state."""


class DeepSearchEvidenceNotFoundError(LookupError):
    """The requested mission or its live project does not exist."""


@dataclass(frozen=True)
class DeepSearchEvidenceCaptureResult:
    """Stable result of one initial or replayed DeepSearch ledger batch."""

    status: Literal["captured", "already_processed"]
    mission_id: UUID
    deepsearch_job_id: str
    session_key: str
    entry_ids: list[UUID]
    entry_count: int


@dataclass(frozen=True)
class _SourceRecord:
    url: str
    title: str | None
    snippet: str | None
    alive: bool | None


@dataclass(frozen=True)
class _ToolFailure:
    url: str
    tool: str
    rationale: str


def _deepsearch_validation(message: str) -> DeepSearchEvidenceValidationError:
    return DeepSearchEvidenceValidationError(message)


def _optional_record_text(
    record: Mapping[str, Any],
    key: str,
    *,
    path: str,
) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _deepsearch_validation(f"{path}.{key} must be a string or null")
    return value


def _required_record_text(
    record: Mapping[str, Any],
    key: str,
    *,
    path: str,
) -> str:
    value = _optional_record_text(record, key, path=path)
    if value is None or not value.strip():
        raise _deepsearch_validation(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _optional_bool(
    record: Mapping[str, Any],
    key: str,
    *,
    path: str,
) -> bool | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _deepsearch_validation(f"{path}.{key} must be a boolean or null")
    return value


def _canonical_url(value: object, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _deepsearch_validation(f"{path} must be a non-empty HTTP(S) URL")
    try:
        validated = _HTTP_URL_ADAPTER.validate_python(value.strip())
    except PydanticValidationError as exc:
        raise _deepsearch_validation(f"{path} must be a valid HTTP(S) URL") from exc
    if validated.username is not None or validated.password is not None:
        raise _deepsearch_validation(f"{path} must not contain URL userinfo")
    canonical = str(validated)
    if len(canonical) > 4_096:
        raise _deepsearch_validation(f"{path} cannot exceed 4096 characters")
    return canonical


def _optional_source_text(
    record: Mapping[str, Any],
    key: str,
    *,
    path: str,
) -> str | None:
    value = _optional_record_text(record, key, path=path)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _merge_source_value(
    current: str | bool | None,
    incoming: str | bool | None,
    *,
    field: str,
    url: str,
) -> str | bool | None:
    if current is None:
        return incoming
    if incoming is None or incoming == current:
        return current
    raise _deepsearch_validation(f"Canonical source {url!r} has conflicting non-empty {field} values")


def _capture_item(
    *,
    claim: str,
    source_url: str,
    disposition: str,
    summary: str | None = None,
    snippet: str | None = None,
    tags: list[str] | None = None,
    exact_claim: bool = False,
) -> CaptureItem:
    """Validate one server projection against the human capture item contract."""
    try:
        item = CaptureItem.model_validate(
            {
                "claim": claim,
                "summary": summary,
                "source_url": source_url,
                "snippet": snippet,
                "query": None,
                "disposition": disposition,
                "tags": tags or [],
            }
        )
    except PydanticValidationError as exc:
        raise _deepsearch_validation(f"DeepSearch evidence item is invalid: {exc.errors(include_url=False)}") from exc
    if exact_claim and item.claim != claim:
        raise _deepsearch_validation("A citation span must be non-empty and contain no surrounding whitespace")
    return item


def _parse_sources(protocol: Mapping[str, Any]) -> list[_SourceRecord]:
    if "sources_collected" not in protocol:
        raise _deepsearch_validation("result_protocol.sources_collected is required")
    raw_sources = protocol["sources_collected"]
    if not isinstance(raw_sources, list):
        raise _deepsearch_validation("result_protocol.sources_collected must be a list")

    sources_by_url: dict[str, _SourceRecord] = {}
    for index, raw_source in enumerate(raw_sources):
        path = f"result_protocol.sources_collected[{index}]"
        if not isinstance(raw_source, Mapping):
            raise _deepsearch_validation(f"{path} must be an object")
        url = _canonical_url(raw_source.get("url"), path=f"{path}.url")
        candidate = _SourceRecord(
            url=url,
            title=_optional_source_text(raw_source, "title", path=path),
            snippet=_optional_source_text(raw_source, "snippet", path=path),
            alive=_optional_bool(raw_source, "alive", path=path),
        )
        existing = sources_by_url.get(url)
        if existing is None:
            sources_by_url[url] = candidate
            continue
        sources_by_url[url] = _SourceRecord(
            url=url,
            title=cast(
                str | None,
                _merge_source_value(
                    existing.title,
                    candidate.title,
                    field="title",
                    url=url,
                ),
            ),
            snippet=cast(
                str | None,
                _merge_source_value(
                    existing.snippet,
                    candidate.snippet,
                    field="snippet",
                    url=url,
                ),
            ),
            alive=cast(
                bool | None,
                _merge_source_value(
                    existing.alive,
                    candidate.alive,
                    field="alive",
                    url=url,
                ),
            ),
        )
    return [sources_by_url[url] for url in sorted(sources_by_url)]


def _tool_failure_rationale(
    record: Mapping[str, Any],
    *,
    tool: str,
    status: str,
) -> str:
    """Preserve the exact outcome fields without inventing a diagnosis."""
    parts = [f"tool={tool}", f"status={status}"]
    for key in ("status_code", "error_category", "alive"):
        if key in record:
            parts.append(f"{key}={record[key]}")
    return "; ".join(parts)


def _parse_tool_failures(
    synthesis_telemetry: Mapping[str, Any],
) -> list[_ToolFailure]:
    if "tool_outcomes" not in synthesis_telemetry:
        raise _deepsearch_validation("execution_metadata.synthesis_telemetry.tool_outcomes is required")
    raw_outcomes = synthesis_telemetry["tool_outcomes"]
    if not isinstance(raw_outcomes, Mapping):
        raise _deepsearch_validation("execution_metadata.synthesis_telemetry.tool_outcomes must be an object")
    if "ledger_records_truncated" not in raw_outcomes:
        raise _deepsearch_validation("tool_outcomes.ledger_records_truncated is required")
    truncated = raw_outcomes["ledger_records_truncated"]
    if not isinstance(truncated, int) or isinstance(truncated, bool) or truncated < 0:
        raise _deepsearch_validation("tool_outcomes.ledger_records_truncated must be a non-negative integer")
    if truncated:
        raise _deepsearch_validation("tool_outcomes ledger records were truncated upstream; refusing partial capture")
    if "ledger_records" not in raw_outcomes:
        raise _deepsearch_validation("tool_outcomes.ledger_records is required")
    raw_records = raw_outcomes["ledger_records"]
    if not isinstance(raw_records, list):
        raise _deepsearch_validation("tool_outcomes.ledger_records must be a list")

    failures: list[_ToolFailure] = []
    for index, raw_record in enumerate(raw_records):
        path = f"tool_outcomes.ledger_records[{index}]"
        if not isinstance(raw_record, Mapping):
            raise _deepsearch_validation(f"{path} must be an object")
        if set(raw_record) - _DEEPSEARCH_LEDGER_OUTCOME_FIELDS:
            raise _deepsearch_validation(f"{path} contains fields outside the schema_version=1 ledger contract")
        tool_value = raw_record.get("tool")
        if not isinstance(tool_value, str):
            raise _deepsearch_validation(f"{path}.tool must be a string")
        tool = tool_value.strip()
        if tool not in {"source_fetch", "url_liveness"}:
            raise _deepsearch_validation(f"{path}.tool must be 'source_fetch' or 'url_liveness'")
        status = _required_record_text(raw_record, "status", path=path)
        if status not in {"ok", "error"}:
            raise _deepsearch_validation(f"{path}.status must be 'ok' or 'error' for {tool}")
        url = _canonical_url(raw_record.get("url"), path=f"{path}.url")
        status_code = raw_record.get("status_code")
        if status_code is not None and (
            not isinstance(status_code, int) or isinstance(status_code, bool) or status_code < 0 or status_code > 599
        ):
            raise _deepsearch_validation(f"{path}.status_code must be an integer from 0 through 599 or null")
        error_category = raw_record.get("error_category")
        if error_category is not None and (not isinstance(error_category, str) or len(error_category) > 200):
            raise _deepsearch_validation(f"{path}.error_category must be a string of at most 200 characters or null")
        alive = _optional_bool(raw_record, "alive", path=path)
        if tool == "url_liveness" and alive is None:
            raise _deepsearch_validation(f"{path}.alive is required for url_liveness")
        failed = status == "error" or (tool == "url_liveness" and alive is False)
        if not failed:
            continue
        failures.append(
            _ToolFailure(
                url=url,
                tool=tool,
                rationale=_tool_failure_rationale(
                    raw_record,
                    tool=tool,
                    status=status,
                ),
            )
        )
    unique_failures = {(failure.url, failure.tool, failure.rationale): failure for failure in failures}
    return [unique_failures[key] for key in sorted(unique_failures)]


def _source_claim(source: _SourceRecord) -> str:
    title = (source.title or "").strip()
    snippet = (source.snippet or "").strip()
    if title and snippet:
        return f"{title}: {snippet}"
    if title:
        return title
    if snippet:
        return snippet
    return source.url


def _canonical_item_key(item: CaptureItem) -> str:
    return json.dumps(
        item.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _project_deepsearch_items(
    *,
    result_protocol: Any,
    result_markdown: Any,
    execution_metadata: Any,
) -> list[CaptureItem]:
    """Project only persisted, source-backed DeepSearch facts into ledger items."""
    if not isinstance(result_protocol, Mapping):
        raise _deepsearch_validation("mission.result_protocol must be an object")
    if not isinstance(result_markdown, str):
        raise _deepsearch_validation("mission.result_markdown must be a string")
    if not isinstance(execution_metadata, Mapping):
        raise _deepsearch_validation("mission.execution_metadata must be an object")

    sources = _parse_sources(result_protocol)
    sources_by_url = {source.url: source for source in sources}
    if "citations" not in result_protocol:
        raise _deepsearch_validation("result_protocol.citations is required")
    raw_citations = result_protocol["citations"]
    if not isinstance(raw_citations, list):
        raise _deepsearch_validation("result_protocol.citations must be a list")

    if "synthesis_telemetry" not in execution_metadata:
        raise _deepsearch_validation("execution_metadata.synthesis_telemetry is required")
    raw_synthesis = execution_metadata["synthesis_telemetry"]
    if not isinstance(raw_synthesis, Mapping):
        raise _deepsearch_validation("execution_metadata.synthesis_telemetry must be an object")
    failures = _parse_tool_failures(raw_synthesis)
    failures_by_url: dict[str, list[_ToolFailure]] = {}
    for failure in failures:
        failures_by_url.setdefault(failure.url, []).append(failure)

    items: list[CaptureItem] = []
    cited_urls: set[str] = set()
    handled_failure_urls: set[str] = set()
    for index, raw_citation in enumerate(raw_citations):
        path = f"result_protocol.citations[{index}]"
        if not isinstance(raw_citation, Mapping):
            raise _deepsearch_validation(f"{path} must be an object")
        citation_type = raw_citation.get("type", "url_citation")
        if citation_type != "url_citation":
            raise _deepsearch_validation(f"{path}.type must be 'url_citation'")
        start = raw_citation.get("start_index")
        end = raw_citation.get("end_index")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or end > len(result_markdown)
        ):
            raise _deepsearch_validation(f"{path} has an invalid result_markdown span")
        url = _canonical_url(raw_citation.get("url"), path=f"{path}.url")
        live = _optional_bool(raw_citation, "live", path=path)
        title = _optional_record_text(raw_citation, "title", path=path)
        source = sources_by_url.get(url)
        cited_urls.add(url)
        failure_details = failures_by_url.get(url, [])
        if live is False:
            rationale_parts = ["citation live=False"]
            rationale_parts.extend(failure.rationale for failure in failure_details)
            summary = "\n".join(rationale_parts)
            disposition = "rejected"
            tags = ["deepsearch", "citation", "rejected-liveness"]
            if failure_details:
                handled_failure_urls.add(url)
        elif live is True:
            summary = title or (source.title if source else None)
            disposition = "supporting"
            tags = ["deepsearch", "citation", "live"]
        else:
            summary = title or (source.title if source else None)
            disposition = "background"
            tags = ["deepsearch", "citation", "liveness-unknown"]
        items.append(
            _capture_item(
                claim=result_markdown[start:end],
                summary=summary,
                source_url=url,
                snippet=source.snippet if source else None,
                disposition=disposition,
                tags=tags,
                exact_claim=True,
            )
        )

    for source in sources:
        if source.url in cited_urls:
            continue
        failure_details = failures_by_url.get(source.url, [])
        if source.alive is False:
            rationale_parts = ["source alive=False"]
            rationale_parts.extend(failure.rationale for failure in failure_details)
            summary = "\n".join(rationale_parts)
            disposition = "rejected"
            tags = ["deepsearch", "source-collected", "rejected-liveness"]
            if failure_details:
                handled_failure_urls.add(source.url)
        else:
            summary = None
            disposition = "background"
            tags = ["deepsearch", "source-collected"]
        items.append(
            _capture_item(
                claim=_source_claim(source),
                summary=summary,
                source_url=source.url,
                snippet=source.snippet,
                disposition=disposition,
                tags=tags,
            )
        )

    raw_critique = raw_synthesis.get("critique_telemetry")
    if raw_critique is not None:
        if not isinstance(raw_critique, Mapping):
            raise _deepsearch_validation("synthesis_telemetry.critique_telemetry must be an object")
        raw_annotations = raw_critique.get("annotations", [])
        if not isinstance(raw_annotations, list):
            raise _deepsearch_validation("critique_telemetry.annotations must be a list")
        for index, raw_annotation in enumerate(raw_annotations):
            path = f"critique_telemetry.annotations[{index}]"
            if not isinstance(raw_annotation, Mapping):
                raise _deepsearch_validation(f"{path} must be an object")
            applied = raw_annotation.get("applied")
            if not isinstance(applied, bool):
                raise _deepsearch_validation(f"{path}.applied must be a boolean")
            if not applied:
                continue
            anchor = _optional_record_text(raw_annotation, "anchor", path=path)
            if anchor is None or not anchor.strip():
                raise _deepsearch_validation(f"{path}.anchor must be a non-empty string")
            if anchor != anchor.strip():
                raise _deepsearch_validation(f"{path}.anchor must not contain surrounding whitespace")
            verdict = _required_record_text(raw_annotation, "verdict", path=path)
            if verdict not in {"unsupported", "hallucinated"}:
                raise _deepsearch_validation(f"{path}.verdict must be 'unsupported' or 'hallucinated'")
            note = _optional_record_text(raw_annotation, "note", path=path)
            reason = _optional_record_text(raw_annotation, "reason", path=path)
            if not (note and note.strip()) and not (reason and reason.strip()):
                raise _deepsearch_validation(f"{path} must preserve a note or rationale")
            raw_urls = raw_annotation.get("citation_urls", [])
            if not isinstance(raw_urls, list):
                raise _deepsearch_validation(f"{path}.citation_urls must be a list")
            rationale_parts = []
            if note is not None:
                rationale_parts.append(f"note={note}")
            if reason is not None:
                rationale_parts.append(f"reason={reason}")
            for url_index, raw_url in enumerate(raw_urls):
                url = _canonical_url(
                    raw_url,
                    path=f"{path}.citation_urls[{url_index}]",
                )
                items.append(
                    _capture_item(
                        claim=anchor,
                        summary="; ".join(rationale_parts),
                        source_url=url,
                        disposition="rejected",
                        tags=["deepsearch", "critique", "applied"],
                        exact_claim=True,
                    )
                )

    # Failures remain distinct attempt claims unless they were already folded
    # into a citation/source rejected by liveness. Exact duplicate outcome
    # records were removed above, but distinct attempts sharing a URL survive.
    for url in sorted(failures_by_url):
        if url in handled_failure_urls:
            continue
        source = sources_by_url.get(url)
        for failure in failures_by_url[url]:
            claim = (
                f"{_source_claim(source)} — {failure.tool} failed retrieval attempt"
                if source is not None
                else f"{failure.tool} failed for {url}"
            )
            items.append(
                _capture_item(
                    claim=claim,
                    summary=failure.rationale,
                    source_url=url,
                    snippet=source.snippet if source else None,
                    disposition="rejected",
                    tags=["deepsearch", "tool-outcome", failure.tool],
                )
            )

    canonical_items: list[CaptureItem] = []
    previous_key: str | None = None
    for item in sorted(items, key=_canonical_item_key):
        item_key = _canonical_item_key(item)
        if item_key != previous_key:
            canonical_items.append(item)
        previous_key = item_key

    if not canonical_items:
        raise _deepsearch_validation("Persisted DeepSearch result projected zero source-backed evidence entries")
    if len(canonical_items) > _DEEPSEARCH_LEDGER_MAX_ENTRIES:
        raise _deepsearch_validation(
            f"DeepSearch evidence projection has {len(canonical_items)} entries; "
            f"maximum is {_DEEPSEARCH_LEDGER_MAX_ENTRIES}"
        )
    return canonical_items


def _deepsearch_payload_hash(
    *,
    project_id: UUID,
    mission_id: UUID,
    deepsearch_job_id: str,
    session_key: str,
    items: Sequence[CaptureItem],
) -> str:
    canonical = {
        "schema_version": 1,
        "project_id": str(project_id),
        "mission_id": str(mission_id),
        "deepsearch_job_id": deepsearch_job_id,
        "session_key": session_key,
        "entries": [item.model_dump(mode="json") for item in items],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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

    def capture_deepsearch_mission_evidence(
        self,
        db: Session,
        mission_id: UUID,
        deepsearch_job_id: str,
    ) -> DeepSearchEvidenceCaptureResult:
        """Atomically project one completed, persisted DeepSearch result.

        The trigger contains no evidence fields. Mission state is locked and
        read from this database, then the canonical projection is claimed by
        ``(mission_id, deepsearch_job_id)`` before sources or entries change.
        """
        session_key = f"deepsearch:{deepsearch_job_id}"
        try:
            mission_query = db.query(Mission).filter(Mission.id == mission_id)
            if db.get_bind().dialect.name == "postgresql":
                mission_query = mission_query.with_for_update(of=Mission)
            mission = mission_query.one_or_none()
            if mission is None:
                raise DeepSearchEvidenceNotFoundError(f"Mission {mission_id} was not found")
            if mission.status not in {"completed", "validation_failed"}:
                raise DeepSearchEvidenceConflictError(
                    "DeepSearch evidence requires a terminal reviewable mission "
                    "('completed' or 'validation_failed'); "
                    f"current status is {mission.status!r}"
                )
            if not mission.deepsearch_job_id:
                raise DeepSearchEvidenceConflictError("Completed mission has no persisted DeepSearch job id")
            if mission.deepsearch_job_id != deepsearch_job_id:
                raise DeepSearchEvidenceConflictError("deepsearch_job_id does not match the mission's persisted job")
            if mission.project_id is None:
                raise DeepSearchEvidenceConflictError("Completed mission has no persisted project")

            project = (
                db.query(Project)
                .filter(
                    Project.id == mission.project_id,
                    Project.deleted_at.is_(None),
                )
                .one_or_none()
            )
            if project is None:
                raise DeepSearchEvidenceNotFoundError(f"Mission project {mission.project_id} is missing or deleted")

            items = _project_deepsearch_items(
                result_protocol=mission.result_protocol,
                result_markdown=mission.result_markdown,
                execution_metadata=mission.execution_metadata,
            )
            payload_hash = _deepsearch_payload_hash(
                project_id=project.id,
                mission_id=mission.id,
                deepsearch_job_id=deepsearch_job_id,
                session_key=session_key,
                items=items,
            )
            batch_id = uuid.uuid4()
            batch_values = {
                "id": batch_id,
                "mission_id": mission.id,
                "deepsearch_job_id": deepsearch_job_id,
                "session_key": session_key,
                "payload_hash": payload_hash,
                "entry_count": len(items),
            }
            dialect_name = db.get_bind().dialect.name
            if dialect_name == "postgresql":
                batch_insert = postgresql_insert(DeepSearchLedgerBatch).values(batch_values)
                batch_insert = batch_insert.on_conflict_do_nothing(
                    constraint=_DEEPSEARCH_BATCH_IDENTITY_CONSTRAINT
                ).returning(DeepSearchLedgerBatch.id)
            elif dialect_name == "sqlite":
                batch_insert = sqlite_insert(DeepSearchLedgerBatch).values(batch_values)
                batch_insert = batch_insert.on_conflict_do_nothing(
                    index_elements=[
                        DeepSearchLedgerBatch.mission_id,
                        DeepSearchLedgerBatch.deepsearch_job_id,
                    ]
                ).returning(DeepSearchLedgerBatch.id)
            else:
                raise RuntimeError(f"DeepSearch evidence capture does not support {dialect_name!r}")

            claimed_batch_id = db.execute(batch_insert).scalar_one_or_none()
            if claimed_batch_id is None:
                existing = (
                    db.query(DeepSearchLedgerBatch)
                    .filter(
                        DeepSearchLedgerBatch.mission_id == mission.id,
                        DeepSearchLedgerBatch.deepsearch_job_id == deepsearch_job_id,
                    )
                    .one_or_none()
                )
                if existing is None:
                    raise RuntimeError("DeepSearch batch conflict did not resolve its persisted row")
                if (
                    existing.payload_hash != payload_hash
                    or existing.session_key != session_key
                    or existing.entry_count != len(items)
                ):
                    raise DeepSearchEvidenceConflictError(
                        "DeepSearch evidence replay payload differs from the already processed mission/job batch"
                    )
                entry_ids = self._deepsearch_batch_entry_ids(db, existing)
                db.commit()
                return DeepSearchEvidenceCaptureResult(
                    status="already_processed",
                    mission_id=mission.id,
                    deepsearch_job_id=deepsearch_job_id,
                    session_key=session_key,
                    entry_ids=entry_ids,
                    entry_count=len(entry_ids),
                )

            source_urls = [str(item.source_url) for item in items]
            sources = self._upsert_sources(
                db,
                project_id=project.id,
                sightings=Counter(source_urls),
            )
            owner_id = mission.owner_id or project.owner_id
            entries = [
                LedgerEntry(
                    project_id=project.id,
                    mission_id=mission.id,
                    deepsearch_batch_id=claimed_batch_id,
                    session_key=session_key,
                    origin=DEEPSEARCH_WORKER_ORIGIN,
                    claim=item.claim,
                    summary=item.summary,
                    source_url=source_url,
                    source_id=sources[source_url].id,
                    source=sources[source_url],
                    snippet=item.snippet,
                    query=None,
                    disposition=item.disposition,
                    tags=list(item.tags),
                    owner_id=owner_id,
                    workspace_id=project.workspace_id,
                )
                for item, source_url in zip(items, source_urls, strict=True)
            ]
            db.add_all(entries)
            db.flush()
            entry_ids = sorted(
                (cast(UUID, entry.id) for entry in entries),
                key=str,
            )
            if len(entry_ids) != len(items):
                raise RuntimeError("DeepSearch evidence insert cardinality does not match projection")
            db.commit()
            return DeepSearchEvidenceCaptureResult(
                status="captured",
                mission_id=mission.id,
                deepsearch_job_id=deepsearch_job_id,
                session_key=session_key,
                entry_ids=entry_ids,
                entry_count=len(entry_ids),
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _deepsearch_batch_entry_ids(
        db: Session,
        batch: DeepSearchLedgerBatch,
    ) -> list[UUID]:
        """Resolve and validate the exact entries belonging to a claimed batch."""
        entries = db.query(LedgerEntry).filter(LedgerEntry.deepsearch_batch_id == batch.id).all()
        if len(entries) != batch.entry_count:
            raise RuntimeError(
                f"DeepSearch ledger batch {batch.id} expected {batch.entry_count} entries but resolved {len(entries)}"
            )
        for entry in entries:
            if (
                entry.mission_id != batch.mission_id
                or entry.session_key != batch.session_key
                or entry.origin != DEEPSEARCH_WORKER_ORIGIN
            ):
                raise RuntimeError(f"DeepSearch ledger batch {batch.id} has an incompatible entry")
        return sorted((cast(UUID, entry.id) for entry in entries), key=str)

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
