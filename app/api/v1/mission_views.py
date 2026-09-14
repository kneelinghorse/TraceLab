"""Human-owned saved mission views. Preference writes intentionally remain REST-only."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_mission_view_repository
from app.ports.mission_views import MissionViewRepository
from app.schemas.mission_views import MissionViewCreate, MissionViewList, MissionViewResponse, MissionViewUpdate

router = APIRouter()


@router.get("", response_model=MissionViewList)
def list_views(
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: MissionViewRepository = Depends(get_mission_view_repository),
) -> MissionViewList:
    response.headers["Cache-Control"] = "private, no-store"
    return MissionViewList(items=repository.list(db, user))


@router.post("", response_model=MissionViewResponse, status_code=201)
def create_view(
    data: MissionViewCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: MissionViewRepository = Depends(get_mission_view_repository),
) -> MissionViewResponse:
    try:
        return repository.create(db, user, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{view_id}", response_model=MissionViewResponse)
def update_view(
    view_id: UUID,
    data: MissionViewUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: MissionViewRepository = Depends(get_mission_view_repository),
) -> MissionViewResponse:
    try:
        return repository.update(db, user, view_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{view_id}", status_code=204)
def delete_view(
    view_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: MissionViewRepository = Depends(get_mission_view_repository),
) -> Response:
    try:
        repository.delete(db, user, view_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
