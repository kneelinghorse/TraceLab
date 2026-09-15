"""Recent activity stream, its new-item summary and per-item viewed marks."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_activity_service
from app.schemas.activity import ActivityPage, ActivitySummary, MarkViewedRequest, MarkViewedResponse
from app.services.activity import ActivityService

router = APIRouter()


@router.get("", response_model=ActivityPage)
def list_activity(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ActivityService = Depends(get_activity_service),
) -> ActivityPage:
    response.headers["Cache-Control"] = "private, no-store"
    return service.page(db, user, page=page, page_size=page_size)


@router.get("/summary", response_model=ActivitySummary)
def activity_summary(
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ActivityService = Depends(get_activity_service),
) -> ActivitySummary:
    response.headers["Cache-Control"] = "private, no-store"
    return service.summary(db, user)


@router.put("/viewed", response_model=MarkViewedResponse)
def mark_viewed(
    request: MarkViewedRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ActivityService = Depends(get_activity_service),
) -> MarkViewedResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return service.mark_viewed(db, user, request.items)
