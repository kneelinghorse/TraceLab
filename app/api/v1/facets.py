"""Faceted search endpoints for filter metadata."""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.faceted_search import FacetFilters, FacetedSearchService

router = APIRouter()


class FacetRequest(BaseModel):
    """Request payload for fetching available facet values."""

    project_id: Optional[UUID] = Field(None, description="Optional project scope for facets.")
    document_types: Optional[List[str]] = Field(None, description="Current document type selections.")
    source_types: Optional[List[str]] = Field(None, description="Current source type selections.")
    date_from: Optional[date] = Field(None, description="Restrict results collected on/after this date.")
    date_to: Optional[date] = Field(None, description="Restrict results collected on/before this date.")
    tags: Optional[List[str]] = Field(None, description="Tag filters currently applied.")


class FacetValue(BaseModel):
    """Single facet option with a display label and occurrence count."""

    value: str
    label: str
    count: int


class DateRangeFacet(BaseModel):
    """Date range facet describing the available collection window."""

    min: Optional[date]
    max: Optional[date]


class FacetResponse(BaseModel):
    """Response payload containing facet values for each supported dimension."""

    projects: List[FacetValue]
    document_types: List[FacetValue]
    source_types: List[FacetValue]
    tags: List[FacetValue]
    date_range: DateRangeFacet


@router.post("/facets", response_model=FacetResponse)
async def fetch_facets(payload: FacetRequest) -> FacetResponse:
    """Return available facet values scoped by the provided filters."""

    service = FacetedSearchService()
    filters = FacetFilters.from_kwargs(
        project_id=str(payload.project_id) if payload.project_id else None,
        document_types=payload.document_types,
        source_types=payload.source_types,
        tags=payload.tags,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    facets = service.get_facets(filters)
    return FacetResponse(
        projects=[FacetValue(**item) for item in facets["projects"]],
        document_types=[FacetValue(**item) for item in facets["document_types"]],
        source_types=[FacetValue(**item) for item in facets["source_types"]],
        tags=[FacetValue(**item) for item in facets["tags"]],
        date_range=DateRangeFacet(**facets["date_range"]),
    )
