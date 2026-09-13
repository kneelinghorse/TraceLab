"""Readable document context and its projection into existing mission fields."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CollectionDocumentAdd(BaseModel):
    document_id: UUID


class CollectionDocumentRead(BaseModel):
    id: UUID
    name: str
    project_id: UUID
    file_type: str | None = None
    processed: bool | None = None
    chunked: bool | None = None
    embedded: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class CollectionDocumentPage(BaseModel):
    items: list[CollectionDocumentRead]
    total: int
    page: int
    page_size: int


class CollectionContext(BaseModel):
    id: UUID
    name: str
    instructions: str | None
    documents: list[CollectionDocumentRead]


class CollectionMissionSeed(BaseModel):
    collection_id: UUID
    title: str
    project_id: UUID | None
    background: str
    references: list[dict[str, str]]
    context: dict[str, Any]
