"""Home aggregate and explicit completion review, available to UI and REST agents."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_home_service
from app.schemas.home import HomeResponse, ReviewCompletionRequest
from app.services.home import HomeService

router = APIRouter()


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
