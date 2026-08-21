"""Retrieval service for RAG query functionality."""

from datetime import date
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.services.embedding_service import get_embedding_service
from app.services.faceted_search import FacetedSearchService, FacetFilters
from app.services.qdrant_service import get_qdrant_service


class RetrievalService:
    """Service for retrieving relevant document chunks using semantic search."""

    def __init__(self, faceted_service: FacetedSearchService | None = None):
        self.embedding_service = get_embedding_service()
        self.qdrant_service = get_qdrant_service()
        self.faceted_service = faceted_service or FacetedSearchService()

    def search(
        self,
        query: str,
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        source_origin: str | None = None,
        document_types: list[str] | None = None,
        source_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        tags: list[str] | None = None,
        hnsw_ef: int | None = None,
        query_embedding: list[float] | None = None,
        include_embeddings: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
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
            allowed_project_ids: Per-request RBAC project scope. ``None`` keeps
                legacy unrestricted behavior; an empty list fails closed.

        Returns:
            List of search result dicts with chunk information and scores
        """
        if allowed_project_ids is not None:
            allowed_values = {str(identifier) for identifier in allowed_project_ids}
            if not allowed_values or (
                project_id is not None and str(project_id) not in allowed_values
            ):
                return []

        resolved_hnsw_ef = self.recommend_hnsw_ef(top_k) if hnsw_ef is None else hnsw_ef

        # Generate query embedding (can be precomputed by caller)
        effective_query_embedding = (
            query_embedding
            if query_embedding is not None
            else self.embedding_service.generate_embedding(query)
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
            with_vectors=include_embeddings,
            allowed_project_ids=allowed_project_ids,
        )
        if allowed_project_ids is not None:
            # Defense in depth: do not trust the vector backend alone to enforce
            # tenancy. Missing, malformed, and out-of-scope payload IDs all fail
            # closed for a scoped request. ``None`` deliberately skips this block
            # to preserve the unrestricted legacy response byte-for-byte.
            expected_project_ids = set(allowed_project_ids)
            if project_id is not None:
                try:
                    expected_project_ids = {UUID(str(project_id))}
                except (TypeError, ValueError, AttributeError):
                    return []
            expected_document_id = None
            if document_id is not None:
                try:
                    expected_document_id = UUID(str(document_id))
                except (TypeError, ValueError, AttributeError):
                    return []
            scoped_results = []
            for result in results:
                try:
                    result_project_id = UUID(str(result.get("project_id")))
                except (TypeError, ValueError, AttributeError):
                    continue
                if result_project_id not in expected_project_ids:
                    continue
                if expected_document_id is not None:
                    try:
                        result_document_id = UUID(str(result.get("document_id")))
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if result_document_id != expected_document_id:
                        continue
                scoped_results.append(result)
            results = scoped_results

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
        """Recommend an HNSW ef value that balances recall and latency.

        Re-tuned for 3072d vectors (T30.4, text-embedding-3-large):
        - B19.3 baseline (1536d): ef=64 gave 45% P99 improvement, 100% recall at 7K
        - 3072d doubles distance-computation cost per candidate
        - Scaling is slightly more conservative to maintain recall with higher dims

        Uses lower ef values for latency-sensitive interactive queries,
        scaling up for larger result sets to maintain recall.
        """
        base_ef = settings.qdrant_hnsw_ef_default  # 64 by default

        if top_k <= 5:
            # Small result sets: use base ef
            return base_ef
        if top_k <= 10:
            # Medium result sets: slight increase for recall margin
            return max(base_ef, 80)
        if top_k <= 20:
            # Larger result sets: more aggressive scaling for 3072d recall
            return max(base_ef, 112)
        # Very large fan-outs: scale conservatively, cap at 160 for 3072d
        return min(160, max(base_ef, int(top_k * 5)))


# Singleton instance (lazy initialization)
_retrieval_service: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the singleton retrieval service instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
