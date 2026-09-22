"""The Librarian, part 1: the mission-authoring assistant (LIB-1).

Two stages behind one provider seam (decision #517, #519):

* ``converse`` runs one conversational turn. The model may call a single tool,
  ``search_evidence``, scoped to the caller's own access to the project's evidence
  ledger. Its reply is a list of typed segments, and the provenance validator
  below rejects any corpus claim that is uncited or cites an entry the tool did
  not return in this turn. That validator is the product's integrity guarantee
  (decision #513), so it runs on the server, not in a prompt.
* ``draft_mission`` is the planning stage: one JSON-mode call that produces a
  ``MissionDraft`` validated with the exact constraints ``MissionCreate`` applies,
  repaired once on failure, then compiled through the offline contract preview
  and the submit linter so the user sees what DeepSearch would run.

Creating the mission is a separate, human-confirmed, idempotent call (decision
#515). Nothing here persists between requests.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.project import Project
from app.models.usage_record import USAGE_KIND_LIBRARIAN_DRAFT, USAGE_KIND_LIBRARIAN_TURN
from app.schemas.librarian import (
    AssistantReply,
    LintViolationOut,
    MissionDraft,
    ReplySegment,
    TranscriptMessage,
)
from app.schemas.mission import MissionCreate
from app.services.cost_monitor import get_cost_monitor
from app.services.deepsearch_preview_client import (
    ContractPreviewError,
    preview_mission_contract,
)
from app.services.evidence_ledger import EvidenceLedgerService, evidence_access_filter
from app.services.librarian_model import ModelReply
from app.services.mission_linter import lint_mission_for_submit
from app.services.mission_service import MissionNotFoundError, MissionService
from app.services.usage_recorder import record_librarian_usage

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
EVIDENCE_PAGE_SIZE = 8
TURN_MAX_TOKENS = 3000
DRAFT_MAX_TOKENS = 2500
LIBRARIAN_TAG = "librarian"
LIBRARIAN_AUTHOR = "librarian"
SEARCH_EVIDENCE = "search_evidence"

WITHHELD_TEXT = (
    "A statement about this project's evidence was withheld: it did not carry a "
    "citation that resolves to an evidence entry found in this turn."
)

SEARCH_EVIDENCE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SEARCH_EVIDENCE,
        "description": (
            "Search this project's evidence ledger: claims captured from earlier research, "
            "each with a source URL. Call it before saying anything about what the project "
            "already knows, and cite the returned ids."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for."},
            },
            "required": ["query"],
        },
    },
}

_MISSION_ID_CLEAN = re.compile(r"[^A-Za-z0-9._-]+")


class LibrarianDraftError(ValueError):
    """The model could not produce a valid mission draft after one repair."""


class LibrarianConflict(ValueError):
    """The draft's mission_id already names a different mission."""


@dataclass
class ProvenanceViolation:
    segment_index: int
    reason: str
    detail: str


@dataclass
class _UsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, usage: dict[str, int] | None) -> None:
        self.calls += 1
        if not usage:
            return
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.total_tokens += int(usage.get("total_tokens", 0) or 0)

    def as_dict(self) -> dict[str, int] | None:
        if self.total_tokens == 0 and self.prompt_tokens == 0 and self.completion_tokens == 0:
            return None
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class TurnResult:
    reply: AssistantReply
    evidence: list[LedgerEntry]
    withheld_count: int
    usage: dict[str, int] | None
    model: str


@dataclass
class DraftResult:
    draft: MissionDraft
    preview: dict[str, Any] | None
    preview_error: str | None
    lint_errors: list[LintViolationOut]
    lint_warnings: list[LintViolationOut]
    notes: list[str] = field(default_factory=list)
    usage: dict[str, int] | None = None
    model: str = ""


# --------------------------------------------------------------------------- provenance


def validate_provenance(reply: AssistantReply, retrieved_ids: Iterable[str]) -> list[ProvenanceViolation]:
    """Return every way the reply's provenance fails to hold.

    Two failure modes, mirroring criterion 4 of LIB-1: a corpus claim with no
    citation, and any citation (on any segment) that is not one of the evidence
    ids the tool loop actually returned in this turn. The second is what a
    fabricated citation is, operationally.
    """
    allowed = {str(item) for item in retrieved_ids}
    violations: list[ProvenanceViolation] = []
    for index, segment in enumerate(reply.segments):
        unresolved = [citation for citation in segment.citations if citation not in allowed]
        if segment.kind == "corpus_claim" and not segment.citations:
            violations.append(
                ProvenanceViolation(
                    index,
                    "uncited_corpus_claim",
                    "Segment asserts something about the project's evidence but cites nothing.",
                )
            )
        if unresolved:
            violations.append(
                ProvenanceViolation(
                    index,
                    "unresolved_citation",
                    "Citations do not match any evidence returned by search_evidence in this turn: "
                    + ", ".join(unresolved),
                )
            )
    return violations


def withhold(reply: AssistantReply, violations: Iterable[ProvenanceViolation]) -> AssistantReply:
    """Replace every violating segment with a visible notice. Nothing unproven is rendered as fact."""
    bad = {violation.segment_index for violation in violations}
    segments = [
        ReplySegment(kind="withheld", text=WITHHELD_TEXT, citations=[]) if index in bad else segment
        for index, segment in enumerate(reply.segments)
    ]
    return AssistantReply(segments=segments, suggested_action=reply.suggested_action)


# --------------------------------------------------------------------------- parsing


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _extract_json_object(text: str) -> Any:
    candidate = _strip_fences(text)
    try:
        return json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(candidate[start : end + 1])


_TEXT_FIELD = re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"?', re.DOTALL)


def _salvage_text(text: str) -> str:
    """Pull the human-readable text out of a reply whose JSON never closed.

    Found in production on the first day: a reply longer than the token cap arrives
    as truncated JSON, and rendering that verbatim shows the user braces and escape
    codes. Every ``text`` value is recovered and rendered as prose. Citations are
    deliberately dropped: nothing salvaged from a broken reply may pass as a claim.
    """
    pieces = []
    for match in _TEXT_FIELD.finditer(text):
        raw = match.group(1)
        try:
            pieces.append(json.loads(f'"{raw}"'))
        except ValueError:
            pieces.append(raw.replace("\\n", "\n").replace('\\"', '"'))
    return "\n\n".join(piece.strip() for piece in pieces if piece.strip())


def _parse_reply_detailed(content: str | None) -> tuple[AssistantReply, bool]:
    """Parse the model's reply; the flag says whether the JSON shape was honoured.

    Anything unparseable becomes prose: it can never pass as a claim. Truncated
    JSON is salvaged to its text values so the user never sees braces.
    """
    text = (content or "").strip()
    try:
        data = _extract_json_object(text)
        if isinstance(data, dict) and "segments" in data:
            return AssistantReply.model_validate(data), True
    except (ValueError, ValidationError):
        pass
    if text.startswith("{"):
        text = _salvage_text(text) or text
    return (
        AssistantReply(
            segments=[ReplySegment(kind="prose", text=text or "I have nothing to add yet.", citations=[])],
            suggested_action=None,
        ),
        False,
    )


def parse_reply(content: str | None) -> AssistantReply:
    return _parse_reply_detailed(content)[0]


def _broken_json_reply(reply: ModelReply, parsed_ok: bool) -> bool:
    """The model tried to answer in JSON but the reply was cut off or never parsed."""
    return reply.truncated or (not parsed_ok and (reply.content or "").strip().startswith("{"))


_TRUNCATION_REPAIR = (
    "Your previous reply was cut off before its JSON closed, so none of it could be shown. Reply again to the "
    "same message, in the same JSON shape, in under 250 words. Put detail into the mission draft rather than "
    "into the chat."
)


def _sanitize_mission_id(value: Any) -> str:
    cleaned = _MISSION_ID_CLEAN.sub("-", str(value or "")).strip("-._")
    cleaned = cleaned.lstrip("-._")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"LIB-{uuid.uuid4().hex[:6].upper()}"
    return cleaned[:50]


def parse_draft(content: str | None) -> MissionDraft:
    """Validate the planning stage's JSON with the mission's own constraints."""
    data = _extract_json_object(content or "")
    if not isinstance(data, dict):
        raise ValidationError.from_exception_data("MissionDraft", [])
    data = dict(data)
    data["mission_id"] = _sanitize_mission_id(data.get("mission_id"))
    return MissionDraft.model_validate(data)


# --------------------------------------------------------------------------- prompts


def _turn_system_prompt(project: Project | None) -> str:
    scope = (
        f"Current project: {project.name} ({project.id}). Use search_evidence before any statement "
        "about what this project already holds."
        if project is not None
        else "No project is selected, so there is no corpus to cite: stay in planning mode."
    )
    return (
        "You are the TraceLab Librarian. You help people shape research questions into DeepSearch "
        "missions and you answer questions along the way. Converse freely: general questions get "
        "real answers, and you use world knowledge to suggest angles, narrow a question that is too "
        "broad, and connect dots.\n\n"
        "Provenance rule, never broken: any statement about what THIS project's evidence contains is a "
        "corpus claim and must cite evidence entry ids returned by search_evidence in this turn. If you "
        "cannot cite it, do not assert it. Report an empty search as prose, in your own words.\n\n"
        f"{scope}\n\n"
        "Reply ONLY with one JSON object of this shape:\n"
        '{"segments": [{"kind": "prose" | "corpus_claim", "text": "markdown", '
        '"citations": ["<evidence id>"]}], "suggested_action": "draft_mission" | null}\n'
        "- prose: anything that asserts nothing about the corpus; citations must be empty.\n"
        "- corpus_claim: a statement about this project's evidence; citations must be non-empty and "
        "contain only ids from this turn's search_evidence results.\n"
        "- suggested_action is \"draft_mission\" once the conversation has a clear objective, an "
        "audience, and a picture of what a good answer looks like; otherwise null.\n"
        "Keep each reply under 350 words; a long comparison belongs in the mission, not the chat. Ask one "
        "question at a time when something essential is missing."
    )


def _repair_prompt(violations: Iterable[ProvenanceViolation]) -> str:
    lines = [f"- segment {v.segment_index}: {v.reason}: {v.detail}" for v in violations]
    return (
        "Your reply failed provenance validation:\n"
        + "\n".join(lines)
        + "\nRewrite it as the same JSON shape. Remove or re-cite the failing statements using only "
        "evidence ids returned by search_evidence in this turn, or restate them as prose that "
        "asserts nothing about the corpus."
    )


def _draft_system_prompt() -> str:
    schema = json.dumps(MissionDraft.model_json_schema(), separators=(",", ":"))
    return (
        "You are the TraceLab Librarian, turning a conversation into a DeepSearch research mission. "
        "Output ONLY one JSON object that validates against this schema:\n"
        f"{schema}\n\n"
        "Authoring rules, learned from real runs:\n"
        "- objective: one paragraph stating the research question and why it matters. Name the "
        "specific entities, sources or concepts; the contract compiler anchors research on them.\n"
        "- success_criteria: 3 to 7 items. Each is ONE short, measurable statement under 200 "
        "characters. Long or multi-clause criteria are misread by the compiler as output "
        "formatting rather than research objectives, so split them.\n"
        "- required_entities: names that must appear in the findings. excluded_entities: homonyms "
        "or adjacent topics to rule out.\n"
        "- constraints: source-quality or recency rules, for example \"Prefer sources published in "
        "2025 or 2026\".\n"
        "- deliverable_format: one line describing the report shape.\n"
        "- mission_id: short, uppercase letters, digits, dots or hyphens, for example ONBOARD-1. "
        "title: 3 to 120 characters.\n"
        "- Use only what the conversation established. Do not invent facts about the user's "
        "documents or evidence. Leave optional fields null when the conversation gave nothing."
    )


def _transcript_text(messages: Iterable[TranscriptMessage]) -> str:
    return "\n\n".join(f"{message.role.upper()}: {message.content}" for message in messages)


# --------------------------------------------------------------------------- service


class LibrarianService:
    def __init__(
        self,
        model_factory: Callable[[], Any],
        ledger: EvidenceLedgerService | None = None,
        missions: MissionService | None = None,
    ) -> None:
        self._model_factory = model_factory
        self._model: Any | None = None
        self._ledger = ledger or EvidenceLedgerService()
        self._missions = missions or MissionService()

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._model_factory()
        return self._model

    # ----------------------------------------------------------------- stage A: turn

    def converse(
        self,
        db: Session,
        user: AuthenticatedUser,
        project: Project | None,
        messages: list[TranscriptMessage],
    ) -> TurnResult:
        transcript: list[dict[str, Any]] = [{"role": "system", "content": _turn_system_prompt(project)}]
        transcript.extend({"role": message.role, "content": message.content} for message in messages)
        retrieved: dict[str, LedgerEntry] = {}
        usage = _UsageTotals()
        tools = [SEARCH_EVIDENCE_TOOL] if project is not None else None

        reply = self._run_tool_loop(db, user, project, transcript, tools, retrieved, usage)
        parsed, parsed_ok = _parse_reply_detailed(reply.content)
        if _broken_json_reply(reply, parsed_ok):
            # One concise retry; if that also fails, the salvaged prose is what the user sees.
            transcript.append({"role": "assistant", "content": reply.content or ""})
            transcript.append({"role": "user", "content": _TRUNCATION_REPAIR})
            retry = self.model.complete(transcript, tools=None, max_tokens=TURN_MAX_TOKENS)
            usage.add(retry.usage)
            retried, retried_ok = _parse_reply_detailed(retry.content)
            if not _broken_json_reply(retry, retried_ok):
                reply, parsed = retry, retried
        violations = validate_provenance(parsed, retrieved)
        if violations:
            transcript.append({"role": "assistant", "content": reply.content or ""})
            transcript.append({"role": "user", "content": _repair_prompt(violations)})
            repaired = self.model.complete(transcript, tools=None, max_tokens=TURN_MAX_TOKENS)
            usage.add(repaired.usage)
            parsed = parse_reply(repaired.content)
            violations = validate_provenance(parsed, retrieved)
            if violations:
                parsed = withhold(parsed, violations)

        cited = [
            retrieved[citation]
            for segment in parsed.segments
            for citation in segment.citations
            if citation in retrieved
        ]
        evidence = list({str(entry.id): entry for entry in cited}.values())
        self._record_usage(usage, project, stage="turn", db=db, user=user)
        return TurnResult(
            reply=parsed,
            evidence=evidence,
            withheld_count=len(violations),
            usage=usage.as_dict(),
            model=str(getattr(self.model, "model_name", "")),
        )

    def _run_tool_loop(
        self,
        db: Session,
        user: AuthenticatedUser,
        project: Project | None,
        transcript: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        retrieved: dict[str, LedgerEntry],
        usage: _UsageTotals,
    ) -> ModelReply:
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.model.complete(transcript, tools=tools, max_tokens=TURN_MAX_TOKENS)
            usage.add(reply.usage)
            if not reply.tool_calls:
                return reply
            transcript.append(_assistant_tool_message(reply))
            for call in reply.tool_calls:
                result = self._execute_tool(db, user, project, call.name, call.arguments, retrieved)
                transcript.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)}
                )
        # Rounds exhausted while the model kept asking for tools: force a final answer.
        reply = self.model.complete(transcript, tools=None, max_tokens=TURN_MAX_TOKENS)
        usage.add(reply.usage)
        return reply

    def _execute_tool(
        self,
        db: Session,
        user: AuthenticatedUser,
        project: Project | None,
        name: str,
        arguments: dict[str, Any],
        retrieved: dict[str, LedgerEntry],
    ) -> dict[str, Any]:
        if name != SEARCH_EVIDENCE or project is None:
            return {"error": f"Unknown tool {name!r}." if project is not None else "No project is selected."}
        query = str(arguments.get("query", "") or "").strip()[:4000]
        if not query:
            return {"error": "query is required."}
        # Same scoping the ledger routes apply: the caller's accessible filter, the owning
        # project's owner allow path, and the caller's accessible project set. The Librarian
        # never widens what its user could read directly (criterion 7).
        entries, total = self._ledger.search(
            db,
            project_id=project.id,
            keyword=query,
            session_key=None,
            mission_id=None,
            disposition=None,
            page=1,
            page_size=EVIDENCE_PAGE_SIZE,
            access_filter=evidence_access_filter(user, LedgerEntry, db),
            allowed_project_ids=accessible_project_ids(user, db),
        )
        for entry in entries:
            retrieved[str(entry.id)] = entry
        return {
            "query": query,
            "total": total,
            "entries": [
                {
                    "id": str(entry.id),
                    "claim": entry.claim,
                    "summary": entry.summary,
                    "source_url": entry.source_url,
                    "disposition": entry.disposition,
                }
                for entry in entries
            ],
        }

    # ----------------------------------------------------------------- stage B: draft

    def draft_mission(
        self,
        project: Project,
        messages: list[TranscriptMessage],
        *,
        db: Session | None = None,
        user: AuthenticatedUser | None = None,
    ) -> DraftResult:
        transcript: list[dict[str, Any]] = [
            {"role": "system", "content": _draft_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Destination project: {project.name}.\n\nConversation transcript:\n\n"
                    f"{_transcript_text(messages)}\n\nProduce the mission JSON now."
                ),
            },
        ]
        usage = _UsageTotals()
        reply = self.model.complete(transcript, json_mode=True, max_tokens=DRAFT_MAX_TOKENS)
        usage.add(reply.usage)
        try:
            draft = parse_draft(reply.content)
        except (ValueError, ValidationError) as first_error:
            transcript.append({"role": "assistant", "content": reply.content or ""})
            transcript.append(
                {
                    "role": "user",
                    "content": (
                        f"That draft failed validation:\n{first_error}\n"
                        "Return the corrected JSON object only."
                    ),
                }
            )
            repaired = self.model.complete(transcript, json_mode=True, max_tokens=DRAFT_MAX_TOKENS)
            usage.add(repaired.usage)
            try:
                draft = parse_draft(repaired.content)
            except (ValueError, ValidationError) as second_error:
                self._record_usage(usage, project, stage="draft", db=db, user=user)
                raise LibrarianDraftError(str(second_error)) from second_error

        namespace = _as_mission_namespace(draft)
        preview: dict[str, Any] | None
        preview_error: str | None = None
        try:
            preview = preview_mission_contract(namespace).to_dict()
        except ContractPreviewError as exc:
            preview = None
            preview_error = str(getattr(exc, "detail", None) or exc)
        lint = lint_mission_for_submit(namespace)
        notes = _draft_notes(draft, preview)
        self._record_usage(usage, project, stage="draft", db=db, user=user)
        return DraftResult(
            draft=draft,
            preview=preview,
            preview_error=preview_error,
            lint_errors=[LintViolationOut(**violation.to_dict()) for violation in lint.errors],
            lint_warnings=[LintViolationOut(**violation.to_dict()) for violation in lint.warnings],
            notes=notes,
            usage=usage.as_dict(),
            model=str(getattr(self.model, "model_name", "")),
        )

    # ----------------------------------------------------------------- stage C: create

    def create_mission(self, db: Session, project: Project, draft: MissionDraft) -> tuple[Mission, bool]:
        """Create the draft as a pristine ``draft`` mission. Idempotent on mission_id.

        Decision #517's operational warning: framework replay can re-execute a
        mutating action, so the same draft submitted twice must not create twice.
        """
        try:
            existing = self._missions.get_mission_by_mission_id(db, draft.mission_id)
        except MissionNotFoundError:
            existing = None
        if existing is not None:
            if existing.project_id == project.id and existing.title == draft.title:
                return existing, False
            raise LibrarianConflict(f"Mission id '{draft.mission_id}' already names a different mission.")
        tags = list(dict.fromkeys([*draft.tags, LIBRARIAN_TAG]))
        data = MissionCreate(
            **draft.model_dump(exclude={"tags"}),
            project_id=project.id,
            tags=tags,
            status="draft",
            created_by=LIBRARIAN_AUTHOR,
        )
        return self._missions.create_mission(db, data), True

    # ----------------------------------------------------------------- bookkeeping

    def _record_usage(
        self,
        usage: _UsageTotals,
        project: Project | None,
        *,
        stage: str,
        db: Session | None = None,
        user: AuthenticatedUser | None = None,
    ) -> None:
        totals = usage.as_dict()
        if totals is None:
            return
        if db is not None:
            # METER-0: durable, per-user (decision #522). The cost monitor below is process-local.
            record_librarian_usage(
                db,
                user_id=getattr(user, "user_id", None),
                project_id=project.id if project is not None else None,
                kind=USAGE_KIND_LIBRARIAN_DRAFT if stage == "draft" else USAGE_KIND_LIBRARIAN_TURN,
                model=str(getattr(self.model, "model_name", "unknown")),
                usage=totals,
                requests=usage.calls,
            )
        try:
            get_cost_monitor().track_usage(
                model=str(getattr(self.model, "model_name", "unknown")),
                prompt_tokens=totals["prompt_tokens"],
                completion_tokens=totals["completion_tokens"],
                total_tokens=totals["total_tokens"],
                project_id=str(project.id) if project is not None else None,
                route="librarian",
                metadata={"stage": stage, "calls": usage.calls},
            )
        except Exception:  # pragma: no cover - telemetry must never fail a turn
            logger.warning("Librarian usage could not be recorded", exc_info=True)


def _assistant_tool_message(reply: ModelReply) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": reply.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in reply.tool_calls
        ],
    }


def _as_mission_namespace(draft: MissionDraft) -> SimpleNamespace:
    """A duck-typed mission for the offline compiler and the linter (both read attributes)."""
    return SimpleNamespace(
        **draft.model_dump(),
        context={},
        references=None,
        expected_output_schema=None,
        coverage_thresholds=None,
        validation_thresholds=None,
        max_loops=None,
        min_loops=None,
    )


def _draft_notes(draft: MissionDraft, preview: dict[str, Any] | None) -> list[str]:
    notes: list[str] = []
    if preview is not None:
        schemas = preview.get("deliverable_schemas") or []
        if schemas:
            # LIB-0's defect: the compiler reclassifies long or repetitive criteria as tables.
            notes.append(
                f"{len(schemas)} success criteria compiled as deliverable schemas rather than research "
                "objectives; DeepSearch would format a table instead of gathering evidence for them. "
                "Shorten or split those criteria before running."
            )
    long_criteria = [criterion for criterion in draft.success_criteria if len(criterion) > 200]
    if long_criteria:
        notes.append(
            f"{len(long_criteria)} success criteria exceed 200 characters; shorter criteria compile "
            "more reliably as research objectives."
        )
    if not draft.required_entities:
        notes.append("No required_entities were named; DeepSearch anchors coverage on named entities.")
    return notes
