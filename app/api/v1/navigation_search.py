"""Human-authenticated object-name navigation for the shell palette."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_navigation_search_repository
from app.ports.navigation_search import NavigationSearchRepository
from app.schemas.navigation_search import NavigationEntityType, NavigationSearchResponse

router = APIRouter()


@router.get("/search", response_model=NavigationSearchResponse)
def search_navigation(
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    entity_type: NavigationEntityType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 5,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: NavigationSearchRepository = Depends(get_navigation_search_repository),
) -> NavigationSearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Enter a name to find.")
    response.headers["Cache-Control"] = "private, no-store"
    return repository.search(db, user, query=query, entity_type=entity_type, page=page, page_size=page_size)
