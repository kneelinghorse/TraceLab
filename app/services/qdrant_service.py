"""Qdrant vector database service with optimized configuration."""

# ruff: noqa: S110, SIM105 - payload-index creation is intentionally idempotent.

from typing import Any
from uuid import UUID

try:  # pragma: no cover - allow importing module without qdrant dependency
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        HnswConfig,
        HnswConfigDiff,
        MatchAny,
        MatchValue,
        OptimizersConfigDiff,
        PayloadSchemaType,
        PointStruct,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
        VectorParams,
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Distance = VectorParams = PointStruct = HnswConfig = HnswConfigDiff = None  # type: ignore
    ScalarQuantization = ScalarQuantizationConfig = ScalarType = None  # type: ignore
    Filter = FieldCondition = MatchAny = MatchValue = PayloadSchemaType = None  # type: ignore
    OptimizersConfigDiff = None  # type: ignore
    _qdrant_import_error = exc
else:
    _qdrant_import_error = None

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client


class QdrantService:
    """Service for managing Qdrant vector database collections and operations.

    Uses the shared pre-warmed Qdrant client from app.core.qdrant_client
    to eliminate cold-start latency on first query.
    """

    def __init__(
        self,
        client: QdrantClient | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ):
        """Initialize QdrantService.

        Args:
            client: Optional QdrantClient instance. If not provided, uses the
                    shared pre-warmed client from app.core.qdrant_client.
            collection_name: Optional collection override for migrations.
            vector_size: Optional vector dimension override for advanced testing.
        """
        if _qdrant_import_error is not None:
            raise RuntimeError(
                "The qdrant-client package is required for vector storage interactions. "
                "Install dependencies from requirements.txt."
            ) from _qdrant_import_error

        # Use provided client or fall back to shared singleton
        self.client = client if client is not None else get_qdrant_client()
        self.collection_name = collection_name or settings.qdrant_collection_name
        self.vector_size = vector_size or settings.openai_embedding_dimension

    @staticmethod
    def _extract_vector_size(collection_info: Any) -> int | None:
        """Extract configured vector size from Qdrant collection metadata."""
        config = getattr(collection_info, "config", None)
        params = getattr(config, "params", None) if config else None
        vectors = getattr(params, "vectors", None) if params else None
        if vectors is None:
            return None

        direct_size = getattr(vectors, "size", None)
        if isinstance(direct_size, int):
            return direct_size

        # Named-vector collections expose vectors as a mapping.
        if isinstance(vectors, dict):
            for value in vectors.values():
                candidate = getattr(value, "size", None)
                if isinstance(candidate, int):
                    return candidate
                if isinstance(value, dict):
                    nested = value.get("size")
                    if isinstance(nested, int):
                        return nested
        return None

    def _create_collection(self, write_optimized: bool) -> None:
        """Create collection using either write-optimized or query-optimized settings.

        HNSW parameters are tuned for 3072d vectors (text-embedding-3-large):
        - m=24: Higher graph degree for better recall in high-dimensional space
          (increased from 16 used for 1536d vectors in Sprint 19)
        - ef_construct=128: Better index quality for doubled dimensions
          (increased from 100 used for 1536d vectors)
        """
        hnsw_m = settings.qdrant_hnsw_m
        hnsw_ef_construct = settings.qdrant_hnsw_ef_construct

        if write_optimized:
            # Write-optimized: lower m for faster bulk import, delayed indexing.
            vectors_config = VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
                on_disk=True,
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=64,
                    full_scan_threshold=1_000_000,
                    on_disk=False,
                ),
            )
            optimizer_config = OptimizersConfigDiff(
                indexing_threshold=1_000_000  # Prevent indexing during bulk import
            )
        else:
            # Query-optimized: tuned HNSW for 3072d vectors (T30.4).
            vectors_config = VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
                on_disk=True,
                hnsw_config=HnswConfigDiff(
                    m=hnsw_m,
                    ef_construct=hnsw_ef_construct,
                    full_scan_threshold=20_000,
                    on_disk=False,  # Keep HNSW graph in RAM
                ),
            )
            optimizer_config = None

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            optimizers_config=optimizer_config,
            on_disk_payload=True,  # Store payloads on disk
        )

    def _validate_collection_vector_size(self) -> None:
        """Ensure existing collection dimension matches configured embedding size."""
        try:
            info = self.client.get_collection(self.collection_name)
        except Exception:
            # Some managed Qdrant versions expose fields older SDKs cannot parse.
            # Skip strict validation when metadata cannot be inspected safely.
            return
        current_size = self._extract_vector_size(info)
        if current_size is None:
            return
        if current_size != self.vector_size:
            raise RuntimeError(
                f"Qdrant collection '{self.collection_name}' uses vector_size={current_size}, "
                f"but the application is configured for {self.vector_size}. "
                "Create and migrate to a new collection (for example, research_chunks_v2_3072d) "
                "before ingesting embeddings."
            )

    def ensure_collection(self, write_optimized: bool = False) -> None:
        """
        Create collection if it doesn't exist with optimized configuration.

        Args:
            write_optimized: If True, create collection with indexing disabled for bulk import
        """
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]

        if self.collection_name not in collection_names:
            self._create_collection(write_optimized=write_optimized)
            self._create_payload_indexes()
            return

        self._validate_collection_vector_size()
        # Collection already exists; ensure payload indexes are present
        self._create_payload_indexes()

        # Switch to write-optimized mode on demand for bulk imports
        if write_optimized:
            self.client.update_collection(
                collection_name=self.collection_name,
                hnsw_config=HnswConfigDiff(
                    m=16, ef_construct=32, full_scan_threshold=1_000_000
                ),
                optimizers_config=OptimizersConfigDiff(indexing_threshold=1_000_000),
                quantization_config=None,
            )

    def _create_payload_indexes(self) -> None:
        """Create payload indexes for project_id, document_id, source_type, and source_origin."""
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="project_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # Index may already exist

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source_type",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source_origin",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

    def enable_indexing_and_quantization(self) -> None:
        """
        Enable HNSW indexing and scalar quantization after bulk import.
        This should be called after bulk data upload is complete.
        """
        self.client.update_collection(
            collection_name=self.collection_name,
            hnsw_config=HnswConfigDiff(
                m=16, ef_construct=100, full_scan_threshold=20000
            ),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,  # Keep quantized vectors in RAM
                )
            ),
        )

    def upsert_chunks(
        self, chunks: list[dict[str, Any]], batch_size: int = 100, parallel: int = 2
    ) -> None:
        """
        Store document chunks as vectors in Qdrant.

        Args:
            chunks: List of chunk dicts with keys:
                - chunk_id (UUID): Chunk ID
                - embedding (List[float]): Embedding vector
                - content (str): Chunk text content
                - document_id (str): UUID of source document
                - project_id (str): UUID of project
                - chunk_index (int): Index within document
                - source_type (str, optional): Type of source document
                - source_origin (str, optional): Origin type (upload, synthesized, imported)
            batch_size: Batch size for upload_points
            parallel: Number of parallel upload workers
        """
        points = []
        for chunk in chunks:
            point_id = str(chunk["chunk_id"])
            payload = {
                "content": chunk["content"],
                "document_id": str(chunk["document_id"]),
                "project_id": str(chunk["project_id"]),
                "chunk_index": chunk["chunk_index"],
            }
            if "source_type" in chunk:
                payload["source_type"] = chunk["source_type"]
            if "source_origin" in chunk:
                payload["source_origin"] = chunk["source_origin"]

            point = PointStruct(id=point_id, vector=chunk["embedding"], payload=payload)
            points.append(point)

        # Respect batch_size to avoid oversize payloads on large corpora.
        if batch_size <= 0:
            batch_size = len(points) or 1
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            self.client.upsert(
                collection_name=self.collection_name, points=batch, wait=True
            )

    def delete_chunks(self, document_id: str) -> None:
        """Delete every vector whose payload belongs to one document."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    )
                ]
            ),
            wait=True,
        )

    def search_chunks(
        self,
        query_vector: list[float],
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        source_origin: str | None = None,
        hnsw_ef: int | None = None,
        with_vectors: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            project_id: Optional filter by project
            document_id: Optional filter by document
            source_type: Optional filter by source type
            source_origin: Optional filter by source origin (upload, synthesized, imported)
            hnsw_ef: HNSW search parameter (higher = better recall, slower).
                     Defaults to settings.qdrant_hnsw_ef_default (64).
            allowed_project_ids: Per-request RBAC project scope. ``None`` keeps
                the legacy unrestricted behavior; an empty list fails closed.

        Returns:
            List of search result dicts with keys:
                - chunk_id: Chunk UUID
                - content: Chunk text
                - document_id: Source document UUID
                - project_id: Project UUID
                - chunk_index: Index within document
                - score: Similarity score
                - source_origin: Document origin type
        """
        scoped_project_ids: list[str] | None = None
        if allowed_project_ids is not None:
            # Preserve caller order while removing duplicates so the emitted
            # MatchAny predicate is deterministic and no broader than necessary.
            scoped_project_ids = list(
                dict.fromkeys(str(identifier) for identifier in allowed_project_ids)
            )
            if project_id is not None:
                requested_project_id = str(project_id)
                scoped_project_ids = (
                    [requested_project_id]
                    if requested_project_id in scoped_project_ids
                    else []
                )
            if not scoped_project_ids:
                return []

        # Use configured default if not specified
        effective_hnsw_ef = (
            hnsw_ef if hnsw_ef is not None else settings.qdrant_hnsw_ef_default
        )

        # Build filter
        filter_conditions = []
        if scoped_project_ids is not None:
            filter_conditions.append(
                FieldCondition(
                    key="project_id", match=MatchAny(any=scoped_project_ids)
                )
            )
        elif project_id:
            filter_conditions.append(
                FieldCondition(
                    key="project_id", match=MatchValue(value=str(project_id))
                )
            )
        if document_id:
            filter_conditions.append(
                FieldCondition(
                    key="document_id", match=MatchValue(value=str(document_id))
                )
            )
        if source_type:
            filter_conditions.append(
                FieldCondition(
                    key="source_type", match=MatchValue(value=str(source_type))
                )
            )
        if source_origin:
            filter_conditions.append(
                FieldCondition(
                    key="source_origin", match=MatchValue(value=str(source_origin))
                )
            )

        query_filter = Filter(must=filter_conditions) if filter_conditions else None

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
            search_params={"hnsw_ef": effective_hnsw_ef},
            with_vectors=with_vectors,
        )

        chunk_results: list[dict[str, Any]] = []
        for result in results:
            chunk_payload = {
                "chunk_id": str(result.id),
                "content": result.payload.get("content", ""),
                "document_id": result.payload.get("document_id"),
                "project_id": result.payload.get("project_id"),
                "chunk_index": result.payload.get("chunk_index"),
                "source_type": result.payload.get("source_type"),
                "source_origin": result.payload.get("source_origin"),
                "score": result.score,
            }
            if with_vectors:
                vector = getattr(result, "vector", None)
                if isinstance(vector, dict):
                    vector = next(iter(vector.values()), None)
                if vector is not None:
                    chunk_payload["embedding"] = vector
            chunk_results.append(chunk_payload)

        return chunk_results

    def get_collection_diagnostics(self) -> dict[str, Any]:
        """Return collection stats plus inferred memory/quantization health."""

        diagnostics: dict[str, Any] = {
            "collection": self.collection_name,
            "collection_exists": False,
            "points_count": 0,
            "vectors_count": 0,
            "payload_indexes": [],
            "hnsw": {},
            "quantization": {"enabled": False},
            "optimizer": {},
            "vector_size": self.vector_size,
            "memory_estimate_bytes": 0,
            "memory_estimate_gb": 0.0,
            "error": None,
        }

        try:
            info = self.client.get_collection(self.collection_name)
        except Exception as exc:  # pragma: no cover - real Qdrant only
            diagnostics["error"] = str(exc)
            return diagnostics

        diagnostics["collection_exists"] = True
        diagnostics["points_count"] = int(getattr(info, "points_count", 0) or 0)
        diagnostics["vectors_count"] = int(
            getattr(info, "vectors_count", diagnostics["points_count"]) or 0
        )

        payload_schema = getattr(info, "payload_schema", {}) or {}
        diagnostics["payload_indexes"] = [
            {"field": field, "present": True} for field in sorted(payload_schema.keys())
        ]

        config = getattr(info, "config", None)
        params = getattr(config, "params", None) if config else None
        vectors = getattr(params, "vectors", None) if params else None
        hnsw_config = getattr(vectors, "hnsw_config", None) if vectors else None
        diagnostics["hnsw"] = {
            "m": getattr(hnsw_config, "m", None),
            "ef_construct": getattr(hnsw_config, "ef_construct", None),
            "full_scan_threshold": getattr(hnsw_config, "full_scan_threshold", None),
            "on_disk": getattr(hnsw_config, "on_disk", None),
        }

        optimizer_config = getattr(config, "optimizer_config", None) if config else None
        if optimizer_config is None and config is not None:
            optimizer_config = getattr(config, "optimizers_config", None)
        diagnostics["optimizer"] = (
            {
                "indexing_threshold": getattr(
                    optimizer_config, "indexing_threshold", None
                )
            }
            if optimizer_config
            else {}
        )

        quantization_config = (
            getattr(config, "quantization_config", None) if config else None
        )
        scalar_config = (
            getattr(quantization_config, "scalar", None)
            if quantization_config
            else None
        )
        quantization_type = None
        if scalar_config is not None:
            quantization_type = getattr(scalar_config, "type", None)
        elif quantization_config is not None:
            quantization_type = getattr(quantization_config, "type", None)

        diagnostics["quantization"] = {
            "enabled": quantization_config is not None,
            "type": str(quantization_type) if quantization_type else None,
            "always_ram": getattr(scalar_config, "always_ram", None)
            if scalar_config
            else None,
            "quantile": getattr(scalar_config, "quantile", None)
            if scalar_config
            else None,
        }

        quantized = diagnostics["quantization"]["enabled"]
        vector_bytes = self.vector_size * (1 if quantized else 4)
        vector_memory_bytes = vector_bytes * diagnostics["vectors_count"]
        payload_overhead = (
            diagnostics["points_count"] * 256
        )  # heuristic payload footprint
        total_bytes = vector_memory_bytes + payload_overhead
        diagnostics["memory_estimate_bytes"] = total_bytes
        diagnostics["memory_estimate_gb"] = round(total_bytes / (1024**3), 3)
        return diagnostics

    def apply_hnsw_settings(
        self,
        *,
        m: int,
        ef_construct: int,
        full_scan_threshold: int,
        on_disk: bool = False,
        optimizer_threshold: int | None = 20000,
        enable_quantization: bool = True,
        quantile: float = 0.99,
        always_ram: bool = True,
    ) -> None:
        """Update collection HNSW/quantization parameters in-place."""

        quantization_config = None
        if enable_quantization:
            quantization_config = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=quantile,
                    always_ram=always_ram,
                )
            )

        optimizers_config = (
            OptimizersConfigDiff(indexing_threshold=optimizer_threshold)
            if optimizer_threshold is not None
            else None
        )

        self.client.update_collection(
            collection_name=self.collection_name,
            hnsw_config=HnswConfigDiff(
                m=m,
                ef_construct=ef_construct,
                full_scan_threshold=full_scan_threshold,
                on_disk=on_disk,
            ),
            optimizers_config=optimizers_config,
            quantization_config=quantization_config,
        )


# Singleton instance (lazy initialization)
_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    """Get or create the singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
