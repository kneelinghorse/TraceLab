"""Hybrid search service combining semantic (Qdrant) and keyword (PostgreSQL) results."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.services.faceted_search import FacetedSearchService, FacetFilters
from app.services.pedr import (
    QualityFilters,
    QualityScoringService,
    get_quality_scoring_service,
)
from app.services.pedr.syntactic import (
    SyntacticFilters,
    SyntacticService,
    get_syntactic_service,
)
from app.services.retrieval_service import RetrievalService, get_retrieval_service

SessionFactory = Callable[[], Session]


class HybridSearchService:
    """Execute semantic, keyword, or hybrid searches with weighted scoring."""

    VALID_MODES = {"semantic", "keyword", "hybrid"}

    def __init__(
        self,
        *,
        retrieval_service: RetrievalService | None = None,
        session_factory: SessionFactory = SessionLocal,
        semantic_weight: float | None = None,
        keyword_weight: float | None = None,
        keyword_language: str | None = None,
        keyword_limit_multiplier: int | None = None,
        faceted_service: FacetedSearchService | None = None,
        quality_service: QualityScoringService | None = None,
        syntactic_service: SyntacticService | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.session_factory = session_factory
        semantic_weight = (
            semantic_weight
            if semantic_weight is not None
            else settings.hybrid_search_semantic_weight
        )
        keyword_weight = (
            keyword_weight
            if keyword_weight is not None
            else settings.hybrid_search_keyword_weight
        )
        total = semantic_weight + keyword_weight
        if total <= 0:
            raise ValueError("Hybrid search weights must be greater than zero.")
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
        self.keyword_language = (
            keyword_language or settings.hybrid_search_keyword_language
        ).lower()
        multiplier = (
            keyword_limit_multiplier or settings.hybrid_search_result_multiplier
        )
        self.keyword_limit_multiplier = (
            multiplier if multiplier and multiplier > 0 else 1
        )
        self.faceted_service = faceted_service or FacetedSearchService(
            session_factory=session_factory
        )
        self.quality_service = quality_service or get_quality_scoring_service()
        self.syntactic_service = syntactic_service or get_syntactic_service()

    def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        search_mode: str = "semantic",
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        document_types: list[str] | None = None,
        source_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        tags: list[str] | None = None,
        hnsw_ef: int | None = None,
        query_embedding: list[float] | None = None,
        include_embeddings: bool = False,
        min_quality_gates: int | None = None,
        status_filters: list[str] | None = None,
        allow_pii: bool | None = None,
        governance_mode: str | None = None,
        element_type: str | None = None,
        element_types: list[str] | None = None,
        auto_detect_type: bool = True,
        type_boost_enabled: bool = True,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute the requested search mode and return ranked chunks."""
        normalized_mode = (search_mode or "semantic").strip().lower()
        if normalized_mode not in self.VALID_MODES:
            raise ValueError(
                f"Unsupported search_mode '{search_mode}'. Expected one of {sorted(self.VALID_MODES)}."
            )

        limit = max(1, int(top_k))
        if allowed_project_ids == [] or (
            allowed_project_ids is not None
            and project_id is not None
            and str(project_id)
            not in {str(allowed_id) for allowed_id in allowed_project_ids}
        ):
            return []

        facet_filters = FacetFilters.from_kwargs(
            project_id=project_id,
            document_types=document_types,
            source_types=source_types,
            source_type=source_type,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
        )
        quality_filters = QualityFilters(
            min_quality_gates=min_quality_gates,
            statuses=tuple(status_filters or ()),
            allow_pii=allow_pii,
            governance_mode=governance_mode or "strict",
        )
        syntactic_filters = self.syntactic_service.create_filters(
            element_type=element_type,
            element_types=element_types,
            query=query,
            auto_detect=auto_detect_type,
            type_boost_enabled=type_boost_enabled,
        )

        if normalized_mode == "semantic":
            semantic_only_kwargs: dict[str, Any] = dict(
                query=query,
                top_k=limit,
                project_id=project_id,
                document_id=document_id,
                source_type=source_type,
                document_types=document_types,
                source_types=source_types,
                date_from=date_from,
                date_to=date_to,
                tags=tags,
                hnsw_ef=hnsw_ef,
                query_embedding=query_embedding,
                include_embeddings=include_embeddings,
            )
            if allowed_project_ids is not None:
                semantic_only_kwargs["allowed_project_ids"] = allowed_project_ids
            semantic_only = self._semantic_only(**semantic_only_kwargs)
            quality_scored = self._apply_quality_scoring(
                semantic_only, limit=limit, quality_filters=quality_filters
            )
            return self._apply_syntactic_processing(
                quality_scored, limit=limit, syntactic_filters=syntactic_filters
            )

        if normalized_mode == "keyword":
            keyword_kwargs: dict[str, Any] = dict(
                query=query,
                project_id=project_id,
                document_id=document_id,
                source_type=source_type,
                filters=facet_filters,
                limit=limit,
            )
            if allowed_project_ids is not None:
                keyword_kwargs["allowed_project_ids"] = allowed_project_ids
            keyword_results = self._keyword_search(**keyword_kwargs)
            keyword_results = self._filter_allowed_projects(
                keyword_results,
                allowed_project_ids,
                project_id=project_id,
                document_id=document_id,
            )
            finalized = self._finalize_keyword_results(keyword_results, limit=limit)
            quality_scored = self._apply_quality_scoring(
                finalized, limit=limit, quality_filters=quality_filters
            )
            return self._apply_syntactic_processing(
                quality_scored, limit=limit, syntactic_filters=syntactic_filters
            )

        semantic_kwargs: dict[str, Any] = dict(
            query=query,
            top_k=limit * self.keyword_limit_multiplier,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            document_types=document_types,
            source_types=source_types,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            hnsw_ef=hnsw_ef,
            query_embedding=query_embedding,
            include_embeddings=include_embeddings,
        )
        if allowed_project_ids is not None:
            semantic_kwargs["allowed_project_ids"] = allowed_project_ids
        semantic_results = self.retrieval_service.search(**semantic_kwargs)
        semantic_results = self._filter_allowed_projects(
            semantic_results,
            allowed_project_ids,
            project_id=project_id,
            document_id=document_id,
        )
        hybrid_keyword_kwargs: dict[str, Any] = dict(
            query=query,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            filters=facet_filters,
            limit=limit * self.keyword_limit_multiplier,
        )
        if allowed_project_ids is not None:
            hybrid_keyword_kwargs["allowed_project_ids"] = allowed_project_ids
        keyword_results = self._keyword_search(**hybrid_keyword_kwargs)
        keyword_results = self._filter_allowed_projects(
            keyword_results,
            allowed_project_ids,
            project_id=project_id,
            document_id=document_id,
        )
        merged = self._merge_results(semantic_results, keyword_results, limit=limit)
        quality_scored = self._apply_quality_scoring(
            merged, limit=limit, quality_filters=quality_filters
        )
        return self._apply_syntactic_processing(
            quality_scored, limit=limit, syntactic_filters=syntactic_filters
        )

    def _semantic_only(
        self,
        *,
        query: str,
        top_k: int,
        project_id: str | None,
        document_id: str | None,
        source_type: str | None,
        document_types: list[str] | None,
        source_types: list[str] | None,
        date_from: date | None,
        date_to: date | None,
        tags: list[str] | None,
        hnsw_ef: int | None,
        query_embedding: list[float] | None,
        include_embeddings: bool,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Delegate to the semantic retriever and annotate payloads."""
        semantic_kwargs: dict[str, Any] = dict(
            query=query,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            document_types=document_types,
            source_types=source_types,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            hnsw_ef=hnsw_ef,
            query_embedding=query_embedding,
            include_embeddings=include_embeddings,
        )
        if allowed_project_ids is not None:
            semantic_kwargs["allowed_project_ids"] = allowed_project_ids
        results = self.retrieval_service.search(**semantic_kwargs)
        results = self._filter_allowed_projects(
            results,
            allowed_project_ids,
            project_id=project_id,
            document_id=document_id,
        )
        annotated: list[dict[str, Any]] = []
        for result in results:
            payload = dict(result)
            payload.setdefault("semantic_score", float(payload.get("score") or 0.0))
            payload.setdefault("keyword_score", 0.0)
            payload.setdefault("search_mode", "semantic")
            payload.setdefault("combined_score", payload["semantic_score"])
            annotated.append(payload)
        return annotated

    def _keyword_search(
        self,
        *,
        query: str,
        project_id: str | None,
        document_id: str | None,
        source_type: str | None,
        source_origin: str | None = None,
        filters: FacetFilters,
        limit: int,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute PostgreSQL full-text search via SQLAlchemy."""
        if not query.strip():
            return []
        if allowed_project_ids == []:
            return []

        session = self.session_factory()
        try:
            ts_query = func.websearch_to_tsquery(self.keyword_language, query)
            rank = func.ts_rank_cd(DocumentChunk.content_tsv, ts_query).label("score")
            stmt = (
                select(
                    DocumentChunk.id.label("chunk_id"),
                    DocumentChunk.content,
                    DocumentChunk.chunk_index,
                    DocumentChunk.document_id,
                    Document.project_id.label("project_id"),
                    Document.source_type,
                    rank,
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.content_tsv.op("@@")(ts_query))
                .order_by(rank.desc())
                .limit(limit)
            )

            stmt = self.faceted_service.apply_sql_filters(stmt, filters)
            project_uuid = self._coerce_uuid(project_id)
            document_uuid = self._coerce_uuid(document_id)
            if project_uuid:
                stmt = stmt.where(Document.project_id == project_uuid)
            if document_uuid:
                stmt = stmt.where(DocumentChunk.document_id == document_uuid)
            if source_type:
                stmt = stmt.where(Document.source_type == source_type)
            if source_origin:
                stmt = stmt.where(Document.source_origin == source_origin)
            if allowed_project_ids is not None:
                stmt = stmt.where(Document.project_id.in_(allowed_project_ids))

            rows = session.execute(stmt).all()
            results: list[dict[str, Any]] = []
            for row in rows:
                mapping = row._mapping  # SQLAlchemy 1.4+/2.0 row interface
                results.append(
                    {
                        "chunk_id": str(mapping["chunk_id"]),
                        "content": mapping["content"],
                        "document_id": str(mapping["document_id"]),
                        "project_id": str(mapping["project_id"])
                        if mapping["project_id"]
                        else None,
                        "chunk_index": mapping["chunk_index"],
                        "source_type": mapping["source_type"],
                        "score": float(mapping["score"] or 0.0),
                    }
                )
            return self.faceted_service.filter_chunks(results, filters)
        finally:
            session.close()

    def _finalize_keyword_results(
        self, results: list[dict[str, Any]], *, limit: int
    ) -> list[dict[str, Any]]:
        """Normalize keyword-only results for consistent payloads."""
        normalized = self._normalize_scores(
            results, score_key="score", target_key="keyword_score"
        )
        final: list[dict[str, Any]] = []
        for payload in normalized[:limit]:
            entry = dict(payload)
            entry["semantic_score"] = 0.0
            entry["combined_score"] = entry.get("keyword_score", 0.0)
            entry["search_mode"] = "keyword"
            final.append(entry)
        return final

    def _merge_results(
        self,
        semantic_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Normalize and merge results using configured weights."""
        semantic_norm = self._normalize_scores(
            semantic_results, score_key="score", target_key="semantic_score"
        )
        keyword_norm = self._normalize_scores(
            keyword_results, score_key="score", target_key="keyword_score"
        )

        combined: dict[str, dict[str, Any]] = {}
        for result in semantic_norm:
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue
            entry = dict(result)
            semantic_score = float(entry.get("semantic_score") or 0.0)
            entry["keyword_score"] = float(entry.get("keyword_score") or 0.0)
            entry["combined_score"] = semantic_score * self.semantic_weight
            entry["search_mode"] = "semantic"
            entry["score"] = entry["combined_score"]
            combined[chunk_id] = entry

        for result in keyword_norm:
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue
            normalized_keyword = float(result.get("keyword_score") or 0.0)
            if chunk_id in combined:
                entry = combined[chunk_id]
                entry["keyword_score"] = normalized_keyword
                entry["combined_score"] += normalized_keyword * self.keyword_weight
                entry["score"] = entry["combined_score"]
                entry["search_mode"] = (
                    "hybrid" if entry.get("semantic_score", 0.0) else "keyword"
                )
                continue
            entry = dict(result)
            entry["semantic_score"] = 0.0
            entry["keyword_score"] = normalized_keyword
            entry["combined_score"] = normalized_keyword * self.keyword_weight
            entry["score"] = entry["combined_score"]
            entry["search_mode"] = "keyword"
            combined[chunk_id] = entry

        return sorted(
            combined.values(),
            key=lambda item: float(item.get("combined_score") or 0.0),
            reverse=True,
        )

    def _apply_quality_scoring(
        self,
        results: list[dict[str, Any]],
        *,
        limit: int,
        quality_filters: QualityFilters,
    ) -> list[dict[str, Any]]:
        """Annotate and re-rank results with PEDR quality metadata."""
        if not results or self.quality_service is None:
            return results[:limit]
        annotated = self.quality_service.apply(results, filters=quality_filters)
        ranked = sorted(
            annotated,
            key=lambda item: float(item.get("combined_score") or 0.0),
            reverse=True,
        )
        return ranked[:limit]

    @staticmethod
    def _filter_allowed_projects(
        results: list[dict[str, Any]],
        allowed_project_ids: list[UUID] | None,
        *,
        project_id: str | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fail closed if an upstream provider ignores request filters."""
        if allowed_project_ids is None:
            return results
        allowed = {str(allowed_id) for allowed_id in allowed_project_ids}
        filtered: list[dict[str, Any]] = []
        for result in results:
            result_project_id = result.get("project_id")
            result_document_id = result.get("document_id")
            if (
                result_project_id is None or str(result_project_id) not in allowed
            ):
                continue
            if project_id is not None and str(result_project_id) != str(project_id):
                continue
            if (
                document_id is not None
                and str(result_document_id) != str(document_id)
            ):
                continue
            filtered.append(result)
        return filtered

    def _apply_syntactic_processing(
        self,
        results: list[dict[str, Any]],
        *,
        limit: int,
        syntactic_filters: SyntacticFilters,
    ) -> list[dict[str, Any]]:
        """Apply PEDR syntactic layer: type detection, filtering, and boosting."""
        if not results or self.syntactic_service is None:
            return results[:limit]

        # Apply type boost (re-ranks based on element type match)
        processed = self.syntactic_service.apply(
            results,
            filters=syntactic_filters,
            filter_mode=False,  # Boost only, don't filter out results
        )

        # Re-sort by combined_score after type boost
        ranked = sorted(
            processed,
            key=lambda item: float(item.get("combined_score") or 0.0),
            reverse=True,
        )
        return ranked[:limit]

    @staticmethod
    def _normalize_scores(
        results: list[dict[str, Any]],
        *,
        score_key: str,
        target_key: str,
    ) -> list[dict[str, Any]]:
        """Apply min-max normalization to the provided score field."""
        if not results:
            return []

        scores = [float(result.get(score_key) or 0.0) for result in results]
        minimum = min(scores)
        maximum = max(scores)
        span = maximum - minimum

        normalized: list[dict[str, Any]] = []
        for result, score in zip(results, scores, strict=True):
            payload = dict(result)
            if span <= 0:
                payload[target_key] = 1.0 if score > 0 or score == maximum else 0.0
            else:
                payload[target_key] = (score - minimum) / span
            normalized.append(payload)
        return normalized

    @staticmethod
    def _coerce_uuid(value: str | None) -> uuid.UUID | None:
        if value in (None, "", "*"):
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


_hybrid_search_service: HybridSearchService | None = None


def get_hybrid_search_service() -> HybridSearchService:
    """Return a singleton hybrid search service."""
    global _hybrid_search_service
    if _hybrid_search_service is None:
        _hybrid_search_service = HybridSearchService()
    return _hybrid_search_service
