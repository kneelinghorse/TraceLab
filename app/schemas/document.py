"""Pydantic schemas for document entities."""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.schemas.chunk import DocumentChunkRead
    from app.schemas.tag import DocumentTagRead
    from app.schemas.document_status import DocumentProcessingStatusRead


class DocumentBase(BaseModel):
    """Shared attributes for document operations."""

    project_id: UUID
    name: str
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    content: Optional[str] = None
    raw_content: Optional[bytes] = None
    uploaded_at: Optional[datetime] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    source_type: Optional[str] = None
    participant_count: Optional[int] = None
    collection_date: Optional[date] = None
    processed: Optional[bool] = False
    chunked: Optional[bool] = False
    embedded: Optional[bool] = False
    transcription_accuracy: Optional[Decimal] = None
    validation_status: Optional[str] = None


class DocumentCreate(DocumentBase):
    """Payload for creating a document."""

    pass


class DocumentUpdate(BaseModel):
    """Payload for updating a document."""

    project_id: Optional[UUID] = None
    name: Optional[str] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    content: Optional[str] = None
    raw_content: Optional[bytes] = None
    uploaded_at: Optional[datetime] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    source_type: Optional[str] = None
    participant_count: Optional[int] = None
    collection_date: Optional[date] = None
    processed: Optional[bool] = None
    chunked: Optional[bool] = None
    embedded: Optional[bool] = None
    transcription_accuracy: Optional[Decimal] = None
    validation_status: Optional[str] = None


class DocumentRead(DocumentBase):
    """Representation of a persisted document."""

    id: UUID
    chunks: Optional[List["DocumentChunkRead"]] = None
    tags: Optional[List["DocumentTagRead"]] = None
    processing_events: Optional[List["DocumentProcessingStatusRead"]] = None

    model_config = ConfigDict(from_attributes=True)


from app.schemas.chunk import DocumentChunkRead  # noqa: E402
from app.schemas.tag import DocumentTagRead  # noqa: E402
from app.schemas.document_status import DocumentProcessingStatusRead  # noqa: E402

DocumentRead.model_rebuild()
