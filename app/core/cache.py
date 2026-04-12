"""Thread-safe TTL cache utilities shared across the application."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from cachetools import TTLCache
from cachetools.keys import hashkey

T = TypeVar("T")
Loader = Callable[[], T]
KeyBuilder = Callable[..., Hashable]

_MISSING = object()


def _utc_now() -> float:
    return time.time()


def _normalize(value: Any) -> Any:
    """Best-effort transformation that turns unhashable objects into stable representations."""
    try:
        hash(value)
    except TypeError:
        if isinstance(value, Mapping):
            return tuple(sorted((str(k), _normalize(v)) for k, v in value.items()))
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return tuple(_normalize(item) for item in value)
        return repr(value)
    return value


def _safe_hashkey(*args: Any, **kwargs: Any) -> Hashable:
    """Return a hashable cache key even when inputs include unhashable objects."""
    try:
        return hashkey(*args, **kwargs)
    except TypeError:
        norm_args = tuple(_normalize(arg) for arg in args)
        norm_kwargs = {key: _normalize(value) for key, value in kwargs.items()}
        return hashkey(*norm_args, **norm_kwargs)


@dataclass(frozen=True)
class CacheConfig:
    """Configuration for a cache namespace."""

    name: str
    ttl_seconds: float
    maxsize: int


@dataclass
class CacheStats:
    """Mutable statistics collected for an individual cache."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    invalidations: int = 0
    last_event_ts: float = field(default_factory=_utc_now)

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0

    def snapshot(self) -> dict[str, float]:
        return {
            "hits": float(self.hits),
            "misses": float(self.misses),
            "sets": float(self.sets),
            "invalidations": float(self.invalidations),
            "hit_rate": self.hit_rate(),
            "last_event_ts": self.last_event_ts,
        }


class CacheNamespace:
    """Container that wraps a TTLCache with statistics and invalidation helpers."""

    def __init__(self, config: CacheConfig) -> None:
        self.config = config
        self._cache: TTLCache = TTLCache(maxsize=config.maxsize, ttl=config.ttl_seconds)
        self._lock = threading.RLock()
        self._stats = CacheStats()

    def _touch(self) -> None:
        self._stats.last_event_ts = _utc_now()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def get(self, key: Hashable, *, default: Any = _MISSING) -> Any:
        with self._lock:
            try:
                value = self._cache[key]
            except KeyError:
                self._stats.misses += 1
                self._touch()
                return default
            self._stats.hits += 1
            self._touch()
            return copy.deepcopy(value)

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._cache[key] = copy.deepcopy(value)
            self._stats.sets += 1
            self._touch()

    def get_or_set(self, key: Hashable, loader: Loader) -> tuple[Any, bool]:
        cached = self.get(key, default=_MISSING)
        if cached is not _MISSING:
            return cached, True
        value = loader()
        self.set(key, value)
        return copy.deepcopy(value), False

    def invalidate(self, predicate: Callable[[Hashable], bool] | None = None) -> int:
        """Remove entries that match predicate. When predicate is None, clear the entire cache."""
        with self._lock:
            if predicate is None:
                removed = len(self._cache)
                self._cache.clear()
            else:
                targets = [key for key in self._cache.keys() if predicate(key)]
                removed = 0
                for key in targets:
                    try:
                        del self._cache[key]
                        removed += 1
                    except KeyError:
                        continue
            if removed:
                self._stats.invalidations += removed
                self._touch()
            return removed

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stats = self._stats.snapshot()
            return {
                "name": self.config.name,
                "ttl_seconds": self.config.ttl_seconds,
                "maxsize": self.config.maxsize,
                "size": len(self._cache),
                "stats": stats,
            }


class CacheRegistry:
    """Global registry that stores cache namespaces by name."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._namespaces: dict[str, CacheNamespace] = {}

    def namespace(self, config: CacheConfig) -> CacheNamespace:
        with self._lock:
            namespace = self._namespaces.get(config.name)
            if namespace and namespace.config == config:
                return namespace
            namespace = CacheNamespace(config)
            self._namespaces[config.name] = namespace
            return namespace

    def get(self, name: str) -> CacheNamespace | None:
        with self._lock:
            return self._namespaces.get(name)

    def clear_all(self) -> None:
        with self._lock:
            for namespace in self._namespaces.values():
                namespace.invalidate()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: namespace.snapshot()
                for name, namespace in self._namespaces.items()
            }


DEFAULT_CACHE_REGISTRY = CacheRegistry()


def ttl_cache(
    name: str,
    *,
    ttl_seconds: float,
    maxsize: int = 128,
    key_builder: KeyBuilder | None = None,
    registry: CacheRegistry | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that memoizes function results using a shared TTL cache namespace."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache_registry = registry or DEFAULT_CACHE_REGISTRY
        namespace = cache_registry.namespace(
            CacheConfig(name=name, ttl_seconds=ttl_seconds, maxsize=maxsize)
        )

        def _key(*args: Any, **kwargs: Any) -> Hashable:
            if key_builder:
                return key_builder(*args, **kwargs)
            return _safe_hashkey(*args, **kwargs)

        def wrapper(*args: Any, **kwargs: Any) -> T:
            key = _key(*args, **kwargs)
            cached = namespace.get(key, default=_MISSING)
            if cached is not _MISSING:
                return cached
            value = func(*args, **kwargs)
            namespace.set(key, value)
            return value

        wrapper.cache_namespace = namespace  # type: ignore[attr-defined]
        return wrapper

    return decorator


__all__ = [
    "CacheConfig",
    "CacheRegistry",
    "CacheNamespace",
    "DEFAULT_CACHE_REGISTRY",
    "ttl_cache",
]
