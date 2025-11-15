"""Qdrant vector database service with optimized configuration."""
from typing import List, Dict, Any, Optional

try:  # pragma: no cover - allow importing module without qdrant dependency
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        HnswConfig,
        HnswConfigDiff,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
        Filter,
        FieldCondition,
        MatchValue,
        PayloadSchemaType,
        OptimizersConfigDiff
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Distance = VectorParams = PointStruct = HnswConfig = HnswConfigDiff = None  # type: ignore
    ScalarQuantization = ScalarQuantizationConfig = ScalarType = None  # type: ignore
    Filter = FieldCondition = MatchValue = PayloadSchemaType = None  # type: ignore
    OptimizersConfigDiff = None  # type: ignore
    _qdrant_import_error = exc
else:
    _qdrant_import_error = None

from app.core.config import settings


class QdrantService:
    """Service for managing Qdrant vector database collections and operations."""
    
    def __init__(self):
        if _qdrant_import_error is not None:
            raise RuntimeError(
                "The qdrant-client package is required for vector storage interactions. "
                "Install dependencies from requirements.txt."
            ) from _qdrant_import_error
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL must be configured before using QdrantService")
        if settings.qdrant_api_key and settings.qdrant_url.startswith("http://"):
            raise ValueError(
                "QDRANT_URL must use HTTPS when QDRANT_API_KEY is set. "
                "See docs/qdrant-railway-setup.md and R7.1 research notes."
            )
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
            prefer_grpc=settings.qdrant_prefer_grpc,
            timeout=settings.qdrant_timeout_seconds,
        )
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = settings.openai_embedding_dimension
        
    def ensure_collection(self, write_optimized: bool = False) -> None:
        """
        Create collection if it doesn't exist with optimized configuration.
        
        Args:
            write_optimized: If True, create collection with indexing disabled for bulk import
        """
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            # Configure for write-optimized bulk import if requested
            if write_optimized:
                # Create collection with relaxed HNSW settings and delayed indexing.
                vectors_config = VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=32,
                        full_scan_threshold=1_000_000,
                        on_disk=False
                    )
                )
                optimizer_config = OptimizersConfigDiff(
                    indexing_threshold=1_000_000  # Prevent indexing during bulk import
                )
            else:
                # Normal configuration with tuned HNSW indexing.
                vectors_config = VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                        full_scan_threshold=20_000,
                        on_disk=False  # Keep HNSW graph in RAM
                    )
                )
                optimizer_config = None
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_config,
                optimizers_config=optimizer_config,
                on_disk_payload=True  # Store payloads on disk
            )
            
            # Create payload indexes for filtering BEFORE data ingestion
            self._create_payload_indexes()
        else:
            # Collection already exists; ensure payload indexes are present
            self._create_payload_indexes()
            
            # Switch to write-optimized mode on demand for bulk imports
            if write_optimized:
                self.client.update_collection(
                    collection_name=self.collection_name,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=32,
                        full_scan_threshold=1_000_000
                    ),
                    optimizers_config=OptimizersConfigDiff(
                        indexing_threshold=1_000_000
                    ),
                    quantization_config=None
                )
    
    def _create_payload_indexes(self) -> None:
        """Create payload indexes for project_id, document_id, and source_type."""
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="project_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass  # Index may already exist
        
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass
        
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source_type",
                field_schema=PayloadSchemaType.KEYWORD
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
                m=16,
                ef_construct=100,
                full_scan_threshold=20000
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000
            ),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True  # Keep quantized vectors in RAM
                )
            )
        )
    
    def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 2000,
        parallel: int = 2
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
                "chunk_index": chunk["chunk_index"]
            }
            if "source_type" in chunk:
                payload["source_type"] = chunk["source_type"]
            
            point = PointStruct(
                id=point_id,
                vector=chunk["embedding"],
                payload=payload
            )
            points.append(point)
        
        # Use upsert for efficient batch upload
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True
        )
    
    def search_chunks(
        self,
        query_vector: List[float],
        top_k: int = 5,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        hnsw_ef: int = 128,
        with_vectors: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            project_id: Optional filter by project
            document_id: Optional filter by document
            source_type: Optional filter by source type
            hnsw_ef: HNSW search parameter (higher = better recall, slower)
            
        Returns:
            List of search result dicts with keys:
                - chunk_id: Chunk UUID
                - content: Chunk text
                - document_id: Source document UUID
                - project_id: Project UUID
                - chunk_index: Index within document
                - score: Similarity score
        """
        # Build filter
        filter_conditions = []
        if project_id:
            filter_conditions.append(
                FieldCondition(key="project_id", match=MatchValue(value=str(project_id)))
            )
        if document_id:
            filter_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))
            )
        if source_type:
            filter_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=str(source_type)))
            )
        
        query_filter = Filter(must=filter_conditions) if filter_conditions else None
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
            search_params={"hnsw_ef": hnsw_ef} if hnsw_ef else None,
            with_vectors=with_vectors
        )

        chunk_results: List[Dict[str, Any]] = []
        for result in results:
            chunk_payload = {
                "chunk_id": str(result.id),
                "content": result.payload.get("content", ""),
                "document_id": result.payload.get("document_id"),
                "project_id": result.payload.get("project_id"),
                "chunk_index": result.payload.get("chunk_index"),
                "source_type": result.payload.get("source_type"),
                "score": result.score
            }
            if with_vectors:
                vector = getattr(result, "vector", None)
                if isinstance(vector, dict):
                    vector = next(iter(vector.values()), None)
                if vector is not None:
                    chunk_payload["embedding"] = vector
            chunk_results.append(chunk_payload)

        return chunk_results

    def get_collection_diagnostics(self) -> Dict[str, Any]:
        """Return collection stats plus inferred memory/quantization health."""

        diagnostics: Dict[str, Any] = {
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
        diagnostics["vectors_count"] = int(getattr(info, "vectors_count", diagnostics["points_count"]) or 0)

        payload_schema = getattr(info, "payload_schema", {}) or {}
        diagnostics["payload_indexes"] = [
            {"field": field, "present": True}
            for field in sorted(payload_schema.keys())
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
            {"indexing_threshold": getattr(optimizer_config, "indexing_threshold", None)}
            if optimizer_config
            else {}
        )

        quantization_config = getattr(config, "quantization_config", None) if config else None
        scalar_config = getattr(quantization_config, "scalar", None) if quantization_config else None
        quantization_type = None
        if scalar_config is not None:
            quantization_type = getattr(scalar_config, "type", None)
        elif quantization_config is not None:
            quantization_type = getattr(quantization_config, "type", None)

        diagnostics["quantization"] = {
            "enabled": quantization_config is not None,
            "type": str(quantization_type) if quantization_type else None,
            "always_ram": getattr(scalar_config, "always_ram", None) if scalar_config else None,
            "quantile": getattr(scalar_config, "quantile", None) if scalar_config else None,
        }

        quantized = diagnostics["quantization"]["enabled"]
        vector_bytes = self.vector_size * (1 if quantized else 4)
        vector_memory_bytes = vector_bytes * diagnostics["vectors_count"]
        payload_overhead = diagnostics["points_count"] * 256  # heuristic payload footprint
        total_bytes = vector_memory_bytes + payload_overhead
        diagnostics["memory_estimate_bytes"] = total_bytes
        diagnostics["memory_estimate_gb"] = round(total_bytes / (1024 ** 3), 3)
        return diagnostics

    def apply_hnsw_settings(
        self,
        *,
        m: int,
        ef_construct: int,
        full_scan_threshold: int,
        on_disk: bool = False,
        optimizer_threshold: Optional[int] = 20000,
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
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Get or create the singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
