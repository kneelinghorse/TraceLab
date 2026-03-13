"""Cost monitoring service with telemetry exports."""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


DEFAULT_MODEL_PRICING = {
    # USD per 1K tokens. Pricing source: https://openai.com/api/pricing/
    "gpt-5.1": {"prompt": 0.00125, "completion": 0.01000},
    "gpt-5.2": {"prompt": 0.00200, "completion": 0.01600},
}


class CostMonitor:
    """Track OpenAI usage, estimate costs, and emit telemetry."""

    def __init__(
        self,
        *,
        telemetry_path: Path | None = None,
        retention_days: int = 45,
        currency: str = "USD",
        model_pricing: Dict[str, Dict[str, float]] | None = None,
        max_query_chars: int = 120,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.telemetry_path = telemetry_path or (repo_root / "telemetry" / "events" / "sprint-04-performance.jsonl")
        self.retention_days = max(1, retention_days)
        self.currency = currency
        self.model_pricing = model_pricing or dict(DEFAULT_MODEL_PRICING)
        self.max_query_chars = max(40, max_query_chars)
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []

    def track_usage(
        self,
        *,
        model: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        cache_hit: Optional[bool] = None,
        project_id: Optional[str] = None,
        query: Optional[str] = None,
        route: str = "primary",
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        estimated_cost: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record a usage event and append it to telemetry."""

        prompt = max(0, int(prompt_tokens or 0))
        completion = max(0, int(completion_tokens or 0))
        total = max(prompt + completion, int(total_tokens or 0)) if total_tokens is not None else prompt + completion
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        normalized_query = (query or "").strip() or None
        if normalized_query:
            normalized_query = normalized_query[: self.max_query_chars]

        usage_payload = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

        cost = self._estimate_cost(model=model, prompt_tokens=prompt, completion_tokens=completion, fallback=estimated_cost)

        record = {
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "model": model,
            "route": route,
            "usage": usage_payload,
            "cost_usd": round(cost, 6),
            "currency": self.currency,
            "latency_ms": round(latency_ms, 3) if latency_ms is not None else None,
            "cache_hit": cache_hit,
            "project_id": project_id,
            "query": normalized_query,
            "metadata": metadata or None,
        }

        with self._lock:
            self._events.append({"_ts": ts, **record})
            self._prune_locked(now=ts)
        self._append_telemetry(record)
        return {"event": record, "usage": usage_payload, "cost_usd": record["cost_usd"]}

    def record_cache_hit(
        self,
        *,
        latency_ms: float,
        project_id: Optional[str],
        query: str,
    ) -> None:
        """Log a cache hit with zero cost."""

        self.track_usage(
            model="semantic-cache",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            cache_hit=True,
            project_id=project_id,
            query=query,
            route="cache",
            estimated_cost=0.0,
        )

    def summary(self, *, days: int = 30, months: int = 3) -> Dict[str, Any]:
        """Return aggregated statistics for dashboards and APIs."""

        snapshot: List[Dict[str, Any]]
        with self._lock:
            snapshot = list(self._events)

        totals = self._aggregate_totals(snapshot)
        daily = self._group_by_day(snapshot, limit=days)
        monthly = self._group_by_month(snapshot, limit=months)
        recent = self._recent_events(snapshot, limit=10)

        return {
            "currency": self.currency,
            "retention_days": self.retention_days,
            "totals": totals,
            "daily": daily,
            "monthly": monthly,
            "recent": recent,
        }

    def _aggregate_totals(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not events:
            return {
                "queries": 0,
                "cost_usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "avg_latency_ms": 0.0,
                "cache_hit_rate": 0.0,
            }

        queries = len(events)
        total_cost = sum(event.get("cost_usd", 0.0) for event in events)
        prompt_tokens = sum((event.get("usage") or {}).get("prompt_tokens", 0) for event in events)
        completion_tokens = sum((event.get("usage") or {}).get("completion_tokens", 0) for event in events)
        latencies = [event.get("latency_ms") for event in events if event.get("latency_ms") is not None]
        cache_hit_count = sum(1 for event in events if event.get("cache_hit"))
        return {
            "queries": queries,
            "cost_usd": round(total_cost, 6),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "avg_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
            "cache_hit_rate": round(cache_hit_count / queries, 4) if queries else 0.0,
        }

    def _group_by_day(self, events: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            ts: datetime = event["_ts"]
            buckets[ts.date().isoformat()].append(event)
        ordered_keys = sorted(buckets.keys(), reverse=True)[:limit]
        return [self._summarize_bucket(key, buckets[key]) for key in ordered_keys]

    def _group_by_month(self, events: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            ts: datetime = event["_ts"]
            label = f"{ts.year:04d}-{ts.month:02d}"
            buckets[label].append(event)
        ordered_keys = sorted(buckets.keys(), reverse=True)[:limit]
        return [self._summarize_bucket(key, buckets[key]) for key in ordered_keys]

    def _summarize_bucket(self, label: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "label": label,
            "queries": len(events),
            "cost_usd": round(sum(event.get("cost_usd", 0.0) for event in events), 6),
            "avg_latency_ms": self._safe_mean(event.get("latency_ms") for event in events),
        }

    def _recent_events(self, events: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
        recent = sorted(events, key=lambda event: event["_ts"], reverse=True)[:limit]
        return [
            {
                "ts": event["ts"],
                "model": event["model"],
                "route": event.get("route"),
                "cost_usd": event.get("cost_usd", 0.0),
                "cache_hit": event.get("cache_hit"),
                "latency_ms": event.get("latency_ms"),
                "project_id": event.get("project_id"),
            }
            for event in recent
        ]

    def _estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        fallback: Optional[float],
    ) -> float:
        if fallback is not None:
            return float(fallback)
        pricing = self.model_pricing.get(model)
        if not pricing:
            return 0.0
        prompt_cost = (prompt_tokens / 1000) * pricing.get("prompt", 0.0)
        completion_cost = (completion_tokens / 1000) * pricing.get("completion", 0.0)
        return prompt_cost + completion_cost

    def _prune_locked(self, *, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retention_days)
        self._events = [event for event in self._events if event["_ts"] >= cutoff]

    def _append_telemetry(self, payload: Dict[str, Any]) -> None:  # pragma: no cover - simple IO
        from app.core.telemetry import emit_telemetry

        emit_telemetry(
            path=self.telemetry_path,
            event_type="cost.monitor.event",
            source="tracelab",
            payload=payload,
        )

    @staticmethod
    def _safe_mean(values: Any) -> float:
        numeric = [value for value in values if isinstance(value, (int, float))]
        return round(mean(numeric), 3) if numeric else 0.0


_cost_monitor: CostMonitor | None = None


def get_cost_monitor() -> CostMonitor:
    """Return the singleton cost monitor instance."""

    global _cost_monitor
    if _cost_monitor is None:
        _cost_monitor = CostMonitor()
    return _cost_monitor


__all__ = ["CostMonitor", "get_cost_monitor"]
