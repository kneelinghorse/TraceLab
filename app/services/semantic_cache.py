"""Semantic cache service backed by Qdrant."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable, Iterator
from typing import Any

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client
from app.services.cache_metrics import cache_metrics

try:  # pragma: no cover - allow import without qdrant dependency
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PayloadSchemaType,
        PointStruct,
        VectorParams,
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Distance = FieldCondition = Filter = MatchValue = PayloadSchemaType = (
        PointStruct
    ) = VectorParams = None  # type: ignore
    _qdrant_import_error = exc
else:
    _qdrant_import_error = None


class SemanticCacheService:
    """Qdrant-backed semantic cache for RAG responses.

    Uses the shared pre-warmed Qdrant client from app.core.qdrant_client
    to eliminate cold-start latency on first cache lookup.
    """

    def __init__(
        self, client: QdrantClient | None = None, enabled: bool | None = None
    ) -> None:
        """Initialize SemanticCacheService.

        Args:
            client: Optional QdrantClient instance. If not provided, uses the
                    shared pre-warmed client from app.core.qdrant_client.
            enabled: Override for cache enabled setting. If None, uses settings.
        """
        if _qdrant_import_error is not None:  # pragma: no cover
            raise RuntimeError(
                "The qdrant-client package is required for semantic cache support. "
                "Install dependencies from requirements.txt."
            ) from _qdrant_import_error

        self.enabled = settings.semantic_cache_enabled if enabled is None else enabled
        self.similarity_threshold = settings.semantic_cache_similarity_threshold
        self.ttl_seconds = settings.semantic_cache_ttl_seconds
        self.max_items = settings.semantic_cache_max_items
        self.collection_name = settings.semantic_cache_collection_name
        self.metrics = cache_metrics

        # Use provided client or fall back to shared singleton
        self._client = client if client is not None else get_qdrant_client()

        if self.enabled:
            self._ensure_collection()

    @property
    def client(self) -> QdrantClient:
        """Return the underlying Qdrant client."""
        return self._client

    @staticmethod
    def _extract_vector_size(collection_info: Any) -> int | None:
        """Extract configured vector size from Qdrant collection metadata."""
        config = getattr(collection_info, "config", None)
        params = getattr(config, "params", None) if config else None
        vectors = getattr(params, "vectors", None) if params else None
        if vectors is None:
            return None

        size = getattr(vectors, "size", None)
        if isinstance(size, int):
            return size

        if isinstance(vectors, dict):
            for value in vectors.values():
                nested = getattr(value, "size", None)
                if isinstance(nested, int):
                    return nested
                if isinstance(value, dict):
                    fallback = value.get("size")
                    if isinstance(fallback, int):
                        return fallback
        return None

    def _create_collection(self) -> None:
        """Create semantic cache collection at the configured embedding dimension."""
        vectors_config = VectorParams(
            size=settings.openai_embedding_dimension,
            distance=Distance.COSINE,
            on_disk=True,
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            hnsw_config=None,
            optimizers_config=None,
            on_disk_payload=True,
        )

    def _ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        names = [collection.name for collection in collections]
        if self.collection_name not in names:
            self._create_collection()
            self._create_payload_indexes()
            return

        # Semantic cache is ephemeral; safe to recreate when dimensions change.
        try:
            info = self.client.get_collection(self.collection_name)
        except Exception:
            self._create_payload_indexes()
            return
        existing_size = self._extract_vector_size(info)
        if existing_size and existing_size != settings.openai_embedding_dimension:
            self.client.delete_collection(self.collection_name)
            self._create_collection()

        self._create_payload_indexes()

    def _create_payload_indexes(self) -> None:
        """Ensure common filter fields are indexed for quick lookups."""
        for field in ("project_id", "document_id", "source_type", "filters_signature"):
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:  # pragma: no cover - idempotent create
                continue

    def check_cache(
        self, query_embedding: Iterable[float], metadata: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Attempt to satisfy a query from the semantic cache."""
        if not self.enabled:
            return None

        start = time.perf_counter()
        project_id = metadata.get("project_id")
        document_id = metadata.get("document_id")
        source_type = metadata.get("source_type")
        filters_signature = metadata.get("filters_signature")

        filters = []
        if project_id:
            filters.append(
                FieldCondition(
                    key="project_id", match=MatchValue(value=str(project_id))
                )
            )
        if document_id:
            filters.append(
                FieldCondition(
                    key="document_id", match=MatchValue(value=str(document_id))
                )
            )
        if source_type:
            filters.append(
                FieldCondition(
                    key="source_type", match=MatchValue(value=str(source_type))
                )
            )
        if filters_signature:
            filters.append(
                FieldCondition(
                    key="filters_signature",
                    match=MatchValue(value=str(filters_signature)),
                )
            )
        query_filter = Filter(must=filters) if filters else None

        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=list(query_embedding),
                limit=1,
                query_filter=query_filter,
                with_payload=True,
                score_threshold=self.similarity_threshold,
            )
            duration = time.perf_counter() - start
            self.metrics.observe_lookup(duration)
        except Exception:  # pragma: no cover - defensive against qdrant outages
            self.metrics.record_error()
            self.metrics.observe_lookup(time.perf_counter() - start)
            return None

        if not results:
            self.metrics.record_miss(project_id)
            return None

        hit = results[0]
        payload = hit.payload or {}
        now_ts = time.time()
        expires_at = payload.get("expires_at")

        if expires_at and expires_at <= now_ts:
            # Expired entry; remove it eagerly.
            self._delete_points([hit.id])
            self.metrics.record_miss(project_id)
            return None

        self.metrics.record_hit(project_id)
        created_at = payload.get("created_at", now_ts)
        age_seconds = max(0.0, now_ts - created_at)
        ttl_remaining = max(0.0, (expires_at - now_ts)) if expires_at else None

        return {
            "answer": payload.get("answer", ""),
            "citations": payload.get("citations", []),
            "sources": payload.get("sources", []),
            "compression": payload.get("compression", {}),
            "cache": {
                "hit": True,
                "score": float(hit.score),
                "age_seconds": round(age_seconds, 3),
                "ttl_seconds": ttl_remaining,
            },
        }

    def store_in_cache(
        self,
        query_embedding: Iterable[float],
        result: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Persist a query result in the cache."""
        if not self.enabled:
            return

        vector = list(query_embedding)
        now_ts = time.time()
        expires_at = now_ts + self.ttl_seconds if self.ttl_seconds else None

        payload = {
            "query": metadata.get("query"),
            "project_id": metadata.get("project_id"),
            "document_id": metadata.get("document_id"),
            "source_type": metadata.get("source_type"),
            "filters_signature": metadata.get("filters_signature"),
            "document_types": metadata.get("document_types"),
            "source_types": metadata.get("source_types"),
            "tags": metadata.get("tags"),
            "date_from": metadata.get("date_from"),
            "date_to": metadata.get("date_to"),
            "top_k": metadata.get("top_k"),
            "temperature": metadata.get("temperature"),
            "max_tokens": metadata.get("max_tokens"),
            "answer": result.get("answer"),
            "citations": result.get("citations", []),
            "sources": result.get("sources", []),
            "compression": result.get("compression", {}),
            "created_at": now_ts,
            "expires_at": expires_at,
        }

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        )

        try:
            self.client.upsert(
                collection_name=self.collection_name, points=[point], wait=True
            )
            expired = self._evict_expired(now_ts)
            if expired:
                self.metrics.record_eviction(expired)
            overflow = self._trim_to_max_items()
            if overflow:
                self.metrics.record_eviction(overflow)
        except Exception:  # pragma: no cover - defensive against qdrant outages
            self.metrics.record_error()

    def _evict_expired(self, now_ts: float) -> int:
        if not self.ttl_seconds:
            return 0

        expired_ids: list[str] = []
        for point in self._iterate_points():
            payload = point.payload or {}
            expires_at = payload.get("expires_at")
            if expires_at and expires_at <= now_ts:
                expired_ids.append(str(point.id))

        self._delete_points(expired_ids)
        return len(expired_ids)

    def _trim_to_max_items(self) -> int:
        if not self.max_items or self.max_items <= 0:
            return 0

        count_response = self.client.count(
            collection_name=self.collection_name, exact=True
        )
        total = getattr(count_response, "count", 0)
        if total <= self.max_items:
            return 0

        to_remove = total - self.max_items
        points = list(self._iterate_points())
        points.sort(key=lambda point: (point.payload or {}).get("created_at", 0.0))
        victim_ids = [str(point.id) for point in points[:to_remove]]
        self._delete_points(victim_ids)
        return len(victim_ids)

    def _delete_points(self, ids: Iterable[str]) -> None:
        ids_list = [str(id_) for id_ in ids if id_]
        if not ids_list:
            return
        self.client.delete(
            collection_name=self.collection_name, points_selector=ids_list, wait=True
        )

    def _iterate_points(self, batch_size: int = 128) -> Iterator[Any]:
        """Yield all points in the cache collection with payloads."""
        offset = None
        while True:
            points, next_page_offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=batch_size,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                yield point
            if next_page_offset is None:
                break
            offset = next_page_offset


_semantic_cache_service: SemanticCacheService | None = None


def get_semantic_cache_service() -> SemanticCacheService:
    """Return the singleton semantic cache service."""
    global _semantic_cache_service
    if _semantic_cache_service is None:
        _semantic_cache_service = SemanticCacheService()
    return _semantic_cache_service
