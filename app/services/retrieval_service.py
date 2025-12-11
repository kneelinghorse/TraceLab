"""Retrieval service for RAG query functionality."""
from datetime import date
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.services.embedding_service import get_embedding_service
from app.services.faceted_search import FacetFilters, FacetedSearchService
from app.services.qdrant_service import get_qdrant_service


class RetrievalService:
    """Service for retrieving relevant document chunks using semantic search."""
    
    def __init__(self, faceted_service: Optional[FacetedSearchService] = None):
        self.embedding_service = get_embedding_service()
        self.qdrant_service = get_qdrant_service()
        self.faceted_service = faceted_service or FacetedSearchService()
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_origin: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        query_embedding: Optional[List[float]] = None,
        include_embeddings: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using semantic similarity.

        Args:
            query: Natural language query string
            top_k: Number of results to return
            project_id: Optional filter by project UUID
            document_id: Optional filter by document UUID
            source_type: Optional filter by source type
            source_origin: Optional filter by source origin (upload, synthesized, imported)
            hnsw_ef: Explicit HNSW search parameter override
            include_embeddings: Include embedding vectors in results

        Returns:
            List of search result dicts with chunk information and scores
        """
        resolved_hnsw_ef = self.recommend_hnsw_ef(top_k) if hnsw_ef is None else hnsw_ef

        # Generate query embedding (can be precomputed by caller)
        effective_query_embedding = (
            query_embedding if query_embedding is not None else self.embedding_service.generate_embedding(query)
        )

        # Search Qdrant
        results = self.qdrant_service.search_chunks(
            query_vector=effective_query_embedding,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            source_origin=source_origin,
            hnsw_ef=resolved_hnsw_ef,
            with_vectors=include_embeddings
        )

        filters = FacetFilters.from_kwargs(
            project_id=project_id,
            document_types=document_types,
            source_types=source_types,
            source_type=source_type,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
        )
        return self.faceted_service.filter_chunks(results, filters)

    def recommend_hnsw_ef(self, top_k: int) -> int:
        """
        Recommend an HNSW ef value that balances recall and latency.

        Tuned based on B19.3 benchmarks (2025-12-10):
        - ef=32-64: ~40ms avg latency, 100% recall at 7K corpus
        - ef=128: ~47ms avg latency (baseline)

        Uses lower ef values for latency-sensitive interactive queries,
        scaling up only for large result sets to maintain recall.
        """
        base_ef = settings.qdrant_hnsw_ef_default  # 64 by default

        if top_k <= 5:
            # Small result sets: use base ef, very fast
            return base_ef
        if top_k <= 10:
            # Medium result sets: slight increase for recall margin
            return max(base_ef, 72)
        if top_k <= 20:
            # Larger result sets: increase for better recall
            return max(base_ef, 96)
        # Very large fan-outs: scale conservatively
        return min(128, max(base_ef, int(top_k * 4)))


# Singleton instance (lazy initialization)
_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the singleton retrieval service instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
