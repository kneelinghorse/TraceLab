"""Pydantic schemas for tagging entities."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TagBase(BaseModel):
    """Shared attributes for tag operations."""

    name: str
    user_id: UUID | None = None
    category: str | None = None
    color: str | None = None
    parent_id: UUID | None = None


class TagCreate(TagBase):
    """Payload for creating a tag."""

    pass


class TagUpdate(BaseModel):
    """Payload for updating a tag."""

    name: str | None = None
    user_id: UUID | None = None
    category: str | None = None
    color: str | None = None
    parent_id: UUID | None = None


class TagRead(TagBase):
    """Representation of a persisted tag with hierarchy support."""

    id: UUID
    children: list[TagRead] | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentTagBase(BaseModel):
    """Shared attributes for document-tag junction operations."""

    document_id: UUID
    tag_id: UUID


class DocumentTagCreate(DocumentTagBase):
    """Payload for creating a document-tag association."""

    pass


class DocumentTagRead(DocumentTagBase):
    """Representation of a persisted document-tag association."""

    model_config = ConfigDict(from_attributes=True)


TagRead.model_rebuild()
