"""Pydantic schemas for document processing status entries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentProcessingStatusBase(BaseModel):
    """Shared attributes for processing status operations."""

    document_id: UUID
    stage: str
    status: str
    message: str | None = None
    details: dict[str, Any] | None = None


class DocumentProcessingStatusRead(DocumentProcessingStatusBase):
    """Representation of a persisted processing event."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
