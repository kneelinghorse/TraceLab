"""Mission relationship context endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.relationships import RelationshipContextResponse
from app.services.relationship_service import (
    MissionRelationshipNotFound,
    RelationshipService,
    RelationshipServiceError,
)

router = APIRouter()
_service = RelationshipService()


@router.get("/{mission_id}/related", response_model=RelationshipContextResponse)
def get_relationship_context(
    mission_id: UUID,
    depth: int = Query(1, ge=1, le=2, description="Traversal depth (1 or 2 hops)"),
    entity_types: list[str] | None = Query(
        default=None,
        description="Subset of entity types to include (documents, insights, chunks, missions)",
    ),
    min_relevance: float | None = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Filter out relationships below this relevance score",
    ),
    db: Session = Depends(get_db),
) -> RelationshipContextResponse:
    """Return relationship context for the specified mission."""

    try:
        return _service.get_relationship_context(
            db,
            mission_id,
            depth=depth,
            entity_types=entity_types,
            min_relevance=min_relevance,
        )
    except MissionRelationshipNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RelationshipServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
