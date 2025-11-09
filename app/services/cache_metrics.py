"""Prometheus-compatible metrics helpers for the semantic cache service."""
from __future__ import annotations

import threading
import time
from typing import Optional

try:  # pragma: no cover - prometheus optional
    from prometheus_client import Counter, Histogram
except ModuleNotFoundError:  # pragma: no cover
    Counter = Histogram = None  # type: ignore


class CacheMetrics:
    """Collect and expose semantic cache metrics with in-memory fallbacks."""

    def __init__(self) -> None:
        # In-memory counters for quick assertions and local introspection.
        self._lock = threading.Lock()
        self.hit_count = 0
        self.miss_count = 0
        self.error_count = 0
        self.eviction_count = 0
        self.lookup_latencies: list[float] = []

        # Optional Prometheus instrumentation.
        if Counter and Histogram:
            self._hits = Counter("semantic_cache_hits_total", "Semantic cache hits", ["project_id"])
            self._misses = Counter("semantic_cache_misses_total", "Semantic cache misses", ["project_id"])
            self._errors = Counter("semantic_cache_errors_total", "Semantic cache errors")
            self._evictions = Counter("semantic_cache_evictions_total", "Semantic cache evictions")
            self._lookup_latency = Histogram(
                "semantic_cache_lookup_latency_seconds",
                "Semantic cache lookup latency distribution",
            )
        else:  # pragma: no cover - instrumentation unavailable
            self._hits = None
            self._misses = None
            self._errors = None
            self._evictions = None
            self._lookup_latency = None

    def record_hit(self, project_id: Optional[str]) -> None:
        label = project_id or "unknown"
        with self._lock:
            self.hit_count += 1
        if self._hits:
            self._hits.labels(project_id=label).inc()

    def record_miss(self, project_id: Optional[str]) -> None:
        label = project_id or "unknown"
        with self._lock:
            self.miss_count += 1
        if self._misses:
            self._misses.labels(project_id=label).inc()

    def record_error(self) -> None:
        with self._lock:
            self.error_count += 1
        if self._errors:
            self._errors.inc()

    def record_eviction(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.eviction_count += count
        if self._evictions:
            self._evictions.inc(count)

    def observe_lookup(self, duration_seconds: float) -> None:
        with self._lock:
            self.lookup_latencies.append(duration_seconds)
        if self._lookup_latency:
            self._lookup_latency.observe(duration_seconds)

    def hit_rate(self) -> float:
        """Return the observed cache hit rate."""
        with self._lock:
            total = self.hit_count + self.miss_count
            if total == 0:
                return 0.0
            return self.hit_count / total

    def snapshot(self) -> dict[str, float]:
        """Take a thread-safe snapshot of counters for diagnostics."""
        with self._lock:
            total = self.hit_count + self.miss_count
            hit_rate = (self.hit_count / total) if total else 0.0
            mean_latency = (
                sum(self.lookup_latencies) / len(self.lookup_latencies)
                if self.lookup_latencies
                else 0.0
            )
            return {
                "hits": float(self.hit_count),
                "misses": float(self.miss_count),
                "errors": float(self.error_count),
                "evictions": float(self.eviction_count),
                "hit_rate": hit_rate,
                "avg_lookup_seconds": mean_latency,
            }


# Global metrics sink used by the semantic cache service.
cache_metrics = CacheMetrics()
