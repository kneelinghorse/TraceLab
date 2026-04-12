"""Monitoring API endpoints for cost and performance telemetry."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.cache_manager import get_cache_manager
from app.services.cache_metrics import cache_metrics
from app.services.cost_monitor import get_cost_monitor
from app.services.rag_service import current_rag_service

router = APIRouter()
_cache_manager = get_cache_manager()


@router.get("/costs", summary="Return aggregated OpenAI cost metrics")
def read_costs() -> dict:
    monitor = get_cost_monitor()
    return monitor.summary()


@router.get(
    "/performance", summary="Return cache, routing, and cost telemetry snapshot"
)
def read_performance() -> dict:
    monitor = get_cost_monitor()
    return {
        "costs": monitor.summary(days=7),
        "cache": cache_metrics.snapshot(),
        "ttl_caches": _cache_manager.snapshot(),
        "routing": _routing_snapshot(),
    }


def _routing_snapshot() -> dict:
    try:
        rag_service = current_rag_service()
    except Exception as exc:  # pragma: no cover - defensive fallback for optional deps
        return {
            "total_queries": 0,
            "escalations": 0,
            "unavailable": str(exc),
        }
    if rag_service is None:
        return {
            "total_queries": 0,
            "escalations": 0,
            "unavailable": "rag_service not initialized",
        }
    return dict(rag_service.routing_metrics)
