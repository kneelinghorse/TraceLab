"""Admin endpoints for Qdrant initialization and health checks."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.config import settings
from app.services.qdrant_service import QdrantService, get_qdrant_service

router = APIRouter(tags=["admin"])


def get_admin_qdrant_service() -> QdrantService:
    """Dependency that returns the shared Qdrant service instance."""
    return get_qdrant_service()


def _extract_attr(obj: Any, path: Iterable[str]) -> Any:
    """Safely walk nested attributes, returning None when a value is missing."""
    current = obj
    for attr in path:
        if current is None:
            return None
        current = getattr(current, attr, None)
    return current


@router.post("/init-qdrant")
def init_qdrant_collection(
    write_optimized: bool = Body(
        False,
        embed=True,
        description="Apply write-optimized settings for bulk loads",
    ),
    service: QdrantService = Depends(get_admin_qdrant_service),
) -> Dict[str, Any]:
    """Create the Qdrant collection if missing and ensure payload indexes exist."""

    try:
        service.ensure_collection(write_optimized=write_optimized)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to initialize Qdrant collection '{service.collection_name}': {exc}",
        ) from exc

    return {
        "status": "initialized",
        "collection": service.collection_name,
        "write_optimized": write_optimized,
        "qdrant_url": settings.qdrant_url,
    }


@router.get("/health")
def qdrant_health(service: QdrantService = Depends(get_admin_qdrant_service)) -> Dict[str, Any]:
    """Report Qdrant connectivity and collection readiness."""

    try:
        collections = service.client.get_collections()
        collection_names = [c.name for c in getattr(collections, "collections", [])]
        exists = service.collection_name in collection_names
        info = None
        if exists:
            info = service.client.get_collection(service.collection_name)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Qdrant health check failed: {exc}") from exc

    vector_size = _extract_attr(info, ("config", "params", "vectors", "size")) if info else None
    distance = _extract_attr(info, ("config", "params", "vectors", "distance")) if info else None
    status_value = getattr(info, "status", None)
    if status_value is not None:
        status_value = getattr(status_value, "value", None) or getattr(status_value, "name", None) or str(status_value)
    vectors_count = getattr(info, "vectors_count", None)

    return {
        "status": "healthy" if exists else "collection_missing",
        "collection": service.collection_name,
        "collection_exists": exists,
        "qdrant_url": settings.qdrant_url,
        "expected": {
            "vector_size": service.vector_size,
            "distance": "COSINE",
        },
        "actual": {
            "vector_size": vector_size,
            "distance": str(distance) if distance is not None else None,
            "status": status_value,
            "vectors_count": vectors_count,
        },
    }
