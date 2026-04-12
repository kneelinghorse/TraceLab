"""Aggregate telemetry, cache, and system health metrics for the admin dashboard."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import engine as db_engine
from app.services.cache_manager import CacheManager, get_cache_manager
from app.services.cache_metrics import cache_metrics
from app.services.cost_monitor import CostMonitor, get_cost_monitor
from app.services.qdrant_service import QdrantService, get_qdrant_service


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    cleaned = value
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(float(ordered[0]), 3)
    rank = (len(ordered) - 1) * (pct / 100)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(float(ordered[int(rank)]), 3)
    lower_value = float(ordered[lower])
    upper_value = float(ordered[upper])
    result = lower_value + (upper_value - lower_value) * (rank - lower)
    return round(result, 3)


@dataclass
class ExportRow:
    category: str
    metric: str
    value: Any
    unit: str | None = None
    notes: str | None = None


class MetricsAggregator:
    """Collects metrics for the admin dashboard from existing services and telemetry."""

    def __init__(
        self,
        *,
        telemetry_path: Path | str | None = None,
        cost_monitor: CostMonitor | None = None,
        cache_manager: CacheManager | None = None,
        semantic_cache_metrics: Any | None = None,
        engine: Engine | None = None,
        qdrant_service_factory: Callable[[], QdrantService] | None = None,
        max_events: int = 5000,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.telemetry_path = (
            Path(telemetry_path)
            if telemetry_path
            else repo_root / "telemetry" / "events" / "sprint-04-performance.jsonl"
        )
        self.cost_monitor = cost_monitor or get_cost_monitor()
        self.cache_manager = cache_manager or get_cache_manager()
        self.semantic_cache_metrics = semantic_cache_metrics or cache_metrics
        self.engine = engine or db_engine
        self._qdrant_service_factory = qdrant_service_factory or get_qdrant_service
        self.max_events = max_events

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def collect(self) -> dict[str, Any]:
        events = self._load_cost_events()
        cost = self._cost_overview(events)
        cache = self._cache_performance()
        query = self._query_performance(events, cache)
        system = self._system_health(events, cache)
        export_rows = self._export_rows(cost, cache, query, system)
        return {
            "generated_at": _utc_now(),
            "cost_overview": cost,
            "cache_performance": cache,
            "query_performance": query,
            "system_health": system,
            "export_rows": [row.__dict__ for row in export_rows],
        }

    # ------------------------------------------------------------------
    # Metric builders
    # ------------------------------------------------------------------
    def _cost_overview(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        summary = self.cost_monitor.summary()
        now = datetime.now(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        windows = {
            "today": self._sum_cost(events, midnight),
            "week": self._sum_cost(events, now - timedelta(days=7)),
            "month": self._sum_cost(events, now - timedelta(days=30)),
        }
        embedding_cost = self._sum_cost(
            events, None, predicate=self._is_embedding_event
        )
        total_cost = round(float(summary.get("totals", {}).get("cost_usd", 0.0)), 6)
        queries = int(summary.get("totals", {}).get("queries", 0))
        avg_cost = round(total_cost / queries, 6) if queries else 0.0
        return {
            "currency": summary.get("currency", "USD"),
            "retention_days": summary.get("retention_days"),
            "totals": summary.get("totals", {}),
            "periods": windows,
            "average_cost_per_query": avg_cost,
            "embedding_cost_usd": embedding_cost,
            "generation_cost_usd": max(total_cost - embedding_cost, 0.0),
            "model_breakdown": self._aggregate_costs(events, key="model"),
            "route_breakdown": self._aggregate_costs(events, key="route"),
            "daily_trend": self._daily_trend(events, days=14),
            "recent_events": [self._simplify_event(event) for event in events[:8]],
        }

    def _cache_performance(self) -> dict[str, Any]:
        snapshot = self.cache_manager.snapshot()
        ttl_caches = [info for _, info in sorted(snapshot.items())]
        semantic = self.semantic_cache_metrics.snapshot()
        ttl_hit_rates = [
            cache.get("hit_rate")
            for cache in ttl_caches
            if isinstance(cache.get("hit_rate"), (int, float))
        ]
        aggregate = {
            "ttl_cache_count": len(ttl_caches),
            "ttl_average_hit_rate": round(mean(ttl_hit_rates), 3)
            if ttl_hit_rates
            else 0.0,
            "semantic_hit_rate": round(float(semantic.get("hit_rate", 0.0)), 3),
            "semantic_evictions": semantic.get("evictions", 0.0),
        }
        return {
            "ttl_caches": ttl_caches,
            "semantic_cache": semantic,
            "aggregate": aggregate,
        }

    def _query_performance(
        self, events: list[dict[str, Any]], cache: dict[str, Any]
    ) -> dict[str, Any]:
        latencies = [
            float(event.get("latency_ms"))
            for event in events
            if isinstance(event.get("latency_ms"), (int, float))
        ]
        now = datetime.now(UTC)
        last_hour = sum(
            1
            for event in events
            if event.get("_ts") and event["_ts"] >= now - timedelta(hours=1)
        )
        slow_queries = [
            self._simplify_event(event)
            for event in sorted(
                events, key=lambda e: float(e.get("latency_ms", 0.0)), reverse=True
            )
            if event.get("latency_ms")
        ]
        semantic_hit = float(cache.get("semantic_cache", {}).get("hit_rate", 0.0))
        ttl_avg = float(cache.get("aggregate", {}).get("ttl_average_hit_rate", 0.0))
        return {
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "p99_latency_ms": _percentile(latencies, 99),
            "average_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
            "requests_last_hour": last_hour,
            "semantic_cache_hit_rate": round(semantic_hit, 3),
            "application_cache_hit_rate": round(ttl_avg, 3),
            "slow_queries": slow_queries[:10],
            "trend": self._daily_latency_trend(events, days=7),
        }

    def _system_health(
        self, events: list[dict[str, Any]], cache: dict[str, Any]
    ) -> dict[str, Any]:
        telemetry_info = {
            "events_available": len(events),
            "source": str(self.telemetry_path),
            "last_event": events[0].get("ts") if events else None,
        }
        return {
            "database": self._database_health(),
            "qdrant": self._qdrant_health(),
            "cache": {
                "ttl_cache_count": cache.get("aggregate", {}).get("ttl_cache_count", 0),
                "semantic_cache_hit_rate": cache.get("semantic_cache", {}).get(
                    "hit_rate", 0.0
                ),
            },
            "telemetry": telemetry_info,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_cost_events(self) -> list[dict[str, Any]]:
        if not self.telemetry_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.telemetry_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_timestamp(payload.get("ts"))
                if ts is None:
                    continue
                payload["_ts"] = ts
                events.append(payload)
        events.sort(key=lambda event: event["_ts"], reverse=True)
        return events[: self.max_events]

    def _sum_cost(
        self,
        events: list[dict[str, Any]],
        threshold: datetime | None,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> float:
        total = 0.0
        for event in events:
            if predicate and not predicate(event):
                continue
            if threshold and event["_ts"] < threshold:
                continue
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                total += float(cost)
        return round(total, 6)

    @staticmethod
    def _is_embedding_event(event: dict[str, Any]) -> bool:
        model = (event.get("model") or "").lower()
        route = (event.get("route") or "").lower()
        if "embedding" in model:
            return True
        return route in {"embedding", "vector"}

    def _aggregate_costs(
        self, events: list[dict[str, Any]], *, key: str
    ) -> list[dict[str, Any]]:
        buckets: dict[str, float] = defaultdict(float)
        for event in events:
            value = event.get(key) or "unknown"
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                buckets[str(value)] += float(cost)
        top = sorted(buckets.items(), key=lambda item: item[1], reverse=True)
        return [
            {
                key: label,
                "cost_usd": round(total, 6),
                "share": round(total / top[0][1], 4) if top and top[0][1] else 0.0,
            }
            for label, total in top
        ]

    def _daily_trend(
        self, events: list[dict[str, Any]], *, days: int
    ) -> list[dict[str, Any]]:
        if not events:
            return []
        buckets: dict[str, float] = defaultdict(float)
        start = datetime.now(UTC) - timedelta(days=days)
        for event in events:
            if event["_ts"] < start:
                continue
            label = event["_ts"].date().isoformat()
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                buckets[label] += float(cost)
        ordered = sorted(buckets.items())
        return [
            {"label": label, "cost_usd": round(total, 6)} for label, total in ordered
        ]

    def _daily_latency_trend(
        self, events: list[dict[str, Any]], *, days: int
    ) -> list[dict[str, Any]]:
        if not events:
            return []
        buckets: dict[str, list[float]] = defaultdict(list)
        start = datetime.now(UTC) - timedelta(days=days)
        for event in events:
            if event["_ts"] < start:
                continue
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)):
                buckets[event["_ts"].date().isoformat()].append(float(latency))
        ordered = sorted(buckets.items())
        return [
            {"label": label, "latency_ms": round(mean(values), 3)}
            for label, values in ordered
        ]

    @staticmethod
    def _simplify_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "ts": event.get("ts"),
            "model": event.get("model"),
            "route": event.get("route"),
            "latency_ms": event.get("latency_ms"),
            "cost_usd": event.get("cost_usd"),
            "cache_hit": event.get("cache_hit"),
            "project_id": event.get("project_id"),
        }

    def _database_health(self) -> dict[str, Any]:
        if self.engine is None:
            return {"status": "unavailable", "error": "Database engine not configured"}
        info: dict[str, Any] = {"engine": str(self.engine.url), "pool_status": None}
        pool = getattr(self.engine, "pool", None)
        if pool is not None:
            status = getattr(pool, "status", None)
            if callable(status):
                info["pool_status"] = status()
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                backend = self.engine.url.get_backend_name()
                info["dialect"] = backend
                if backend.startswith("sqlite"):
                    table_count = connection.execute(
                        text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    )
                    index_count = connection.execute(
                        text("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
                    )
                else:
                    table_count = connection.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')"
                        )
                    )
                    index_count = connection.execute(
                        text(
                            "SELECT COUNT(*) FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')"
                        )
                    )
                info["tables"] = int(table_count.scalar_one())
                info["indexes"] = int(index_count.scalar_one())
                info["status"] = "healthy"
        except Exception as exc:  # pragma: no cover - defensive guardrail
            info["status"] = "unavailable"
            info["error"] = str(exc)
        return info

    def _qdrant_health(self) -> dict[str, Any]:
        try:
            service = self._qdrant_service_factory()
        except (
            Exception
        ) as exc:  # pragma: no cover - qdrant optional in some environments
            return {"status": "unavailable", "error": str(exc)}
        try:
            collections = service.client.get_collections()
            names = [
                getattr(collection, "name", None)
                for collection in getattr(collections, "collections", [])
            ]
            exists = service.collection_name in names
            info = None
            if exists:
                info = service.client.get_collection(service.collection_name)
        except Exception as exc:  # pragma: no cover - remote failure not deterministic
            return {
                "status": "unavailable",
                "collection": service.collection_name,
                "error": str(exc),
            }

        payload_indexes = []
        schema = getattr(info, "payload_schema", None) if info else None
        if isinstance(schema, dict):
            for field in ("project_id", "document_id", "source_type"):
                payload_indexes.append({"field": field, "present": field in schema})

        return {
            "status": "healthy" if exists else "collection_missing",
            "collection": service.collection_name,
            "vector_size": service.vector_size,
            "vectors_count": getattr(info, "vectors_count", None),
            "payload_indexes": payload_indexes,
        }

    def _export_rows(
        self,
        cost: dict[str, Any],
        cache: dict[str, Any],
        query: dict[str, Any],
        system: dict[str, Any],
    ) -> list[ExportRow]:
        rows: list[ExportRow] = []
        periods = cost.get("periods", {})
        for label, value in periods.items():
            rows.append(ExportRow("costs", f"{label}_cost_usd", value, unit="USD"))
        rows.append(
            ExportRow(
                "costs",
                "average_cost_per_query",
                cost.get("average_cost_per_query", 0.0),
                unit="USD",
            )
        )
        rows.append(
            ExportRow(
                "costs",
                "embedding_cost_usd",
                cost.get("embedding_cost_usd", 0.0),
                unit="USD",
            )
        )
        rows.append(
            ExportRow(
                "costs",
                "generation_cost_usd",
                cost.get("generation_cost_usd", 0.0),
                unit="USD",
            )
        )

        rows.append(
            ExportRow(
                "cache",
                "semantic_cache_hit_rate",
                cache.get("semantic_cache", {}).get("hit_rate", 0.0),
            )
        )
        rows.append(
            ExportRow(
                "cache",
                "ttl_average_hit_rate",
                cache.get("aggregate", {}).get("ttl_average_hit_rate", 0.0),
            )
        )

        rows.append(
            ExportRow(
                "performance",
                "p50_latency_ms",
                query.get("p50_latency_ms", 0.0),
                unit="ms",
            )
        )
        rows.append(
            ExportRow(
                "performance",
                "p95_latency_ms",
                query.get("p95_latency_ms", 0.0),
                unit="ms",
            )
        )
        rows.append(
            ExportRow(
                "performance",
                "p99_latency_ms",
                query.get("p99_latency_ms", 0.0),
                unit="ms",
            )
        )
        rows.append(
            ExportRow(
                "performance", "requests_last_hour", query.get("requests_last_hour", 0)
            )
        )

        db = system.get("database", {})
        rows.append(ExportRow("system", "database_status", db.get("status")))
        rows.append(ExportRow("system", "database_tables", db.get("tables")))
        rows.append(ExportRow("system", "database_indexes", db.get("indexes")))

        qdrant = system.get("qdrant", {})
        rows.append(ExportRow("system", "qdrant_status", qdrant.get("status")))
        rows.append(ExportRow("system", "qdrant_vectors", qdrant.get("vectors_count")))

        telemetry = system.get("telemetry", {})
        rows.append(
            ExportRow(
                "system", "telemetry_events", telemetry.get("events_available", 0)
            )
        )
        return rows


_aggregator: MetricsAggregator | None = None


def get_metrics_aggregator() -> MetricsAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = MetricsAggregator()
    return _aggregator


__all__ = ["MetricsAggregator", "get_metrics_aggregator", "ExportRow"]
