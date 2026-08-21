"""PEDR Related Entities API endpoint.

GET /api/v1/pedr/related/{urn} - Get entities related to a given URN.

This endpoint provides graph expansion capabilities, enabling queries like
"show me everything related to this mission".
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids, authorize_or_403
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models import Document, DocumentChunk, Insight, Mission, Project, Report
from app.services.pedr.relational import (
    EntityType,
    RelationType,
    get_relational_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)
INTERNAL_ERROR_DETAIL = "Graph expansion failed due to an internal error."


class RelatedEntityResponse(BaseModel):
    """A single related entity in the response."""

    entity_type: str = Field(
        description="Type of the related entity (project, document, chunk, etc.)"
    )
    entity_id: str = Field(description="UUID of the related entity")
    relation_type: str = Field(
        description="Type of relationship (belongs_to, contains, references, etc.)"
    )
    relation_direction: str = Field(description="Direction: 'outbound' or 'inbound'")
    distance: int = Field(ge=1, description="Number of hops from source entity")
    content_preview: str | None = Field(
        default=None, description="Preview of entity content"
    )
    metadata: dict = Field(default_factory=dict, description="Entity-specific metadata")
    urn: str | None = Field(default=None, description="URN of the related entity")


class GraphExpansionResponse(BaseModel):
    """Response from graph expansion query."""

    source_urn: str = Field(description="URN of the source entity")
    source_entity_type: str = Field(description="Type of the source entity")
    source_entity_id: str = Field(description="UUID of the source entity")
    related_entities: list[RelatedEntityResponse] = Field(
        description="List of related entities"
    )
    total_found: int = Field(ge=0, description="Total related entities found")
    expansion_depth: int = Field(ge=1, description="Maximum traversal depth used")


@router.get("/pedr/related/{urn:path}", response_model=GraphExpansionResponse)
async def get_related_entities(
    urn: str,
    max_depth: int = Query(
        default=2, ge=1, le=5, description="Maximum traversal depth (1-5)"
    ),
    limit: int = Query(
        default=50, ge=1, le=200, description="Maximum related entities to return"
    ),
    include_types: str | None = Query(
        default=None,
        description="Comma-separated entity types to include (project,document,chunk,mission,insight,report)",
    ),
    exclude_types: str | None = Query(
        default=None,
        description="Comma-separated entity types to exclude",
    ),
    relation_types: str | None = Query(
        default=None,
        description="Comma-separated relation types to follow (belongs_to,contains,references,derived_from,sibling_of,related_to)",
    ),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> GraphExpansionResponse:
    """Get entities related to the given URN.

    Performs breadth-first graph traversal from the source entity,
    collecting related entities up to max_depth hops away.

    The URN format is: urn:research:{type}:{id}
    Examples:
    - urn:research:mission:550e8400-e29b-41d4-a716-446655440000
    - urn:research:chunk:123e4567-e89b-12d3-a456-426614174000
    - urn:research:project:f47ac10b-58cc-4372-a567-0e02b2c3d479

    Args:
        urn: URN of the source entity.
        max_depth: Maximum traversal depth (default 2).
        limit: Maximum total related entities to return.
        include_types: Comma-separated entity types to include.
        exclude_types: Comma-separated entity types to exclude.
        relation_types: Comma-separated relation types to follow.

    Returns:
        GraphExpansionResponse with related entities.
    """
    # Validate URN format
    if not urn.startswith("urn:research:"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URN format. Expected urn:research:{{type}}:{{id}}, got: {urn}",
        )

    # Parse include_types
    parsed_include_types: list[EntityType] | None = None
    if include_types:
        try:
            parsed_include_types = [
                EntityType(t.strip().lower())
                for t in include_types.split(",")
                if t.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type in include_types: {e}",
            ) from e

    # Parse exclude_types
    parsed_exclude_types: list[EntityType] | None = None
    if exclude_types:
        try:
            parsed_exclude_types = [
                EntityType(t.strip().lower())
                for t in exclude_types.split(",")
                if t.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type in exclude_types: {e}",
            ) from e

    # Parse relation_types
    parsed_relation_types: list[RelationType] | None = None
    if relation_types:
        try:
            parsed_relation_types = [
                RelationType(t.strip().lower())
                for t in relation_types.split(",")
                if t.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid relation type in relation_types: {e}",
            ) from e

    service = get_relational_service()
    try:
        source_type, source_id = service.parse_urn(urn)
        source_uuid = UUID(source_id)
    except ValueError as e:
        logger.warning("Invalid URN: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e

    resource_models = {
        EntityType.PROJECT: Project,
        EntityType.DOCUMENT: Document,
        EntityType.MISSION: Mission,
        EntityType.INSIGHT: Insight,
        EntityType.REPORT: Report,
    }
    if source_type == EntityType.CHUNK:
        chunk = db.get(DocumentChunk, source_uuid)
        resource = db.get(Document, chunk.document_id) if chunk is not None else None
    else:
        resource = db.get(resource_models[source_type], source_uuid)

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail=f"{source_type.value.capitalize()} {source_uuid} not found",
        )

    authorize_or_403(current_user, "read", resource, db)
    allowed_project_ids = accessible_project_ids(current_user, db)

    try:
        result = service.get_related(
            urn,
            max_depth=max_depth,
            limit=limit,
            include_types=parsed_include_types,
            exclude_types=parsed_exclude_types,
            relation_types=parsed_relation_types,
            session=db,
            allowed_project_ids=allowed_project_ids,
        )

        logger.info(
            "Graph expansion completed: urn=%s, found=%d, depth=%d, user=%s",
            urn,
            result.total_found,
            max_depth,
            current_user.username,
        )

        # Convert to response model
        related_entities = [
            RelatedEntityResponse(
                entity_type=e.entity_type.value,
                entity_id=e.entity_id,
                relation_type=e.relation_type.value,
                relation_direction=e.relation_direction,
                distance=e.distance,
                content_preview=e.content_preview,
                metadata=e.metadata,
                urn=e.urn,
            )
            for e in result.related_entities
        ]

        return GraphExpansionResponse(
            source_urn=result.source_urn,
            source_entity_type=result.source_entity_type.value,
            source_entity_id=result.source_entity_id,
            related_entities=related_entities,
            total_found=result.total_found,
            expansion_depth=result.expansion_depth,
        )

    except ValueError as e:
        logger.warning("Invalid URN or parameters: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Graph expansion failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=INTERNAL_ERROR_DETAIL,
        ) from e


__all__ = ["router"]
