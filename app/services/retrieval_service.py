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
        hnsw_ef: int = 128
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using semantic similarity.
        
        Args:
            query: Natural language query string
            top_k: Number of results to return
            project_id: Optional filter by project UUID
            document_id: Optional filter by document UUID
            source_type: Optional filter by source type
            hnsw_ef: HNSW search parameter for recall/performance tradeoff
            
        Returns:
            List of search result dicts with chunk information and scores
        """
        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)
        
        # Search Qdrant
        results = self.qdrant_service.search_chunks(
            query_vector=query_embedding,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            hnsw_ef=hnsw_ef
        )
        
        return results


# Singleton instance (lazy initialization)
_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the singleton retrieval service instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service

