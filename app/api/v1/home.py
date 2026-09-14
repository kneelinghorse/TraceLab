"""Home aggregate and explicit completion review, available to UI and REST agents."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_home_service
from app.schemas.home import HomeAttention, HomeRecent, HomeResponse, HomeSection, ReviewCompletionRequest
from app.services.home import HomeService

router = APIRouter()


@router.get("/attention", response_model=HomeAttention)
def get_attention(
    response: Response,
    project_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> HomeAttention:
    response.headers["Cache-Control"] = "private, no-store"
    return service.attention(db, user, project_id=project_id)


@router.get("/favorites", response_model=HomeSection[HomeRecent])
def get_favorites(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=100),
    project_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> HomeSection[HomeRecent]:
    response.headers["Cache-Control"] = "private, no-store"
    return service.favorites(db, user, page=page, page_size=page_size, project_id=project_id)


@router.put("/favorites/projects/{project_id}", status_code=204)
def pin_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> Response:
    try:
        service.set_favorite(db, user, project_id, favorite=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete("/favorites/projects/{project_id}", status_code=204)
def unpin_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> Response:
    service.set_favorite(db, user, project_id, favorite=False)
    return Response(status_code=204)


@router.get("", response_model=HomeResponse)
def get_home(
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> HomeResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return service.snapshot(db, user)


@router.put("/missions/{mission_id}/review", status_code=204)
def review_completion(
    mission_id: UUID,
    request: ReviewCompletionRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: HomeService = Depends(get_home_service),
) -> Response:
    try:
        service.review_completion(db, user, mission_id, request.updated_at)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)
