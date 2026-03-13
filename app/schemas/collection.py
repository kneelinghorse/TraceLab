"""Pydantic schemas for Collection and CollectionItem APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectionItemBase(BaseModel):
    """Base fields for collection items."""

    chunk_id: UUID
    notes: str | None = Field(default=None, max_length=2000)


class CollectionItemCreate(CollectionItemBase):
    """Payload for adding a chunk to a collection."""

    pass


class CollectionItemResponse(CollectionItemBase):
    """Representation of a collection item returned by the API."""

    id: UUID
    collection_id: UUID
    added_at: datetime
    # Include chunk preview for convenience
    chunk_content: str | None = Field(
        default=None, description="Preview of chunk content"
    )
    document_id: UUID | None = Field(default=None, description="Source document ID")

    model_config = ConfigDict(from_attributes=True)


class CollectionBase(BaseModel):
    """Common fields for collection operations."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CollectionCreate(CollectionBase):
    """Payload for creating a new collection."""

    pass


class CollectionUpdate(BaseModel):
    """Payload for updating collection metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CollectionResponse(CollectionBase):
    """Collection representation returned by the API."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    item_count: int = Field(default=0, description="Number of chunks in collection")

    model_config = ConfigDict(from_attributes=True)


class CollectionDetailResponse(CollectionResponse):
    """Collection with full list of items for detail view."""

    items: list[CollectionItemResponse] = Field(default_factory=list)


class CollectionListResponse(BaseModel):
    """Response for listing collections."""

    data: list[CollectionResponse]
    total: int
