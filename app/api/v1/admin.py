"""Admin endpoints for Qdrant operations and the cost monitoring dashboard."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.core.config import settings
from app.services.metrics_aggregator import MetricsAggregator, get_metrics_aggregator
from app.services.qdrant_service import QdrantService, get_qdrant_service

router = APIRouter(tags=["admin"])
_EXPECTED_PAYLOAD_INDEXES = ("project_id", "document_id", "source_type")
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


class PayloadIndexStatus(BaseModel):
    """Pydantic representation of payload index readiness."""

    field: str
    present: bool


class QdrantInitResponse(BaseModel):
    """Response payload returned after initialization attempts."""

    status: Literal["initialized"]
    collection: str
    write_optimized: bool
    qdrant_url: str


class QdrantHealthResponse(BaseModel):
    """Response payload for Qdrant health checks."""

    status: Literal["healthy", "collection_missing"]
    collection: str
    collection_exists: bool
    qdrant_url: str
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    payload_indexes: List[PayloadIndexStatus]


def get_admin_qdrant_service() -> QdrantService:
    """Dependency that returns the shared Qdrant service instance."""
    return get_qdrant_service()


def get_dashboard_aggregator() -> MetricsAggregator:
    """Dependency for the metrics aggregator singleton."""
    return get_metrics_aggregator()


def _extract_attr(obj: Any, path: Iterable[str]) -> Any:
    """Safely walk nested attributes, returning None when a value is missing."""
    current = obj
    for attr in path:
        if current is None:
            return None
        current = getattr(current, attr, None)
    return current


def _payload_indexes(info: Any) -> List[PayloadIndexStatus]:
    """Return readiness information for payload indexes we rely on."""
    payload_schema = getattr(info, "payload_schema", None) if info else None
    schema_dict = payload_schema if isinstance(payload_schema, dict) else {}
    statuses: List[PayloadIndexStatus] = []
    for field in _EXPECTED_PAYLOAD_INDEXES:
        statuses.append(PayloadIndexStatus(field=field, present=field in schema_dict))
    return statuses


@router.post("/init-qdrant", response_model=QdrantInitResponse)
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


@router.get("/health", response_model=QdrantHealthResponse)
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
        "payload_indexes": _payload_indexes(info),
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    aggregator: MetricsAggregator = Depends(get_dashboard_aggregator),
) -> HTMLResponse:
    """Render the monitoring dashboard with the latest metrics."""

    metrics = aggregator.collect()
    auth_header = request.headers.get("authorization", "")
    return _TEMPLATES.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "metrics": metrics, "auth_header": auth_header},
    )


@router.get("/dashboard/data")
def dashboard_data(aggregator: MetricsAggregator = Depends(get_dashboard_aggregator)) -> Dict[str, Any]:
    """Return the dashboard metrics as JSON for auto-refresh."""

    return aggregator.collect()


@router.get("/dashboard/export")
def dashboard_export(
    format: Literal["json", "csv"] = Query("json", description="Export format"),
    aggregator: MetricsAggregator = Depends(get_dashboard_aggregator),
):
    """Export dashboard metrics for archival or sharing."""

    metrics = aggregator.collect()
    if format == "json":
        return metrics

    rows = metrics.get("export_rows", [])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["category", "metric", "value", "unit", "notes"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        io.BytesIO(buffer.read().encode("utf-8")),
        headers={"Content-Disposition": "attachment; filename=dashboard-metrics.csv"},
        media_type="text/csv",
    )
