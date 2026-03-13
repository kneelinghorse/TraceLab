"""Pydantic schemas for Report APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CitationSchema(BaseModel):
    """A citation to a source chunk."""

    chunk_id: str
    document_id: str | None = None
    excerpt: str = Field(default="", description="Brief excerpt from source")


class ReportSourceSchema(BaseModel):
    """A source reference for a report."""

    id: UUID
    report_id: UUID
    source_type: str = Field(description="'collection' or 'chunk'")
    source_id: UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportBase(BaseModel):
    """Common fields for report operations."""

    title: str = Field(..., min_length=1, max_length=255)


class ReportCreate(BaseModel):
    """Payload for creating a new report."""

    title: str = Field(..., min_length=1, max_length=255)
    collection_id: UUID | None = Field(
        default=None,
        description="Collection to synthesize (mutually exclusive with chunk_ids)",
    )
    chunk_ids: list[UUID] | None = Field(
        default=None,
        description="Specific chunks to synthesize (mutually exclusive with collection_id)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Optional project to associate report with",
    )
    prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Custom synthesis prompt",
    )
    format: Literal["summary", "report", "bullets", "markdown"] = Field(
        default="summary",
        description="Output format for synthesis",
    )


class ReportUpdate(BaseModel):
    """Payload for updating report metadata."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["draft", "final"] | None = Field(default=None)


class ReportResponse(BaseModel):
    """Report representation returned by the API."""

    id: UUID
    title: str
    content: str
    citations: list[CitationSchema] = Field(default_factory=list)
    tokens_used: int = 0
    status: str = "draft"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportDetailResponse(ReportResponse):
    """Report with full details including sources."""

    project_id: UUID | None = None
    report_type: str = "summary"
    prompt: str | None = None
    chunk_count: int = 0
    sources: list[ReportSourceSchema] = Field(default_factory=list)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportListItem(BaseModel):
    """Minimal report info for list views."""

    id: UUID
    title: str
    status: str
    report_type: str
    tokens_used: int
    chunk_count: int
    project_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportListResponse(BaseModel):
    """Paginated list of reports."""

    items: list[ReportListItem]
    total: int
    page: int
    page_size: int


class DeleteResponse(BaseModel):
    """Response for delete operations."""

    success: bool
