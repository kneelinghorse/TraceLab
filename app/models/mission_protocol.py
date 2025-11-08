"""Pydantic models that define the Mission Protocol contract."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MissionStatus = Literal["draft", "in_progress", "review", "complete"]
KeyQuestionStatus = Literal["open", "researching", "answered"]
QualityGateName = Literal[
    "research_statement",
    "evidence_links",
    "contradictions_resolved",
    "synthesis_quality",
    "traceability",
]
QualityGateStatus = Literal["pending", "pass", "fail"]

REQUIRED_COMPLETION_GATES: tuple[QualityGateName, ...] = (
    "research_statement",
    "evidence_links",
    "synthesis_quality",
    "traceability",
    "contradictions_resolved",
)


class ResearchStatement(BaseModel):
    """Defines the hypothesis and guardrails for a mission."""

    topic: str = Field(..., min_length=1, description="Primary research topic")
    objective: str = Field(..., min_length=1, description="Desired business or research outcome")
    scope: str = Field(..., min_length=1, description="Boundaries for the research effort")
    audience: Optional[str] = Field(
        default=None,
        description="Intended audience for the insights",
    )
    methodology: Optional[str] = Field(
        default=None,
        description="Primary research methodology or approach",
    )
    success_metrics: List[str] = Field(
        default_factory=list,
        description="Signals that determine if the mission succeeded",
    )
    risks: List[str] = Field(
        default_factory=list,
        description="Known risks or assumptions that require tracking",
    )

    model_config = ConfigDict(extra="forbid")


class KeyQuestion(BaseModel):
    """Tracks the status of a core mission question."""

    question: str = Field(..., min_length=1)
    status: KeyQuestionStatus = "open"
    answer: Optional[str] = None
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for answered questions",
    )
    owner: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def ensure_answer_when_closed(self) -> "KeyQuestion":
        """Answered questions must contain a non-empty answer."""
        if self.status == "answered" and not (self.answer and self.answer.strip()):
            raise ValueError("Answered key questions must include an answer.")
        return self


class Evidence(BaseModel):
    """Describes evidence that supports the mission synthesis."""

    evidence_id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    chunk_id: Optional[str] = Field(
        default=None,
        description="Document chunk identifier used for traceability",
    )
    insight_id: Optional[str] = Field(
        default=None,
        description="Insight identifier associated with this evidence (UUID string)",
    )
    source_type: Optional[str] = Field(
        default=None,
        description="Type of source (interview, survey, log, etc.)",
    )
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Synthesis(BaseModel):
    """Synthesised insights derived from the research data."""

    key_insights: List[str] = Field(default_factory=list)
    surprising_findings: List[str] = Field(default_factory=list)
    contradictory_information: List[str] = Field(default_factory=list)
    contradiction_resolutions: List[str] = Field(
        default_factory=list,
        description="Resolution notes for each contradiction or uncertainty",
    )
    recommendations: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class QualityCheckpoint(BaseModel):
    """Represents a single quality gate evaluation."""

    gate: QualityGateName
    status: QualityGateStatus = "pending"
    notes: Optional[str] = None
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")


class ParticipantSegment(BaseModel):
    """Distribution slice used for bias and rigor evaluations."""

    segment: str = Field(..., min_length=1, description="Participant cohort name")
    count: Optional[int] = Field(default=None, ge=0)
    percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Normalized ratio between 0 and 1 (values >1 are interpreted as percentages)",
    )

    model_config = ConfigDict(extra="forbid")


class MethodologyDetails(BaseModel):
    """Operational metadata that powers the quality automation checks."""

    participant_segments: List[ParticipantSegment] = Field(default_factory=list)
    total_participants: Optional[int] = Field(default=None, ge=0)
    recruitment_method: Optional[str] = None
    consent_documented: bool = False
    validation_steps_completed: List[str] = Field(default_factory=list)
    artifacts_verified: List[str] = Field(
        default_factory=list,
        description="Artifacts (scripts, transcripts, datasets) that passed QA",
    )
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class MissionProtocolBase(BaseModel):
    """Shared fields for both draft and complete states."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    mission_id: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0")
    title: Optional[str] = None
    summary: Optional[str] = None
    project_id: Optional[str] = None
    status: MissionStatus = "draft"
    owner: Optional[str] = None
    research_statement: Optional[ResearchStatement] = None
    key_questions: List[KeyQuestion] = Field(default_factory=list)
    synthesis: Optional[Synthesis] = None
    evidence: List[Evidence] = Field(default_factory=list)
    quality_checkpoints: List[QualityCheckpoint] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    discussion_guide: List[str] = Field(
        default_factory=list,
        description="Ordered moderator prompts/questions used during sessions",
    )
    methodology_details: Optional[MethodologyDetails] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("mission_id")
    @classmethod
    def strip_mission_id(cls, value: str) -> str:
        """Ensure mission identifiers are persisted without whitespace."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("mission_id cannot be blank.")
        return cleaned

    @model_validator(mode="after")
    def ensure_unique_tags(self) -> "MissionProtocolBase":
        """Tags operate as a set to prevent redundant values."""
        unique_tags = sorted(set(self.tags))
        object.__setattr__(self, "tags", unique_tags)
        return self


class MissionProtocolDraft(MissionProtocolBase):
    """Draft payload that allows partially filled missions."""

    def promote(self) -> "MissionProtocolComplete":
        """Promote a draft payload into the complete state."""
        return MissionProtocolComplete.model_validate(self.model_dump())


class MissionProtocolComplete(MissionProtocolDraft):
    """Complete payload with all required data and quality gates."""

    title: str
    research_statement: ResearchStatement
    synthesis: Synthesis
    status: Literal["review", "complete"] = "complete"

    @model_validator(mode="after")
    def enforce_completion_gates(self) -> "MissionProtocolComplete":
        """Ensure completion-ready payloads honour quality gate requirements."""
        if not self.evidence:
            raise ValueError("Completed missions must reference at least one piece of evidence.")
        if not self.key_questions:
            raise ValueError("Completed missions must document key questions.")
        answered = [question for question in self.key_questions if question.status == "answered"]
        if not answered:
            raise ValueError("At least one key question must be answered before completion.")
        if not self.synthesis.key_insights:
            raise ValueError("Synthesis must include at least one key insight.")
        passed_gates = {checkpoint.gate for checkpoint in self.quality_checkpoints if checkpoint.status == "pass"}
        missing = [gate for gate in REQUIRED_COMPLETION_GATES if gate not in passed_gates]
        if missing:
            raise ValueError(
                f"Missing required quality checkpoints with pass status: {', '.join(missing)}"
            )
        return self
