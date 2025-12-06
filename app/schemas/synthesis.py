"""Pydantic schemas for Synthesize API."""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SynthesizeRequest(BaseModel):
    """Request payload for /api/v1/synthesize endpoint.

    Either collection_id OR chunk_ids must be provided (not both).
    """

    collection_id: Optional[UUID] = Field(
        default=None,
        description="UUID of a collection to synthesize entirely",
    )
    chunk_ids: Optional[List[UUID]] = Field(
        default=None,
        description="List of specific chunk UUIDs to synthesize",
    )
    prompt: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Custom instruction for synthesis (default: 'Summarize the following documents')",
    )
    format: Literal["summary", "report", "bullets"] = Field(
        default="summary",
        description="Output format: summary (prose), report (structured), bullets (list)",
    )

    @model_validator(mode="after")
    def validate_source_input(self) -> "SynthesizeRequest":
        """Ensure exactly one of collection_id or chunk_ids is provided."""
        has_collection = self.collection_id is not None
        has_chunks = self.chunk_ids is not None and len(self.chunk_ids) > 0

        if not has_collection and not has_chunks:
            raise ValueError("Either collection_id or chunk_ids must be provided.")
        if has_collection and has_chunks:
            raise ValueError("Provide either collection_id or chunk_ids, not both.")

        return self


class CitationInfo(BaseModel):
    """Citation reference back to source chunk."""

    chunk_id: UUID = Field(description="UUID of the source chunk")
    document_name: Optional[str] = Field(
        default=None,
        description="Name of the source document",
    )
    excerpt: str = Field(
        description="First ~100 characters of the chunk content",
    )


class SynthesizeResponse(BaseModel):
    """Response payload for /api/v1/synthesize endpoint."""

    content: str = Field(description="Generated markdown content with inline citations")
    citations: List[CitationInfo] = Field(
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
