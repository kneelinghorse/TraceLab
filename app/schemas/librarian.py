"""Request and response shapes for the Librarian (LIB-1).

The transcript is client-held and resent on every call: there is no
conversation table (decision #519). Every assistant reply is a list of typed
segments so the UI can render world knowledge and corpus claims differently,
which is the integrity guarantee decision #513 leaves load-bearing.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.mission import MissionBase, MissionResponse

TranscriptRole = Literal["user", "assistant"]
SegmentKind = Literal["prose", "corpus_claim", "withheld"]
SuggestedAction = Literal["draft_mission"]
TurnMode = Literal["converse", "answer"]

MAX_TRANSCRIPT_MESSAGES = 60
# The answer budget's bounds: RagQuery's floor, and twice the page's full synthesis.
ANSWER_MIN_TOKENS = 64
ANSWER_MAX_TOKENS = 4000


class TranscriptMessage(BaseModel):
    role: TranscriptRole
    content: str = Field(min_length=1, max_length=20_000)


class ReplySegment(BaseModel):
    """One span of an assistant reply.

    ``prose`` asserts nothing about the corpus and may use world knowledge freely.
    ``corpus_claim`` is a statement about what the project's evidence contains and
    must cite evidence entries retrieved in the same turn. ``withheld`` marks a
    claim the server refused to render because its provenance did not hold.
    """

    kind: SegmentKind = "prose"
    text: str = Field(default="", max_length=20_000)
    citations: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> Any:
        if isinstance(value, str):
            lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
            if lowered in {"claim", "corpus", "corpus_claim", "evidence"}:
                return "corpus_claim"
            if lowered in {"prose", "text", "general", "planning", "answer"}:
                return "prose"
            return lowered
        return value

    @field_validator("citations", mode="before")
    @classmethod
    def _coerce_citations(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:20]


class AssistantReply(BaseModel):
    segments: list[ReplySegment] = Field(default_factory=list, max_length=50)
    suggested_action: SuggestedAction | None = None

    @field_validator("suggested_action", mode="before")
    @classmethod
    def _normalize_action(cls, value: Any) -> Any:
        if isinstance(value, str):
            lowered = value.strip().lower()
            return "draft_mission" if lowered in {"draft_mission", "draft", "mission"} else None
        return None


class TurnRequest(BaseModel):
    project_id: UUID | None = Field(
        default=None,
        description="Project whose evidence the Librarian may search. Omit for planning-only conversation.",
    )
    messages: list[TranscriptMessage] = Field(min_length=1, max_length=MAX_TRANSCRIPT_MESSAGES)
    mode: TurnMode = Field(
        default="converse",
        description=(
            "converse: the Librarian talks it through (LIB-1). answer: the last message is a question "
            "answered from the project's documents with citations, or refused (QA-1)."
        ),
    )
    max_tokens: int | None = Field(
        default=None,
        ge=ANSWER_MIN_TOKENS,
        le=ANSWER_MAX_TOKENS,
        description="Answer budget for mode 'answer'. Defaults to settings.rag_default_max_tokens.",
    )

    @model_validator(mode="after")
    def _last_message_is_from_user(self) -> TurnRequest:
        if self.messages[-1].role != "user":
            raise ValueError("The last transcript message must be from the user.")
        return self

    @model_validator(mode="after")
    def _answer_mode_fields(self) -> TurnRequest:
        if self.mode == "answer":
            if self.project_id is None:
                raise ValueError("Mode 'answer' needs a project_id: a question is answered from one project.")
            if not self.messages[-1].content.strip():
                raise ValueError("The question must not be empty.")
        elif self.max_tokens is not None:
            raise ValueError("max_tokens applies only to mode 'answer'.")
        return self


class EvidenceRef(BaseModel):
    """An evidence entry the Librarian consulted this turn, as the UI resolves it."""

    id: UUID
    claim: str
    source_url: str
    disposition: str
    href: str


class ChunkRef(BaseModel):
    """A document chunk an answer cites, as the UI resolves it (QA-1)."""

    id: str
    document_id: str
    document_name: str
    chunk_index: int | None = None
    snippet: str | None = None
    href: str


class TurnResponse(BaseModel):
    segments: list[ReplySegment]
    suggested_action: SuggestedAction | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    chunks: list[ChunkRef] = Field(default_factory=list)
    no_evidence: bool = Field(
        default=False,
        description="True when an answer turn was refused: nothing in the project answers the question.",
    )
    withheld_count: int = 0
    usage: dict[str, int] | None = None
    model: str


class MissionDraft(MissionBase):
    """The planning stage's output: the authoring fields a mission needs, nothing operational.

    Inherits mission_id, title, objective and success_criteria with the exact
    validators MissionCreate applies, so a draft that validates here creates
    unmodified.
    """

    background: str | None = None
    focus: str | None = None
    required_entities: list[str] | None = None
    excluded_entities: list[str] | None = None
    constraints: list[str] | None = None
    deliverable_format: str | None = None
    deliverables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator(
        "required_entities", "excluded_entities", "constraints", "deliverables", "tags", mode="before"
    )
    @classmethod
    def _clean_string_lists(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value


class DraftRequest(BaseModel):
    project_id: UUID
    messages: list[TranscriptMessage] = Field(min_length=1, max_length=MAX_TRANSCRIPT_MESSAGES)


class LintViolationOut(BaseModel):
    rule: str
    field: str | None = None
    message: str
    suggestion: str | None = None


class DraftResponse(BaseModel):
    draft: MissionDraft
    preview: dict[str, Any] | None = None
    preview_error: str | None = None
    lint_errors: list[LintViolationOut] = Field(default_factory=list)
    lint_warnings: list[LintViolationOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    usage: dict[str, int] | None = None
    model: str


class CreateFromDraftRequest(BaseModel):
    project_id: UUID
    draft: MissionDraft


class CreatedMissionResponse(BaseModel):
    mission: MissionResponse
    created: bool
