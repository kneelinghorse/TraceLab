"""Collection CRUD and item management endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.collection import (
    CollectionCreate,
    CollectionDetailResponse,
    CollectionItemCreate,
    CollectionItemResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdate,
)
from app.services.collection import CollectionService, get_collection_service

router = APIRouter()


def _build_collection_response(collection, service: CollectionService) -> CollectionResponse:
    """Build a CollectionResponse with item count."""
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        item_count=service.get_item_count(collection.id),
    )


def _build_item_response(item) -> CollectionItemResponse:
    """Build a CollectionItemResponse with chunk preview."""
    chunk_content = None
    document_id = None
    if item.chunk:
        # Truncate content for preview
        chunk_content = item.chunk.content[:200] if item.chunk.content else None
        document_id = item.chunk.document_id
    return CollectionItemResponse(
        id=item.id,
        collection_id=item.collection_id,
        chunk_id=item.chunk_id,
        notes=item.notes,
        added_at=item.added_at,
        chunk_content=chunk_content,
        document_id=document_id,
    )


@router.get("", response_model=CollectionListResponse)
def list_collections(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionListResponse:
    """Return all collections."""
    entries = service.list_collections()
    payload = [_build_collection_response(entry, service) for entry in entries]
    return CollectionListResponse(data=payload, total=len(payload))


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(
    request: CollectionCreate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    """Create a new collection."""
    try:
        entry = service.create(
            name=request.name,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _build_collection_response(entry, service)


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
def get_collection(
    collection_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionDetailResponse:
    """Get a collection with all its items."""
    entry = service.get(collection_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")

    items = service.get_items(collection_id)
    item_responses = [_build_item_response(item) for item in items]

    return CollectionDetailResponse(
        id=entry.id,
        name=entry.name,
        description=entry.description,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        item_count=len(item_responses),
        items=item_responses,
    )


@router.put("/{collection_id}", response_model=CollectionResponse)
def update_collection(
    collection_id: UUID,
    request: CollectionUpdate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    """Update collection metadata."""
    try:
        entry = service.update(
            collection_id,
            updates=request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return _build_collection_response(entry, service)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> Response:
    """Delete a collection and all its items."""
    deleted = service.delete(collection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{collection_id}/chunks", response_model=CollectionItemResponse, status_code=status.HTTP_201_CREATED)
def add_chunk_to_collection(
    collection_id: UUID,
    request: CollectionItemCreate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionItemResponse:
    """Add a chunk to a collection."""
    try:
        item = service.add_chunk(
            collection_id,
            chunk_id=request.chunk_id,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _build_item_response(item)


@router.delete("/{collection_id}/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chunk_from_collection(
    collection_id: UUID,
    chunk_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: CollectionService = Depends(get_collection_service),
) -> Response:
    """Remove a chunk from a collection."""
    deleted = service.remove_chunk(collection_id, chunk_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found in collection.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
