"""Request and response schemas for the project evidence ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

LedgerOrigin = Literal["mcp-agent", "deepsearch-worker"]
LedgerDisposition = Literal["supporting", "contradicting", "rejected", "background"]
PromotionTarget = Literal["report", "document"]


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value cannot be empty or whitespace")
    return normalized


def _normalized_tags(value: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in value:
        tag = raw_tag.strip()
        if not tag:
            raise ValueError("tags cannot contain empty values")
        if len(tag) > 64:
            raise ValueError("tags cannot exceed 64 characters")
        if tag not in seen:
            normalized.append(tag)
            seen.add(tag)
    return normalized


class CaptureItem(BaseModel):
    """One source-backed evidence claim in a batch capture request."""

    claim: str = Field(min_length=1, max_length=20_000)
    summary: str | None = Field(default=None, max_length=20_000)
    source_url: AnyHttpUrl
    snippet: str | None = Field(default=None, max_length=20_000)
    query: str | None = Field(default=None, max_length=4_000)
    disposition: LedgerDisposition
    tags: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("claim")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("source_url")
    @classmethod
    def validate_source_url_length(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if len(str(value)) > 4_096:
            raise ValueError("source_url cannot exceed 4096 characters")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _normalized_tags(value)


class CaptureRequest(BaseModel):
    """Atomic batch capture request."""

    project_id: UUID
    mission_id: UUID | None = None
    session_key: str = Field(min_length=1, max_length=255)
    entries: list[CaptureItem] = Field(min_length=1, max_length=100)

    @field_validator("session_key")
    @classmethod
    def validate_session_key(cls, value: str) -> str:
        return _required_text(value)


class NoteUpsertRequest(BaseModel):
    """Full replacement for one project/session keyed working note."""

    project_id: UUID
    mission_id: UUID | None = None
    session_key: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=50_000)
    tags: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("session_key", "content")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _normalized_tags(value)


class LedgerEntryRead(BaseModel):
    """Serialized evidence entry."""

    id: UUID
    project_id: UUID
    mission_id: UUID | None
    session_key: str
    origin: LedgerOrigin
    claim: str
    summary: str | None
    source_url: str
    source_id: UUID
    source_sighting_count: int = Field(ge=1)
    snippet: str | None
    query: str | None
    disposition: LedgerDisposition
    tags: list[str]
    owner_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerNoteRead(BaseModel):
    """Serialized keyed working note."""

    id: UUID
    project_id: UUID
    mission_id: UUID | None
    session_key: str
    note_key: str
    origin: LedgerOrigin
    content: str
    tags: list[str]
    owner_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaptureResponse(BaseModel):
    """Result of an atomic evidence capture."""

    entries: list[LedgerEntryRead]
    count: int


class LedgerListResponse(BaseModel):
    """Paginated ledger entries and working notes."""

    entries: list[LedgerEntryRead]
    notes: list[LedgerNoteRead]
    entry_total: int
    note_total: int
    page: int
    page_size: int


class LedgerSearchResponse(BaseModel):
    """Paginated project-scoped keyword search results."""

    entries: list[LedgerEntryRead]
    total: int
    page: int
    page_size: int


class PromotionRequest(BaseModel):
    """Promote one evidence session to a report or searchable document."""

    project_id: UUID
    session_key: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    target: PromotionTarget = "report"

    @field_validator("session_key")
    @classmethod
    def validate_session_key(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _required_text(value)


class PromotionResponse(BaseModel):
    """Identifiers and counts for a completed promotion."""

    project_id: UUID
    session_key: str
    target: PromotionTarget
    report_id: UUID
    document_id: UUID | None = None
    title: str
    entry_count: int
    note_count: int
    status: Literal["created", "completed"]
