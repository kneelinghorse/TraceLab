"""Pydantic schemas for document chunk entities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentChunkBase(BaseModel):
    """Shared attributes for document chunk operations."""

    document_id: UUID
    chunk_index: int
    content: str
    embedding_id: str | None = None
    token_count: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    prev_chunk_id: UUID | None = None
    next_chunk_id: UUID | None = None


class DocumentChunkCreate(DocumentChunkBase):
    """Payload for creating a document chunk."""

    pass


class DocumentChunkUpdate(BaseModel):
    """Payload for updating a document chunk."""

    chunk_index: int | None = None
    content: str | None = None
    embedding_id: str | None = None
    token_count: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    prev_chunk_id: UUID | None = None
    next_chunk_id: UUID | None = None


class DocumentChunkRead(DocumentChunkBase):
    """Representation of a persisted document chunk."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
