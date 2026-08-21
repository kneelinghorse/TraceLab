"""Faceted search endpoints for filter metadata."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.services.faceted_search import FacetedSearchService, FacetFilters

router = APIRouter()


class FacetRequest(BaseModel):
    """Request payload for fetching available facet values."""

    project_id: UUID | None = Field(
        None, description="Optional project scope for facets."
    )
    document_types: list[str] | None = Field(
        None, description="Current document type selections."
    )
    source_types: list[str] | None = Field(
        None, description="Current source type selections."
    )
    date_from: date | None = Field(
        None, description="Restrict results collected on/after this date."
    )
    date_to: date | None = Field(
        None, description="Restrict results collected on/before this date."
    )
    tags: list[str] | None = Field(None, description="Tag filters currently applied.")


class FacetValue(BaseModel):
    """Single facet option with a display label and occurrence count."""

    value: str
    label: str
    count: int


class DateRangeFacet(BaseModel):
    """Date range facet describing the available collection window."""

    min: date | None
    max: date | None


class FacetResponse(BaseModel):
    """Response payload containing facet values for each supported dimension."""

    projects: list[FacetValue]
    document_types: list[FacetValue]
    source_types: list[FacetValue]
    tags: list[FacetValue]
    date_range: DateRangeFacet


@router.post("/facets", response_model=FacetResponse)
async def fetch_facets(
    payload: FacetRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> FacetResponse:
    """Return available facet values scoped by the provided filters."""

    allowed_project_ids = accessible_project_ids(current_user, db)
    service = FacetedSearchService()
    filters = FacetFilters.from_kwargs(
        project_id=str(payload.project_id) if payload.project_id else None,
        document_types=payload.document_types,
        source_types=payload.source_types,
        tags=payload.tags,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    facets = service.get_facets(filters, allowed_project_ids=allowed_project_ids)
    return FacetResponse(
        projects=[FacetValue(**item) for item in facets["projects"]],
        document_types=[FacetValue(**item) for item in facets["document_types"]],
        source_types=[FacetValue(**item) for item in facets["source_types"]],
        tags=[FacetValue(**item) for item in facets["tags"]],
        date_range=DateRangeFacet(**facets["date_range"]),
    )
