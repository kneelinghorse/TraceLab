"""Pydantic schemas for document entities."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.schemas.chunk import DocumentChunkRead
    from app.schemas.document_status import DocumentProcessingStatusRead
    from app.schemas.tag import DocumentTagRead


class DocumentReadBase(BaseModel):
    """Document attributes safe to serialize on every read.

    The extracted text and the original bytes are deliberately absent: reads
    fetch them through ``GET /documents/{id}/content`` and ``/download``.
    """

    project_id: UUID
    name: str
    file_path: str | None = None
    file_type: str | None = None
    uploaded_at: datetime | None = None
    file_size: int | None = None
    mime_type: str | None = None
    source_type: str | None = None
    participant_count: int | None = None
    collection_date: date | None = None
    processed: bool | None = False
    chunked: bool | None = False
    embedded: bool | None = False
    transcription_accuracy: Decimal | None = None
    validation_status: str | None = None


class DocumentBase(DocumentReadBase):
    """Shared attributes for document write operations."""

    content: str | None = None
    raw_content: bytes | None = None


class DocumentCreate(DocumentBase):
    """Payload for creating a document."""

    pass


class DocumentUpdate(BaseModel):
    """Payload for updating a document."""

    project_id: UUID | None = None
    name: str | None = None
    file_path: str | None = None
    file_type: str | None = None
    content: str | None = None
    raw_content: bytes | None = None
    uploaded_at: datetime | None = None
    file_size: int | None = None
    mime_type: str | None = None
    source_type: str | None = None
    participant_count: int | None = None
    collection_date: date | None = None
    processed: bool | None = None
    chunked: bool | None = None
    embedded: bool | None = None
    transcription_accuracy: Decimal | None = None
    validation_status: str | None = None


class DocumentLink(BaseModel):
    """A caller-readable report or mission this document came from."""

    kind: Literal["report", "mission"]
    id: str
    title: str
    href: str


class DocumentRead(DocumentReadBase):
    """Representation of a persisted document (no content or raw bytes)."""

    id: UUID
    chunks: list[DocumentChunkRead] | None = None
    tags: list[DocumentTagRead] | None = None
    processing_events: list[DocumentProcessingStatusRead] | None = None

    # Provenance: where a synthesized or imported document came from
    source_report_id: UUID | None = None
    source_mission_id: UUID | None = None
    source_origin: str | None = None
    links: list[DocumentLink] = []

    # Stats computed from chunks
    chunk_count: int | None = None
    total_tokens: int | None = None
    word_count: int | None = None
    preview: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentContentRead(BaseModel):
    """Full extracted text of one document, fetched on demand."""

    id: UUID
    name: str
    mime_type: str | None = None
    source_origin: str | None = None
    content: str | None = None
    links: list[DocumentLink] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentListItem(BaseModel):
    """Slimmer document view for paginated listings."""

    id: UUID
    project_id: UUID
    name: str
    file_type: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    source_type: str | None = None
    uploaded_at: datetime | None = None
    processed: bool = False
    chunked: bool = False
    embedded: bool = False
    validation_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


from app.schemas.chunk import DocumentChunkRead  # noqa: E402
from app.schemas.document_status import DocumentProcessingStatusRead  # noqa: E402
from app.schemas.tag import DocumentTagRead  # noqa: E402

DocumentRead.model_rebuild()
