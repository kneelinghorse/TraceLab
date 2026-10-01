"""Prometheus-compatible metrics helpers for the semantic cache service."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

try:  # pragma: no cover - prometheus optional
    from prometheus_client import Counter, Histogram
except ModuleNotFoundError:  # pragma: no cover
    Counter = Histogram = None  # type: ignore


class CacheMetrics:
    """Collect and expose semantic cache metrics with in-memory fallbacks."""

    _PROM_METRICS: ClassVar[dict[str, object] | None] = None
    _PROM_LOCK: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        # In-memory counters for quick assertions and local introspection.
        self._lock = threading.Lock()
        self.hit_count = 0
        self.miss_count = 0
        self.error_count = 0
        self.eviction_count = 0
        self._lookup_count = 0
        self._lookup_seconds = 0.0
        self._error_categories: dict[str, dict[str, int]] = {}
        self._last_error_log: dict[tuple[str, str], float] = {}

        metrics = self._get_prometheus_metrics()
        if metrics:
            self._hits = metrics["hits"]
            self._misses = metrics["misses"]
            self._errors = metrics["errors"]
            self._failures = metrics["failures"]
            self._evictions = metrics["evictions"]
            self._lookup_latency = metrics["lookup_latency"]
        else:  # pragma: no cover - instrumentation unavailable
            self._hits = None
            self._misses = None
            self._errors = None
            self._failures = None
            self._evictions = None
            self._lookup_latency = None

    def record_hit(self, project_id: str | None) -> None:
        label = project_id or "unknown"
        with self._lock:
            self.hit_count += 1
        if self._hits:
            self._hits.labels(project_id=label).inc()

    def record_miss(self, project_id: str | None) -> None:
        label = project_id or "unknown"
        with self._lock:
            self.miss_count += 1
        if self._misses:
            self._misses.labels(project_id=label).inc()

    def record_error(self, operation: str = "unknown", category: str = "unknown") -> None:
        # Only this bounded vocabulary may become a log field or metric label.
        if operation not in {"initialize", "lookup", "write", "maintenance"}:
            operation = "unknown"
        if category not in {"timeout", "unavailable", "serialization", "invalid_payload"}:
            category = "unknown"
        now = time.monotonic()
        key = (operation, category)
        with self._lock:
            self.error_count += 1
            counts = self._error_categories.setdefault(operation, {})
            counts[category] = counts.get(category, 0) + 1
            log_error = key not in self._last_error_log or now - self._last_error_log[key] >= 60
            if log_error:
                self._last_error_log[key] = now
        if self._errors:
            self._errors.inc()
        if self._failures:
            self._failures.labels(operation=operation, category=category).inc()
        if log_error:
            logger.warning("Semantic cache failure operation=%s category=%s scope=process_local_since_start", operation, category)

    def record_eviction(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.eviction_count += count
        if self._evictions:
            self._evictions.inc(count)

    def observe_lookup(self, duration_seconds: float) -> None:
        with self._lock:
            self._lookup_count += 1
            self._lookup_seconds += duration_seconds
        if self._lookup_latency:
            self._lookup_latency.observe(duration_seconds)

    def hit_rate(self) -> float:
        """Return the observed cache hit rate."""
        with self._lock:
            total = self.hit_count + self.miss_count
            if total == 0:
                return 0.0
            return self.hit_count / total

    def snapshot(self) -> dict[str, Any]:
        """Take a thread-safe snapshot of counters for diagnostics."""
        with self._lock:
            total = self.hit_count + self.miss_count
            hit_rate = (self.hit_count / total) if total else 0.0
            mean_latency = (
                self._lookup_seconds / self._lookup_count
                if self._lookup_count
                else 0.0
            )
            return {
                "scope": "process_local_since_start",
                "status": "available",
                "error_categories": {operation: dict(counts) for operation, counts in self._error_categories.items()},
                "hits": float(self.hit_count),
                "misses": float(self.miss_count),
                "errors": float(self.error_count),
                "evictions": float(self.eviction_count),
                "hit_rate": hit_rate,
                "avg_lookup_seconds": mean_latency,
            }

    @classmethod
    def _get_prometheus_metrics(cls) -> dict[str, object] | None:
        """Return shared Prometheus collectors, creating them once per process."""
        if not (Counter and Histogram):
            return None
        with cls._PROM_LOCK:
            if cls._PROM_METRICS is None:
                cls._PROM_METRICS = {
                    "hits": Counter(
                        "semantic_cache_hits_total",
                        "Semantic cache hits",
                        ["project_id"],
                    ),
                    "misses": Counter(
                        "semantic_cache_misses_total",
                        "Semantic cache misses",
                        ["project_id"],
                    ),
                    "errors": Counter(
                        "semantic_cache_errors_total", "Semantic cache errors"
                    ),
                    "failures": Counter(
                        "semantic_cache_failures_total", "Semantic cache failures by bounded operation and category", ["operation", "category"]
                    ),
                    "evictions": Counter(
                        "semantic_cache_evictions_total", "Semantic cache evictions"
                    ),
                    "lookup_latency": Histogram(
                        "semantic_cache_lookup_latency_seconds",
                        "Semantic cache lookup latency distribution",
                    ),
                }
            return cls._PROM_METRICS


# Global metrics sink used by the semantic cache service.
cache_metrics = CacheMetrics()
