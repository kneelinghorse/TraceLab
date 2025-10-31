"""Pydantic schemas for tagging entities."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TagBase(BaseModel):
    """Shared attributes for tag operations."""

    name: str
    user_id: Optional[UUID] = None
    category: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[UUID] = None


class TagCreate(TagBase):
    """Payload for creating a tag."""

    pass


class TagUpdate(BaseModel):
    """Payload for updating a tag."""

    name: Optional[str] = None
    user_id: Optional[UUID] = None
    category: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[UUID] = None


class TagRead(TagBase):
    """Representation of a persisted tag with hierarchy support."""

    id: UUID
    children: Optional[List["TagRead"]] = None

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
