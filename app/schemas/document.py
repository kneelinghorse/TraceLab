"""Pydantic schemas for document entities."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.schemas.chunk import DocumentChunkRead
    from app.schemas.document_status import DocumentProcessingStatusRead
    from app.schemas.tag import DocumentTagRead


class DocumentBase(BaseModel):
    """Shared attributes for document operations."""

    project_id: UUID
    name: str
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
    processed: bool | None = False
    chunked: bool | None = False
    embedded: bool | None = False
    transcription_accuracy: Decimal | None = None
    validation_status: str | None = None


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


class DocumentRead(DocumentBase):
    """Representation of a persisted document."""

    id: UUID
    chunks: list[DocumentChunkRead] | None = None
    tags: list[DocumentTagRead] | None = None
    processing_events: list[DocumentProcessingStatusRead] | None = None

    # Stats computed from chunks
    chunk_count: int | None = None
    total_tokens: int | None = None
    word_count: int | None = None
    preview: str | None = None

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
