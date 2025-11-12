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
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None
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


# Singleton instance (lazy initialization)
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Get or create the singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
