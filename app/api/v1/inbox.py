"""Priority inbox reads and the explicit per-user seen watermark (REST/UI only, decision #426)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_inbox_service
from app.schemas.inbox import InboxPage, InboxSection, InboxSeenResponse, InboxSummary, MarkSeenRequest
from app.services.inbox import InboxService

router = APIRouter()


@router.get("/summary", response_model=InboxSummary)
def get_summary(
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: InboxService = Depends(get_inbox_service),
) -> InboxSummary:
    response.headers["Cache-Control"] = "private, no-store"
    return service.summary(db, user)


@router.get("", response_model=InboxPage)
def list_inbox(
    response: Response,
    section: InboxSection = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: InboxService = Depends(get_inbox_service),
) -> InboxPage:
    response.headers["Cache-Control"] = "private, no-store"
    return service.list(db, user, section=section, page=page, page_size=page_size, unread_only=unread_only)


@router.put("/seen", response_model=InboxSeenResponse)
def mark_seen(
    request: MarkSeenRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: InboxService = Depends(get_inbox_service),
) -> InboxSeenResponse:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        seen_through = service.mark_seen(db, user, request.seen_through)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InboxSeenResponse(seen_through=seen_through)
