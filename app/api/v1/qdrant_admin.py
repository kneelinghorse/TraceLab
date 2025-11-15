"""Dedicated endpoints for Qdrant tuning, stats, and health."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.qdrant_service import QdrantService, get_qdrant_service


router = APIRouter(tags=["qdrant-admin"])
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BENCHMARK_PATH = _REPO_ROOT / "artifacts" / "qdrant_parameter_sweep.json"


def get_qdrant_admin_service() -> QdrantService:
    """Dependency hook so tests can override the Qdrant service."""

    return get_qdrant_service()


class HnswStatus(BaseModel):
    """Serialized view of current HNSW configuration."""

    m: Optional[int] = None
    ef_construct: Optional[int] = None
    full_scan_threshold: Optional[int] = None
    on_disk: Optional[bool] = None


class QuantizationStatus(BaseModel):
    """Quantization readiness information."""

    enabled: bool
    type: Optional[str] = None
    always_ram: Optional[bool] = None
    quantile: Optional[float] = None


class MemoryProfile(BaseModel):
    """Memory estimate for the collection footprint."""

    estimate_bytes: int
    estimate_gb: float
    limit_gb: float = Field(2.5, description="Hard memory budget for 500K vectors in RAM")


class QdrantStatsResponse(BaseModel):
    """Detailed stats payload returned by the /stats endpoint."""

    collection: str
    collection_exists: bool
    points_count: int
    vectors_count: int
    payload_indexes: List[Dict[str, Any]]
    hnsw: HnswStatus
    quantization: QuantizationStatus
    optimizer: Dict[str, Any]
    vector_size: int
    memory: MemoryProfile
    error: Optional[str] = None


class BenchmarkSummary(BaseModel):
    """Latest benchmark output emitted by the parameter sweep script."""

    generated_at: str
    target_latency_ms: float
    recall_threshold: float
    trials: int
    top_k: int
    ef_values: List[int]
    recommendation: Dict[str, Any]


class QdrantHealthResponse(BaseModel):
    """Response payload for runtime health snapshot."""

    status: Literal["healthy", "degraded", "collection_missing"]
    latency_target_ms: float
    recall_target: float
    memory_limit_gb: float
    diagnostics: QdrantStatsResponse
    benchmark: Optional[BenchmarkSummary] = None


class HnswUpdateRequest(BaseModel):
    """Input payload for /config/hnsw updates."""

    m: int = Field(16, ge=4, le=128, description="Graph degree")
    ef_construct: int = Field(100, ge=32, le=512, description="HNSW construction ef")
    full_scan_threshold: int = Field(20_000, ge=1_000, le=5_000_000)
    on_disk: bool = Field(False, description="Persist HNSW graph to disk")
    optimizer_threshold: int = Field(20_000, ge=0, le=5_000_000)
    enable_quantization: bool = Field(True)
    quantile: float = Field(0.99, gt=0, lt=1)
    always_ram: bool = Field(True)


class ConfigUpdateResponse(BaseModel):
    """Payload returned after successfully applying config changes."""

    status: Literal["updated"]
    applied: Dict[str, Any]


def _serialize_stats(service: QdrantService) -> QdrantStatsResponse:
    diagnostics = service.get_collection_diagnostics()
    return QdrantStatsResponse(
        collection=diagnostics["collection"],
        collection_exists=diagnostics["collection_exists"],
        points_count=diagnostics["points_count"],
        vectors_count=diagnostics["vectors_count"],
        payload_indexes=diagnostics["payload_indexes"],
        hnsw=HnswStatus(**diagnostics["hnsw"]),
        quantization=QuantizationStatus(**diagnostics["quantization"]),
        optimizer=diagnostics["optimizer"],
        vector_size=diagnostics["vector_size"],
        memory=MemoryProfile(
            estimate_bytes=diagnostics["memory_estimate_bytes"],
            estimate_gb=diagnostics["memory_estimate_gb"],
        ),
        error=diagnostics.get("error"),
    )


def _load_latest_benchmark() -> Optional[BenchmarkSummary]:
    if not _BENCHMARK_PATH.exists():
        return None
    try:
        payload = json.loads(_BENCHMARK_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    required = {"generated_at", "target_latency_ms", "recall_threshold", "trials", "top_k", "ef_values", "recommendation"}
    if not required.issubset(payload):
        return None
    subset = {key: payload[key] for key in required}
    return BenchmarkSummary(**subset)


@router.get("/stats", response_model=QdrantStatsResponse)
def qdrant_stats(service: QdrantService = Depends(get_qdrant_admin_service)) -> QdrantStatsResponse:
    """Expose current collection stats, indexes, and memory usage."""

    return _serialize_stats(service)


@router.get("/health", response_model=QdrantHealthResponse)
def qdrant_health_snapshot(service: QdrantService = Depends(get_qdrant_admin_service)) -> QdrantHealthResponse:
    """Return consolidated health status with latest benchmark snapshot."""

    stats = _serialize_stats(service)
    latency_target = 10.0
    recall_target = 0.99
    if not stats.collection_exists:
        status: Literal["healthy", "degraded", "collection_missing"] = "collection_missing"
    elif not stats.quantization.enabled or stats.memory.estimate_gb > stats.memory.limit_gb:
        status = "degraded"
    else:
        status = "healthy"

    benchmark = _load_latest_benchmark()
    return QdrantHealthResponse(
        status=status,
        latency_target_ms=latency_target,
        recall_target=recall_target,
        memory_limit_gb=stats.memory.limit_gb,
        diagnostics=stats,
        benchmark=benchmark,
    )


@router.post("/config/hnsw", response_model=ConfigUpdateResponse)
def update_hnsw_config(
    payload: HnswUpdateRequest,
    service: QdrantService = Depends(get_qdrant_admin_service),
) -> ConfigUpdateResponse:
    """Allow runtime adjustments to HNSW/quantization parameters."""

    try:
        service.apply_hnsw_settings(**payload.model_dump())
    except Exception as exc:  # pragma: no cover - requires real Qdrant
        raise HTTPException(status_code=503, detail=f"Failed to update collection: {exc}") from exc

    return ConfigUpdateResponse(status="updated", applied=payload.model_dump())
