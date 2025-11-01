"""Retrieval service for RAG query functionality."""
from typing import List, Dict, Any, Optional
from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service


class RetrievalService:
    """Service for retrieving relevant document chunks using semantic search."""
    
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.qdrant_service = get_qdrant_service()
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        hnsw_ef: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using semantic similarity.
        
        Args:
            query: Natural language query string
            top_k: Number of results to return
            project_id: Optional filter by project UUID
            document_id: Optional filter by document UUID
            source_type: Optional filter by source type
            hnsw_ef: Explicit HNSW search parameter override

        Returns:
            List of search result dicts with chunk information and scores
        """
        resolved_hnsw_ef = self.recommend_hnsw_ef(top_k) if hnsw_ef is None else hnsw_ef

        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)

        # Search Qdrant
        results = self.qdrant_service.search_chunks(
            query_vector=query_embedding,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            hnsw_ef=resolved_hnsw_ef
        )

        return results

    def recommend_hnsw_ef(self, top_k: int) -> int:
        """
        Recommend an HNSW ef value that balances recall and latency.

        Uses empirically tuned tiers to keep p99 latency under 10ms for larger
        result sets while keeping recall high for small fan-outs.
        """
        if top_k <= 5:
            return 96
        if top_k <= 10:
            return 108
        if top_k <= 20:
            return 120
        # Guardrails for unusually large fan-outs while avoiding runaway values.
        return min(160, max(96, int(top_k * 5.5)))


# Singleton instance (lazy initialization)
_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the singleton retrieval service instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
