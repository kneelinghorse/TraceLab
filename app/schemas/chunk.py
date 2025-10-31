"""Pydantic schemas for document chunk entities."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentChunkBase(BaseModel):
    """Shared attributes for document chunk operations."""

    document_id: UUID
    chunk_index: int
    content: str
    embedding_id: Optional[str] = None
    token_count: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    prev_chunk_id: Optional[UUID] = None
    next_chunk_id: Optional[UUID] = None


class DocumentChunkCreate(DocumentChunkBase):
    """Payload for creating a document chunk."""

    pass


class DocumentChunkUpdate(BaseModel):
    """Payload for updating a document chunk."""

    chunk_index: Optional[int] = None
    content: Optional[str] = None
    embedding_id: Optional[str] = None
    token_count: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    prev_chunk_id: Optional[UUID] = None
    next_chunk_id: Optional[UUID] = None


class DocumentChunkRead(DocumentChunkBase):
    """Representation of a persisted document chunk."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
