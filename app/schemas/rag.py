"""Schemas for RAG query requests and responses."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.librarian import ANSWER_MAX_TOKENS, ANSWER_MIN_TOKENS
from app.schemas.retrieval import RetrievalQuery, RetrievedChunk


class RagQuery(RetrievalQuery):
    """Client payload for full RAG query execution."""

    search_mode: Literal["semantic", "keyword", "hybrid"] = Field(
        default="semantic",
        description="Select semantic (vector), keyword (full-text), or hybrid search.",
    )
    max_tokens: int = Field(
        default=350,
        ge=64,
        le=1024,
        description="Maximum number of tokens to generate in the answer.",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for answer generation.",
    )


class RagCitation(BaseModel):
    """Structured citation extracted from the generated answer."""

    document_id: str | None
    chunk_id: str | None
    chunk_index: int | None
    source_type: str | None = None
    score: float | None = None
    snippet: str | None = None


class CompressionMetrics(BaseModel):
    """Observability metrics for context compression."""

    original_chunks: int
    filtered_chunks: int
    original_tokens: int
    filtered_tokens: int
    reduction_ratio: float
    threshold: float
    compression_ms: float


class CacheInfo(BaseModel):
    """Metadata describing semantic cache evaluation."""

    hit: bool
    score: float | None = None
    age_seconds: float | None = None
    ttl_seconds: float | None = None


class QualityPillarScores(BaseModel):
    """Breakdown of the heuristic pillar scores."""

    linguistic_uncertainty: float
    answer_integrity: float
    source_provenance: float


class QualityReport(BaseModel):
    """Composite quality assessment report."""

    composite_score: float
    threshold: float
    pillar_scores: QualityPillarScores
    hard_failures: list[str]
    reasons: list[str]
    pre_escalation_score: float | None = None


class RoutingAttempt(BaseModel):
    """Metadata describing a single routing attempt."""

    model: str
    quality_score: float
    below_threshold: bool
    hard_failures: list[str]
    citation_count: int


class RoutingMetrics(BaseModel):
    """Simple counters tracking routing behaviour."""

    total_queries: int
    escalations: int


class RoutingDetails(BaseModel):
    """Routing outcome including whether escalation occurred."""

    selected_model: str
    escalated: bool
    attempts: list[RoutingAttempt]
    estimated_cost_usd: float
    metrics: RoutingMetrics


class RagResponse(BaseModel):
    """Response containing the generated answer alongside supporting metadata."""

    answer: str
    citations: list[RagCitation]
    sources: list[RetrievedChunk]
    latency_ms: float
    compression: CompressionMetrics
    cache: CacheInfo
    quality: QualityReport
    routing: RoutingDetails
    search_mode: Literal["semantic", "keyword", "hybrid"]
    no_evidence: bool = Field(
        default=False,
        description=(
            "True when nothing in scope was retrieved: the model was not asked, "
            "the answer says so, and citations is empty."
        ),
    )


class AskRequest(BaseModel):
    """A question about one project's documents (MCP-6: the MCP's tracelab_search ask)."""

    project_id: UUID = Field(description="The project whose documents answer the question.")
    question: str = Field(min_length=1, max_length=20_000, description="The question, as the Librarian takes it.")
    max_tokens: int | None = Field(
        default=None,
        ge=ANSWER_MIN_TOKENS,
        le=ANSWER_MAX_TOKENS,
        description="Answer budget. Defaults to settings.rag_default_max_tokens.",
    )

    @field_validator("question")
    @classmethod
    def _question_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The question must not be empty.")
        return value


class AskPassage(BaseModel):
    """One paragraph of an answer and the chunk ids it cites; empty when uncited."""

    text: str
    citations: list[str]


class AskCitation(BaseModel):
    """A chunk the answer cites, and the page that opens it."""

    chunk_id: str
    document_id: str
    document_name: str
    chunk_index: int | None = None
    snippet: str | None = None
    href: str


class AskResponse(BaseModel):
    """A cited answer from corpus_qa.answer_question, or its refusal (no_evidence)."""

    answer: str
    passages: list[AskPassage]
    citations: list[AskCitation]
    no_evidence: bool
    model: str | None = None
