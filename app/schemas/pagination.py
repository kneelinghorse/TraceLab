"""Reusable pagination schemas for API responses."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from pydantic.generics import GenericModel


class PaginationMeta(BaseModel):
    """Metadata describing the current page within a result set."""

    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, description="Maximum records returned per page")
    total: int = Field(..., ge=0, description="Total number of records available")
    pages: int = Field(
        ..., ge=0, description="Total number of pages for the current filter"
    )


T = TypeVar("T")


class PaginatedResponse(GenericModel, Generic[T]):
    """Standard envelope for paginated list endpoints."""

    data: list[T]
    pagination: PaginationMeta


class ListResponse(GenericModel, Generic[T]):
    """Standard envelope for non-paginated list endpoints."""

    data: list[T]
