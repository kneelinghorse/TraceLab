"""Collection document membership and a read-only seed for mission authoring."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_collection_context_service
from app.schemas.collection_context import (
    CollectionDocumentAdd,
    CollectionDocumentPage,
    CollectionDocumentRead,
    CollectionMissionSeed,
)
from app.services.collection_context import CollectionContextService

router = APIRouter()


@router.get("/{collection_id}/documents", response_model=CollectionDocumentPage)
def list_documents(
    collection_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionContextService = Depends(get_collection_context_service),
) -> CollectionDocumentPage:
    try:
        return service.documents(db, user, collection_id, page=page, page_size=page_size)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{collection_id}/mission-seed", response_model=CollectionMissionSeed)
def mission_seed(
    collection_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionContextService = Depends(get_collection_context_service),
) -> CollectionMissionSeed:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return service.seed(db, user, collection_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{collection_id}/documents", response_model=CollectionDocumentRead, status_code=201)
def add_document(
    collection_id: UUID,
    request: CollectionDocumentAdd,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionContextService = Depends(get_collection_context_service),
) -> CollectionDocumentRead:
    try:
        return service.attach(db, user, collection_id, request.document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{collection_id}/documents/{document_id}", status_code=204)
def remove_document(
    collection_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionContextService = Depends(get_collection_context_service),
) -> Response:
    try:
        service.detach(db, user, collection_id, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
