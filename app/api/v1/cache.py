"""Cache management endpoints for stats and invalidation."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.cache_manager import get_cache_manager

router = APIRouter()
_cache_manager = get_cache_manager()


class CacheInfo(BaseModel):
    name: str
    ttl_seconds: float
    maxsize: int
    size: int
    hits: float
    misses: float
    sets: float
    invalidations: float
    hit_rate: float = Field(ge=0.0, le=1.0)
    last_event_ts: str | None


class CacheStatsResponse(BaseModel):
    caches: dict[str, CacheInfo]


class CacheClearRequest(BaseModel):
    caches: list[str] | None = Field(
        default=None,
        description="Subset of cache names to clear. Clears all caches when omitted.",
    )


class CacheClearResponse(CacheStatsResponse):
    cleared: dict[str, int]


@router.get("/stats", response_model=CacheStatsResponse)
def cache_stats() -> CacheStatsResponse:
    """Return TTL cache statistics and optionally log them to telemetry."""
    snapshot = _cache_manager.snapshot(log=True)
    cache_payload = {name: CacheInfo(**info) for name, info in snapshot.items()}
    return CacheStatsResponse(caches=cache_payload)


@router.post("/clear", response_model=CacheClearResponse)
def clear_cache(request: CacheClearRequest) -> CacheClearResponse:
    """Clear cache buckets and return the updated statistics."""
    cleared = _cache_manager.clear(request.caches)
    snapshot = _cache_manager.snapshot(log=True)
    cache_payload = {name: CacheInfo(**info) for name, info in snapshot.items()}
    return CacheClearResponse(cleared=cleared, caches=cache_payload)
