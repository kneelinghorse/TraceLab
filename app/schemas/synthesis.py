"""Pydantic schemas for Synthesize API."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SynthesizeRequest(BaseModel):
    """Request payload for /api/v1/synthesize endpoint.

    Either collection_id OR chunk_ids must be provided (not both).

    Optional: Set save_as_report=true with a report_title to persist
    the synthesis result as a report in a single API call.
    """

    collection_id: UUID | None = Field(
        default=None,
        description="UUID of a collection to synthesize entirely",
    )
    chunk_ids: list[UUID] | None = Field(
        default=None,
        description="List of specific chunk UUIDs to synthesize",
    )
    prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Custom instruction for synthesis (default: 'Summarize the following documents')",
    )
    format: Literal["markdown", "summary", "report", "bullets"] = Field(
        default="markdown",
        description="Output format: markdown (default prose), summary (prose), report (structured), bullets (list)",
    )
    save_as_report: bool = Field(
        default=False,
        description="If true, persist the synthesis result as a report",
    )
    report_title: str | None = Field(
        default=None,
        max_length=255,
        description="Title for the report (required if save_as_report=true)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Project UUID to associate the report with (optional, only used if save_as_report=true)",
    )

    @model_validator(mode="after")
    def validate_source_input(self) -> SynthesizeRequest:
        """Ensure exactly one of collection_id or chunk_ids is provided."""
        has_collection = self.collection_id is not None
        has_chunks = self.chunk_ids is not None and len(self.chunk_ids) > 0

        if not has_collection and not has_chunks:
            raise ValueError("Either collection_id or chunk_ids must be provided.")
        if has_collection and has_chunks:
            raise ValueError("Provide either collection_id or chunk_ids, not both.")

        return self

    @model_validator(mode="after")
    def validate_report_params(self) -> SynthesizeRequest:
        """Ensure report_title is provided when save_as_report is true."""
        if self.save_as_report and not self.report_title:
            raise ValueError("report_title is required when save_as_report is true.")
        return self


class CitationInfo(BaseModel):
    """Citation reference back to source chunk."""

    chunk_id: UUID = Field(description="UUID of the source chunk")
    document_id: UUID | None = Field(
        default=None,
        description="UUID of the source document",
    )
    excerpt: str = Field(
        description="First ~100 characters of the chunk content",
    )


class SynthesizeResponse(BaseModel):
    """Response payload for /api/v1/synthesize endpoint."""

    content: str = Field(description="Generated markdown content with inline citations")
    citations: list[CitationInfo] = Field(
        default_factory=list,
        description="List of source references used in the synthesis",
    )
    tokens_used: int = Field(description="Total tokens consumed by the LLM")
    truncated: bool = Field(
        default=False,
        description="True if input was truncated due to token limits",
    )
    chunk_count: int = Field(
        default=0,
        description="Number of chunks included in synthesis",
    )
    cache_hit: bool = Field(
        default=False,
        description="True if result was served from cache",
    )
    cache_id: str | None = Field(
        default=None,
        description="Cache entry UUID if cached",
    )
    report_id: UUID | None = Field(
        default=None,
        description="UUID of the created report (only present if save_as_report=true)",
    )


class SynthesisCacheStatsResponse(BaseModel):
    """Response payload for /api/v1/synthesis/cache/stats endpoint."""

    total_entries: int = Field(description="Total number of cached syntheses")
    total_hits: int = Field(description="Total cache hits across all entries")
    total_tokens_cached: int = Field(description="Total tokens in cached entries")
    total_tokens_saved: int = Field(
        description="Estimated tokens saved by cache hits (hits * tokens per entry)"
    )
    last_hit_at: str | None = Field(
        default=None,
        description="ISO timestamp of most recent cache hit",
    )
    oldest_entry: str | None = Field(
        default=None,
        description="ISO timestamp of oldest cache entry",
    )
    top_entries: list[dict] = Field(
        default_factory=list,
        description="Top cache entries by hit count",
    )
