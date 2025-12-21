"""Application-level cache manager with TTL-backed buckets and telemetry logging."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Hashable, Optional, Sequence, Tuple

from app.core.cache import CacheConfig, CacheRegistry, DEFAULT_CACHE_REGISTRY


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


CacheLoader = Callable[[], Any]


@dataclass(frozen=True)
class _Bucket:
    """Small helper to pair cache names with their configuration."""

    name: str
    config: CacheConfig


_BUCKETS: Dict[str, _Bucket] = {
    "rag_query_results": _Bucket("rag_query_results", CacheConfig("rag_query_results", ttl_seconds=300, maxsize=128)),
    "document_lists": _Bucket("document_lists", CacheConfig("document_lists", ttl_seconds=120, maxsize=512)),
    "project_metadata": _Bucket("project_metadata", CacheConfig("project_metadata", ttl_seconds=300, maxsize=256)),
    "quality_gates": _Bucket("quality_gates", CacheConfig("quality_gates", ttl_seconds=60, maxsize=256)),
    "mission_validation": _Bucket("mission_validation", CacheConfig("mission_validation", ttl_seconds=30, maxsize=256)),
    "relationship_context": _Bucket("relationship_context", CacheConfig("relationship_context", ttl_seconds=300, maxsize=512)),
}


class CacheManager:
    """Coordinates cache lifecycles, invalidation, stats, and telemetry snapshots."""

    def __init__(
        self,
        *,
        registry: CacheRegistry | None = None,
        telemetry_path: Path | None = None,
    ) -> None:
        self.registry = registry or DEFAULT_CACHE_REGISTRY
        default_path = _repo_root() / "cmos" / "telemetry" / "events" / "sprint-08-cache-metrics.jsonl"
        self.telemetry_path = telemetry_path or default_path

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _namespace(self, name: str) -> CacheNamespace:
        bucket = _BUCKETS[name]
        return self.registry.namespace(bucket.config)

    def ttl_seconds(self, name: str) -> float:
        return _BUCKETS[name].config.ttl_seconds

    def cached_value(self, name: str, key: Hashable, loader: CacheLoader) -> Tuple[Any, bool]:
        namespace = self._namespace(name)
        return namespace.get_or_set(key, loader)

    def set_value(self, name: str, key: Hashable, value: Any) -> None:
        namespace = self._namespace(name)
        namespace.set(key, value)

    def get_value(self, name: str, key: Hashable) -> Tuple[Any, bool]:
        namespace = self._namespace(name)
        cached = namespace.get(key, default=None)
        return cached, cached is not None

    def invalidate(self, name: str, predicate: Optional[Callable[[Hashable], bool]] = None) -> int:
        namespace = self._namespace(name)
        return namespace.invalidate(predicate)

    def clear(self, targets: Optional[Sequence[str]] = None) -> Dict[str, int]:
        cleared: Dict[str, int] = {}
        names = targets or list(_BUCKETS.keys())
        for name in names:
            cleared[name] = self.invalidate(name)
        return cleared

    # ------------------------------------------------------------------
    # Domain-specific key helpers
    # ------------------------------------------------------------------
    @staticmethod
    def rag_query_key(
        *,
        query: str,
        project_id: Optional[str],
        document_id: Optional[str],
        source_type: Optional[str],
        top_k: int,
        temperature: Optional[float],
        max_tokens: Optional[int],
        search_mode: str,
        filters_signature: Optional[str] = None,
        quality_signature: Optional[str] = None,
        graph_context_enabled: bool = False,
    ) -> Tuple[Any, ...]:
        return (
            query.strip(),
            project_id or "*",
            document_id or "*",
            source_type or "*",
            int(top_k),
            round(temperature if temperature is not None else 0.0, 3),
            int(max_tokens) if max_tokens is not None else 0,
            (search_mode or "semantic").strip().lower(),
            filters_signature or "*",
            quality_signature or "*",
            "graph" if graph_context_enabled else "no-graph",
        )

    @staticmethod
    def document_list_key(
        *,
        project_id: Optional[str],
        processed: Optional[bool],
        search: Optional[str],
        page: int,
        page_size: int,
        include_deleted: bool = False,
    ) -> Tuple[Any, ...]:
        normalized_search = (search or "").strip().lower()
        processed_state = (
            "processed" if processed is True else "unprocessed" if processed is False else "*"
        )
        return (
            project_id or "*",
            processed_state,
            normalized_search,
            int(page),
            int(page_size),
            include_deleted,
        )

    @staticmethod
    def project_metadata_key(
        *,
        kind: str,
        identifier: Optional[str] = None,
        search: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        include_deleted: bool = False,
    ) -> Tuple[Any, ...]:
        if kind == "detail" and identifier:
            return ("detail", identifier)
        normalized_search = (search or "").strip().lower()
        return (
            "list",
            normalized_search,
            int(page or 1),
            int(page_size or 20),
            include_deleted,
        )

    @staticmethod
    def mission_validation_key(payload: Dict[str, Any]) -> Tuple[str, str]:
        mission_id = str(payload.get("mission_id") or "unknown").strip() or "unknown"
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        return mission_id, digest

    @staticmethod
    def quality_gate_key(mission_id: str) -> Tuple[str]:
        return (mission_id,)

    @staticmethod
    def relationship_context_key(
        *,
        mission_id: str,
        depth: int,
        entity_types: Optional[Sequence[str]],
        min_relevance: Optional[float],
    ) -> Tuple[Any, ...]:
        normalized_types: Tuple[str, ...]
        if entity_types:
            normalized_types = tuple(sorted(entity_types))
        else:
            normalized_types = tuple()
        normalized_relevance = None if min_relevance is None else round(float(min_relevance), 3)
        return (str(mission_id), int(depth), normalized_types, normalized_relevance)

    # ------------------------------------------------------------------
    # Domain-specific invalidation adapters
    # ------------------------------------------------------------------
    def invalidate_document_lists(self, project_id: Optional[str] = None) -> int:
        if not project_id:
            return self.invalidate("document_lists")
        return self.invalidate("document_lists", predicate=lambda key: key[0] == project_id)

    def invalidate_project_metadata(self, project_id: Optional[str] = None) -> int:
        if not project_id:
            return self.invalidate("project_metadata")
        removed = self.invalidate(
            "project_metadata",
            predicate=lambda key: key[0] == "detail" and key[1] == project_id,
        )
        # Project updates also impact listings
        removed += self.invalidate(
            "project_metadata",
            predicate=lambda key: key[0] == "list",
        )
        return removed

    def invalidate_quality_gates(self, mission_id: Optional[str] = None) -> int:
        if not mission_id:
            return self.invalidate("quality_gates")
        return self.invalidate("quality_gates", predicate=lambda key: key[0] == mission_id)

    def invalidate_mission_validation(self, mission_id: Optional[str] = None) -> int:
        if not mission_id:
            return self.invalidate("mission_validation")
        return self.invalidate("mission_validation", predicate=lambda key: key[0] == mission_id)

    def invalidate_relationship_context(self, mission_id: Optional[str] = None) -> int:
        if not mission_id:
            return self.invalidate("relationship_context")
        return self.invalidate("relationship_context", predicate=lambda key: key[0] == str(mission_id))

    # ------------------------------------------------------------------
    # Metrics + telemetry
    # ------------------------------------------------------------------
    def snapshot(self, *, log: bool = False) -> Dict[str, Any]:
        raw = self.registry.snapshot()
        snapshot: Dict[str, Any] = {}
        for name, payload in raw.items():
            stats = payload["stats"]
            last_event = stats.get("last_event_ts")
            snapshot[name] = {
                "name": name,
                "ttl_seconds": payload["ttl_seconds"],
                "maxsize": payload["maxsize"],
                "size": payload["size"],
                "hits": stats.get("hits", 0.0),
                "misses": stats.get("misses", 0.0),
                "sets": stats.get("sets", 0.0),
                "invalidations": stats.get("invalidations", 0.0),
                "hit_rate": stats.get("hit_rate", 0.0),
                "last_event_ts": (
                    datetime.fromtimestamp(last_event, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    if isinstance(last_event, (int, float))
                    else None
                ),
            }
        if log:
            self._write_telemetry(snapshot)
        return snapshot

    def _write_telemetry(self, snapshot: Dict[str, Any]) -> None:
        payload = {
            "ts": _utc_now_str(),
            "caches": snapshot,
        }
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")


_CACHE_MANAGER: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    global _CACHE_MANAGER
    if _CACHE_MANAGER is None:
        _CACHE_MANAGER = CacheManager()
    return _CACHE_MANAGER


__all__ = ["CacheManager", "get_cache_manager"]
