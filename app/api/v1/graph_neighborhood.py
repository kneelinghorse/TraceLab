"""Human-authenticated, uncached relational graph reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_graph_neighborhood_repository
from app.ports.graph_neighborhood import GraphNeighborhoodRepository, GraphRootError
from app.schemas.graph_neighborhood import GraphNeighborhoodResponse
from app.schemas.navigation_search import NavigationEntityType

router = APIRouter()


@router.get("/neighborhood", response_model=GraphNeighborhoodResponse)
def get_neighborhood(
    response: Response,
    root_type: NavigationEntityType,
    root_id: UUID,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    per_relation_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    max_nodes: Annotated[int, Query(ge=1, le=150)] = 60,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: GraphNeighborhoodRepository = Depends(get_graph_neighborhood_repository),
) -> GraphNeighborhoodResponse:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return repository.neighborhood(
            db, user, root_type=root_type, root_id=root_id, depth=depth,
            per_relation_limit=per_relation_limit, max_nodes=max_nodes,
        )
    except GraphRootError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers={"Cache-Control": "private, no-store"}) from exc
