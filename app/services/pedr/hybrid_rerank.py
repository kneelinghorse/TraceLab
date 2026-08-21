"""Hybrid Rerank Architecture for PEDR search.

This module implements the "FTS first, semantic rerank" pattern as an alternative
search strategy for latency-sensitive queries. The approach:

1. Stage 1: PostgreSQL FTS retrieves candidate pool (fast, <100ms)
2. Stage 2: Semantic reranking scores candidates using embeddings (<200ms)
3. Combined latency target: <300ms total

Benefits:
- FTS provides fast initial filtering using existing PostgreSQL GIN index
- Semantic search only runs on candidate pool vs full corpus
- Achieves <300ms latency while maintaining semantic quality

Trade-offs:
- Results depend on FTS candidate quality (may miss semantic-only matches)
- Slightly lower recall than full semantic search
- More complex orchestration

Reference: R19.0 Qdrant Optimization Research (cmos/reports/sprint-19/)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.qdrant_service import QdrantService, get_qdrant_service

logger = logging.getLogger(__name__)


# Type alias for rerank mode
RerankMode = Literal["full", "hybrid"]


@dataclass
class HybridRerankTimings:
    """Timing breakdown for hybrid rerank stages."""

    fts_ms: float = 0.0
    embedding_ms: float = 0.0
    rerank_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class HybridRerankResult:
    """Result from hybrid rerank search."""

    results: list[dict[str, Any]]
    timings: HybridRerankTimings
    mode_used: RerankMode
    fts_candidates_count: int
    fallback_used: bool


SessionFactory = Callable[[], Session]


class HybridReranker:
    """Two-stage search: FTS candidates → semantic rerank.

    This class implements the hybrid rerank pattern for PEDR search:
    - Stage 1: Use PostgreSQL full-text search to retrieve candidate chunks
    - Stage 2: Rerank candidates using semantic (embedding) similarity

    The approach trades slightly lower recall for significantly better latency.
    """

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        session_factory: SessionFactory = SessionLocal,
        fts_language: str = "english",
    ) -> None:
        """Initialize the hybrid reranker.

        Args:
            embedding_service: Service for generating query embeddings.
            qdrant_service: Service for retrieving vectors from Qdrant.
            session_factory: Factory for database sessions.
            fts_language: PostgreSQL text search language configuration.
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.qdrant_service = qdrant_service or get_qdrant_service()
        self.session_factory = session_factory
        self.fts_language = fts_language.lower()

    def search(
        self,
        *,
        query: str,
        top_k: int = 10,
        candidate_pool: int = 50,
        mode: RerankMode = "hybrid",
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        source_origin: str | None = None,
        hnsw_ef: int | None = None,
        include_embeddings: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> HybridRerankResult:
        """Execute hybrid rerank search.

        Args:
            query: Natural language search query.
            top_k: Number of final results to return.
            candidate_pool: Number of FTS candidates to retrieve (hybrid mode only).
            mode: Search mode - "full" for standard semantic, "hybrid" for FTS+rerank.
            project_id: Optional project UUID filter.
            document_id: Optional document UUID filter.
            source_type: Optional source type filter.
            hnsw_ef: HNSW ef override for full semantic search.
            allowed_project_ids: Request-local readable project scope.

        Returns:
            HybridRerankResult with results, timings, and metadata.
        """
        start_time = time.perf_counter()
        timings = HybridRerankTimings()

        if allowed_project_ids == [] or (
            allowed_project_ids is not None
            and project_id is not None
            and str(project_id)
            not in {str(allowed_id) for allowed_id in allowed_project_ids}
        ):
            timings.total_ms = (time.perf_counter() - start_time) * 1000
            return HybridRerankResult(
                results=[],
                timings=timings,
                mode_used=mode,
                fts_candidates_count=0,
                fallback_used=False,
            )

        full_search_kwargs: dict[str, Any] = dict(
            query=query,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            source_origin=source_origin,
            hnsw_ef=hnsw_ef,
            include_embeddings=include_embeddings,
        )
        if allowed_project_ids is not None:
            full_search_kwargs["allowed_project_ids"] = allowed_project_ids

        if mode == "full":
            # Standard semantic search (delegate to existing retrieval)
            results = self._full_semantic_search(**full_search_kwargs)
            timings.total_ms = (time.perf_counter() - start_time) * 1000
            return HybridRerankResult(
                results=results,
                timings=timings,
                mode_used="full",
                fts_candidates_count=0,
                fallback_used=False,
            )

        # Hybrid mode: FTS → Semantic Rerank

        # Stage 1: FTS candidates
        t0 = time.perf_counter()
        fts_kwargs: dict[str, Any] = dict(
            query=query,
            limit=candidate_pool,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            source_origin=source_origin,
        )
        if allowed_project_ids is not None:
            fts_kwargs["allowed_project_ids"] = allowed_project_ids
        candidates = self._fts_candidates(**fts_kwargs)
        candidates = self._filter_results_by_scope(
            candidates,
            allowed_project_ids=allowed_project_ids,
            project_id=project_id,
            document_id=document_id,
        )
        timings.fts_ms = (time.perf_counter() - t0) * 1000
        fts_count = len(candidates)

        if not candidates:
            # Fallback to full semantic if FTS returns nothing
            logger.info(
                "Hybrid rerank: FTS returned no candidates, falling back to full semantic"
            )
            results = self._full_semantic_search(**full_search_kwargs)
            timings.total_ms = (time.perf_counter() - start_time) * 1000
            return HybridRerankResult(
                results=results,
                timings=timings,
                mode_used="hybrid",
                fts_candidates_count=0,
                fallback_used=True,
            )

        # Stage 2: Generate query embedding
        t0 = time.perf_counter()
        query_embedding = self.embedding_service.generate_embedding(query)
        timings.embedding_ms = (time.perf_counter() - t0) * 1000

        # Stage 3: Semantic rerank
        t0 = time.perf_counter()
        reranked = self._semantic_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            top_k=top_k,
            include_embeddings=include_embeddings,
        )
        timings.rerank_ms = (time.perf_counter() - t0) * 1000

        timings.total_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            "Hybrid rerank: FTS=%.1fms (%d candidates), embed=%.1fms, rerank=%.1fms, total=%.1fms",
            timings.fts_ms,
            fts_count,
            timings.embedding_ms,
            timings.rerank_ms,
            timings.total_ms,
        )

        return HybridRerankResult(
            results=reranked,
            timings=timings,
            mode_used="hybrid",
            fts_candidates_count=fts_count,
            fallback_used=False,
        )

    def _fts_candidates(
        self,
        *,
        query: str,
        limit: int,
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        source_origin: str | None = None,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve candidate chunks using PostgreSQL full-text search.

        Uses the existing content_tsv GIN index on document_chunks table
        for fast keyword matching.

        Args:
            query: Search query.
            limit: Maximum candidates to retrieve.
            project_id: Optional project filter.
            document_id: Optional document filter.
            source_type: Optional source type filter.

        Returns:
            List of candidate chunk dictionaries with FTS scores.
        """
        if not query.strip():
            return []
        if allowed_project_ids == []:
            return []

        session = self.session_factory()
        try:
            ts_query = func.websearch_to_tsquery(self.fts_language, query)
            rank = func.ts_rank_cd(DocumentChunk.content_tsv, ts_query).label(
                "fts_score"
            )

            stmt = (
                select(
                    DocumentChunk.id.label("chunk_id"),
                    DocumentChunk.content,
                    DocumentChunk.document_id,
                    DocumentChunk.chunk_index,
                    Document.project_id,
                    Document.source_type,
                    Document.source_origin,
                    rank,
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.content_tsv.op("@@")(ts_query))
                .order_by(rank.desc())
                .limit(limit)
            )

            # Apply filters
            if project_id:
                from uuid import UUID

                stmt = stmt.where(Document.project_id == UUID(project_id))
            if document_id:
                from uuid import UUID

                stmt = stmt.where(DocumentChunk.document_id == UUID(document_id))
            if source_type:
                stmt = stmt.where(Document.source_type == source_type)
            if source_origin:
                stmt = stmt.where(Document.source_origin == source_origin)
            if allowed_project_ids is not None:
                stmt = stmt.where(Document.project_id.in_(allowed_project_ids))

            rows = session.execute(stmt).all()

            candidates = []
            for row in rows:
                mapping = row._mapping
                candidates.append(
                    {
                        "chunk_id": str(mapping["chunk_id"]),
                        "content": mapping["content"],
                        "document_id": str(mapping["document_id"]),
                        "project_id": str(mapping["project_id"])
                        if mapping["project_id"]
                        else None,
                        "chunk_index": mapping["chunk_index"],
                        "source_type": mapping["source_type"],
                        "source_origin": mapping["source_origin"],
                        "fts_score": float(mapping["fts_score"] or 0.0),
                    }
                )
            return candidates

        finally:
            session.close()

    def _semantic_rerank(
        self,
        *,
        query_embedding: list[float],
        candidates: list[dict[str, Any]],
        top_k: int,
        include_embeddings: bool = False,
    ) -> list[dict[str, Any]]:
        """Rerank candidates using semantic similarity.

        Retrieves embeddings from Qdrant for candidates and computes
        cosine similarity with the query embedding.

        Args:
            query_embedding: Query vector from embedding service.
            candidates: FTS candidate chunks.
            top_k: Number of results to return.

        Returns:
            Top-k candidates reranked by semantic similarity.
        """
        if not candidates:
            return []

        # Get chunk IDs for Qdrant retrieval
        chunk_ids = [c["chunk_id"] for c in candidates]

        # Retrieve vectors from Qdrant
        try:
            points = self.qdrant_service.client.retrieve(
                collection_name=self.qdrant_service.collection_name,
                ids=chunk_ids,
                with_vectors=True,
            )
        except Exception as e:
            logger.warning("Failed to retrieve vectors for reranking: %s", e)
            # Fallback: return candidates ordered by FTS score
            return sorted(
                candidates,
                key=lambda x: x.get("fts_score", 0.0),
                reverse=True,
            )[:top_k]

        # Build ID → vector mapping
        id_to_vector: dict[str, list[float]] = {}
        for point in points:
            vector = point.vector
            if isinstance(vector, dict):
                # Named vectors: take first available
                vector = next(iter(vector.values()), None)
            if vector is not None:
                id_to_vector[str(point.id)] = vector

        # Batch cosine computation (matrix multiply) for better rerank latency.
        candidate_ids: list[str] = []
        candidate_vectors: list[list[float]] = []
        for chunk_id in chunk_ids:
            vector = id_to_vector.get(chunk_id)
            if vector is None:
                continue
            candidate_ids.append(chunk_id)
            candidate_vectors.append(vector)

        if not candidate_ids:
            return sorted(
                candidates,
                key=lambda x: x.get("fts_score", 0.0),
                reverse=True,
            )[:top_k]

        query_np = np.asarray(query_embedding, dtype=np.float32)
        query_norm = float(np.linalg.norm(query_np))
        vectors_np = np.asarray(candidate_vectors, dtype=np.float32)
        vector_norms = np.linalg.norm(vectors_np, axis=1)
        scores = np.zeros(len(candidate_ids), dtype=np.float32)

        if query_norm > 0:
            denom = vector_norms * query_norm
            valid_mask = denom > 0
            if np.any(valid_mask):
                dot = vectors_np @ query_np
                scores[valid_mask] = dot[valid_mask] / denom[valid_mask]

        ordered_indices = np.argsort(scores)[::-1]

        # Map back to candidates and annotate with scores
        id_to_candidate = {c["chunk_id"]: c for c in candidates}
        reranked: list[dict[str, Any]] = []

        for idx in ordered_indices[:top_k]:
            chunk_id = candidate_ids[int(idx)]
            semantic_score = float(scores[int(idx)])
            if chunk_id not in id_to_candidate:
                continue
            candidate = id_to_candidate[chunk_id].copy()
            candidate["semantic_score"] = float(semantic_score)
            candidate["score"] = float(semantic_score)  # Primary score for ranking
            candidate["combined_score"] = float(semantic_score)
            candidate["search_mode"] = "hybrid"
            if include_embeddings:
                candidate["embedding"] = id_to_vector.get(chunk_id)
            reranked.append(candidate)

        return reranked

    def _full_semantic_search(
        self,
        *,
        query: str,
        top_k: int,
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        source_origin: str | None = None,
        hnsw_ef: int | None = None,
        include_embeddings: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute full semantic search via retrieval service.

        Args:
            query: Search query.
            top_k: Number of results.
            project_id: Optional project filter.
            document_id: Optional document filter.
            source_type: Optional source type filter.
            hnsw_ef: HNSW ef override.

        Returns:
            List of results from semantic search.
        """
        # Generate embedding
        embedding = self.embedding_service.generate_embedding(query)

        # Search via Qdrant service
        search_kwargs: dict[str, Any] = dict(
            query_vector=embedding,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            source_origin=source_origin,
            hnsw_ef=hnsw_ef,
            with_vectors=include_embeddings,
        )
        if allowed_project_ids is not None:
            search_kwargs["allowed_project_ids"] = allowed_project_ids
        results = self.qdrant_service.search_chunks(**search_kwargs)
        results = self._filter_results_by_scope(
            results,
            allowed_project_ids=allowed_project_ids,
            project_id=project_id,
            document_id=document_id,
        )

        # Annotate results for consistency
        for result in results:
            result["semantic_score"] = result.get("score", 0.0)
            result["combined_score"] = result.get("score", 0.0)
            result["search_mode"] = "semantic"
            result["fts_score"] = 0.0

        return results

    @staticmethod
    def _filter_results_by_scope(
        results: list[dict[str, Any]],
        *,
        allowed_project_ids: list[UUID] | None,
        project_id: str | None,
        document_id: str | None,
    ) -> list[dict[str, Any]]:
        """Fail closed if either rerank backend ignores request filters."""
        if allowed_project_ids is None:
            return results
        allowed = {str(allowed_id) for allowed_id in allowed_project_ids}
        return [
            result
            for result in results
            if (
                result.get("project_id") is not None
                and str(result["project_id"]) in allowed
            )
            and (
                project_id is None
                or str(result.get("project_id")) == str(project_id)
            )
            and (
                document_id is None
                or str(result.get("document_id")) == str(document_id)
            )
        ]

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity in range [-1, 1].
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


# Singleton instance
_hybrid_reranker: HybridReranker | None = None


def get_hybrid_reranker() -> HybridReranker:
    """Get or create the singleton hybrid reranker instance."""
    global _hybrid_reranker
    if _hybrid_reranker is None:
        _hybrid_reranker = HybridReranker()
    return _hybrid_reranker


__all__ = [
    "RerankMode",
    "HybridRerankTimings",
    "HybridRerankResult",
    "HybridReranker",
    "get_hybrid_reranker",
]
