"""RAG service that orchestrates retrieval, compression, and answer generation."""

import logging
import re
import time
from datetime import date
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.services.cache_manager import get_cache_manager
from app.services.context_compression import compress_context
from app.services.cost_monitor import CostMonitor, get_cost_monitor
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.faceted_search import FacetFilters
from app.services.pedr.graph_rag import GraphRAGHelper
from app.services.pedr.search_orchestrator import (
    PEDRSearchOrchestrator,
    create_pedr_orchestrator,
)
from app.services.pedr.semantic_protocol import URNGenerator
from app.services.quality_assessment import (
    QualityAssessmentConfig,
    QualityAssessmentResult,
    QualityAssessor,
)
from app.services.retrieval_service import RetrievalService, get_retrieval_service
from app.services.semantic_cache import SemanticCacheService, get_semantic_cache_service

try:  # pragma: no cover - allow import without OpenAI SDK in some environments
    from openai import APIError, OpenAI, RateLimitError
except ModuleNotFoundError as exc:  # pragma: no cover
    OpenAI = None  # type: ignore
    APIError = RateLimitError = Exception  # type: ignore
    _openai_import_error = exc
else:
    _openai_import_error = None


logger = logging.getLogger(__name__)


_UNSET = object()


_CITATION_PATTERN = re.compile(
    r"\[Document:\s*(?P<document>[^\],]+),\s*Chunk:\s*(?P<chunk>[^\]]+)\]",
    re.IGNORECASE,
)


MODEL_COST_ESTIMATES = {
    # Fallback estimate per attempt when token usage is unavailable.
    "gpt-5.1": 0.0010,
    "gpt-5.2": 0.0016,
}


def build_empty_scope_result(
    *,
    search_mode: str,
    primary_model: str | None = None,
    compression_threshold: float | None = None,
    quality_threshold: float | None = None,
    routing_metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build a normal empty response without constructing caches or providers."""
    return {
        "answer": "No accessible sources were found for this query.",
        "citations": [],
        "sources": [],
        "latency_ms": 0.0,
        "compression": {
            "original_chunks": 0,
            "filtered_chunks": 0,
            "original_tokens": 0,
            "filtered_tokens": 0,
            "reduction_ratio": 0.0,
            "threshold": (
                settings.rag_context_threshold
                if compression_threshold is None
                else compression_threshold
            ),
            "compression_ms": 0.0,
        },
        "cache": {
            "hit": False,
            "score": None,
            "age_seconds": None,
            "ttl_seconds": None,
        },
        "quality": {
            "composite_score": 0.0,
            "threshold": (
                settings.tiered_routing_threshold
                if quality_threshold is None
                else quality_threshold
            ),
            "pillar_scores": {
                "linguistic_uncertainty": 0.0,
                "answer_integrity": 0.0,
                "source_provenance": 0.0,
            },
            "hard_failures": ["no_accessible_sources"],
            "reasons": ["The request authorization scope contains no projects."],
            "pre_escalation_score": None,
        },
        "routing": {
            "selected_model": primary_model or settings.openai_chat_model,
            "escalated": False,
            "attempts": [],
            "estimated_cost_usd": 0.0,
            "metrics": dict(routing_metrics or {"total_queries": 0, "escalations": 0}),
        },
        "search_mode": (search_mode or "semantic").strip().lower(),
    }


class RagService:
    """Compose semantic retrieval with GPT answer generation."""

    GRAPH_CONTEXT_DEPTH = 2
    GRAPH_CONTEXT_MAX_NODES = 50
    GRAPH_CONTEXT_MAX_TOKENS = 800
    GRAPH_CONTEXT_SEED_LIMIT = 8

    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        pedr_orchestrator: PEDRSearchOrchestrator | None = None,
        embedding_service: EmbeddingService | None = None,
        cache_service: SemanticCacheService | None = None,
        client: OpenAI | None = None,  # type: ignore[name-defined]
        model: str | None = None,
        escalation_model: str | None = None,
        default_temperature: float | None = None,
        quality_assessor: QualityAssessor | None = None,
        cost_monitor: CostMonitor | None | object = _UNSET,
        graph_rag_helper: GraphRAGHelper | None = None,
    ) -> None:
        if _openai_import_error is not None:
            raise RuntimeError(
                "The OpenAI SDK is required for RAG answer generation. Install dependencies from requirements.txt."
            ) from _openai_import_error

        if client is None:
            if not settings.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY must be set for RAG answer generation."
                )
            client = OpenAI(api_key=settings.openai_api_key)

        self.client = client
        # retrieval_service is only needed if PEDR orchestrator needs to be created
        self.retrieval_service = retrieval_service
        if pedr_orchestrator is not None:
            self.pedr_orchestrator = pedr_orchestrator
        else:
            # Only create retrieval_service if needed by PEDR factory
            self.retrieval_service = retrieval_service or get_retrieval_service()
            self.pedr_orchestrator = create_pedr_orchestrator()
        self.embedding_service = embedding_service or get_embedding_service()
        self.cache_service = (
            cache_service
            if cache_service is not None
            else (
                get_semantic_cache_service()
                if settings.semantic_cache_enabled
                else None
            )
        )
        self.primary_model = model or settings.openai_chat_model
        self.model = (
            self.primary_model
        )  # maintain backwards compatibility for callers accessing .model
        self.escalation_model = escalation_model or getattr(
            settings, "openai_escalation_model", "gpt-5.2"
        )
        self.default_temperature = (
            default_temperature
            if default_temperature is not None
            else settings.openai_chat_temperature
        )
        self.default_max_tokens = settings.rag_default_max_tokens
        self.compression_threshold = settings.rag_context_threshold
        if quality_assessor is None:
            quality_config = QualityAssessmentConfig(
                escalation_threshold=getattr(
                    settings, "tiered_routing_threshold", 0.85
                ),
                linguistic_weight=getattr(settings, "tiered_weight_linguistic", 0.35),
                integrity_weight=getattr(settings, "tiered_weight_integrity", 0.35),
                provenance_weight=getattr(settings, "tiered_weight_provenance", 0.30),
            )
            quality_assessor = QualityAssessor(quality_config)
        self.quality_assessor = quality_assessor
        self.routing_metrics = {"total_queries": 0, "escalations": 0}
        self.cost_monitor = (
            get_cost_monitor() if cost_monitor is _UNSET else cost_monitor
        )
        self.cache_manager = get_cache_manager()
        self.graph_rag_helper = graph_rag_helper or GraphRAGHelper(
            model_name=self.primary_model
        )

    def run_query(
        self,
        query: str,
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
        source_type: str | None = None,
        document_types: list[str] | None = None,
        source_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        tags: list[str] | None = None,
        hnsw_ef: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        search_mode: str = "semantic",
        min_quality_gates: int | None = None,
        status_filters: list[str] | None = None,
        allow_pii: bool | None = True,
        governance_mode: str | None = None,
        element_type: str | None = None,
        element_types: list[str] | None = None,
        auto_detect_type: bool = True,
        type_boost_enabled: bool = True,
        include_graph_context: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a full RAG workflow: retrieve context and synthesize an answer.
        """
        normalized_mode = (search_mode or "semantic").strip().lower()
        allowed_project_scope = self._normalize_project_scope(allowed_project_ids)
        if allowed_project_scope == () or (
            allowed_project_scope is not None
            and project_id is not None
            and str(project_id) not in set(allowed_project_scope)
        ):
            return self._empty_scope_result(search_mode=normalized_mode)

        filters = FacetFilters.from_kwargs(
            project_id=project_id,
            document_types=document_types,
            source_types=source_types,
            source_type=source_type,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
        )
        filters_signature = filters.signature()
        if allowed_project_scope is not None:
            filters_signature = self._scoped_filters_signature(
                filters_signature,
                allowed_project_scope,
            )
        cache_key = self.cache_manager.rag_query_key(
            query=query,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
            search_mode=normalized_mode,
            filters_signature=filters_signature,
            quality_signature=self._quality_filter_signature(
                min_quality_gates=min_quality_gates,
                statuses=status_filters,
                allow_pii=allow_pii,
                governance_mode=governance_mode,
            ),
            graph_context_enabled=include_graph_context,
        )
        start = time.perf_counter()

        def _loader() -> dict[str, Any]:
            return self._execute_rag_pipeline(
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
                temperature=temperature,
                max_tokens=max_tokens,
                search_mode=normalized_mode,
                min_quality_gates=min_quality_gates,
                status_filters=status_filters,
                allow_pii=allow_pii,
                governance_mode=governance_mode,
                element_type=element_type,
                element_types=element_types,
                auto_detect_type=auto_detect_type,
                type_boost_enabled=type_boost_enabled,
                include_graph_context=include_graph_context,
                allowed_project_ids=(
                    [UUID(project_id) for project_id in allowed_project_scope]
                    if allowed_project_scope is not None
                    else None
                ),
                filters_signature=filters_signature,
            )

        result, hit = self.cache_manager.cached_value(
            "rag_query_results", cache_key, _loader
        )
        cache_info = result.setdefault("cache", {})
        cache_info.setdefault("layer", "ttl")
        cache_info["ttl_seconds"] = self.cache_manager.ttl_seconds("rag_query_results")
        result.setdefault("search_mode", normalized_mode)

        if hit:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            cache_info["hit"] = True
            cache_info["source"] = "application_ttl"
            result["latency_ms"] = latency_ms
            self._record_cache_hit_event(
                query=query, project_id=project_id, latency_ms=latency_ms
            )
            if self.cache_service is not None:
                self._record_semantic_cache_hit(project_id)
            return result

        cache_info.setdefault("source", "application_ttl")
        return result

    def _execute_rag_pipeline(
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
        temperature: float | None,
        max_tokens: int | None,
        search_mode: str,
        min_quality_gates: int | None,
        status_filters: list[str] | None,
        allow_pii: bool | None,
        governance_mode: str | None,
        element_type: str | None = None,
        element_types: list[str] | None = None,
        auto_detect_type: bool = True,
        type_boost_enabled: bool = True,
        include_graph_context: bool = False,
        allowed_project_ids: list[UUID] | None = None,
        filters_signature: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        normalized_mode = (search_mode or "semantic").strip().lower()
        query_embedding = self.embedding_service.generate_embedding(query)
        cache_metadata = {
            "query": query,
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "document_types": list(document_types or []),
            "source_types": list(source_types or []),
            "tags": list(tags or []),
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "top_k": top_k,
            "temperature": temperature
            if temperature is not None
            else self.default_temperature,
            "max_tokens": max_tokens
            if max_tokens is not None
            else self.default_max_tokens,
            "search_mode": normalized_mode,
            "filters_signature": (
                filters_signature
                if filters_signature is not None
                else FacetFilters.from_kwargs(
                    project_id=project_id,
                    document_types=document_types,
                    source_types=source_types,
                    source_type=source_type,
                    tags=tags,
                    date_from=date_from,
                    date_to=date_to,
                ).signature()
            ),
            "min_quality_gates": min_quality_gates,
            "status_filters": list(status_filters or []),
            "allow_pii": allow_pii if allow_pii is not None else True,
            "governance_mode": governance_mode or "strict",
            "graph_context_enabled": include_graph_context,
        }

        if self.cache_service is not None:
            cached_result = self.cache_service.check_cache(
                query_embedding=query_embedding,
                metadata=cache_metadata,
            )
            if cached_result:
                response = dict(cached_result)
                response.setdefault("search_mode", normalized_mode)
                latency_ms = round((time.perf_counter() - start) * 1000, 2)
                response["latency_ms"] = latency_ms
                cache_info = response.get("cache") or {}
                cache_info["hit"] = True
                response["cache"] = cache_info
                self._record_cache_hit_event(
                    query=query,
                    project_id=project_id,
                    latency_ms=latency_ms,
                )
                return response

        # Use PEDR orchestrator for retrieval with proper RRF fusion
        search_kwargs: dict[str, Any] = dict(
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
            include_embeddings=True,
            element_type=element_type,
            element_types=element_types,
            auto_detect_type=auto_detect_type,
            type_boost_enabled=type_boost_enabled,
            min_quality_gates=min_quality_gates,
            status_filters=status_filters,
            allow_pii=allow_pii,
            governance_mode=governance_mode,
        )
        if allowed_project_ids is not None:
            search_kwargs["allowed_project_ids"] = allowed_project_ids
        pedr_response = self.pedr_orchestrator.search(**search_kwargs)

        # Convert PEDR results to dict format for context compression
        retrieved_chunks = [
            {
                "chunk_id": r.chunk_id,
                "content": r.content,
                "document_id": r.document_id,
                "project_id": r.project_id,
                "chunk_index": r.chunk_index,
                "source_type": r.source_type,
                "score": r.rrf_score,
                "embedding": r.embedding,
            }
            for r in pedr_response.results
        ]

        compressed_chunks, compression_metrics = compress_context(
            chunks=retrieved_chunks,
            query_embedding=query_embedding,
            threshold=self.compression_threshold,
        )

        graph_context = None
        if include_graph_context:
            graph_context = self._build_graph_context(
                query=query,
                chunks=compressed_chunks,
            )

        messages = self._build_messages(
            query=query,
            chunks=compressed_chunks,
            graph_context=graph_context,
        )
        (
            answer,
            citations,
            quality_report,
            routing_details,
            attempt_usages,
        ) = self._generate_with_tiered_routing(
            query=query,
            messages=messages,
            chunks=compressed_chunks,
            temperature=temperature
            if temperature is not None
            else self.default_temperature,
            max_tokens=max_tokens
            if max_tokens is not None
            else self.default_max_tokens,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        result = {
            "answer": answer,
            "citations": citations,
            "sources": compressed_chunks,
            "latency_ms": round(latency_ms, 2),
            "compression": compression_metrics,
            "cache": {"hit": False},
            "quality": quality_report,
            "routing": routing_details,
            "search_mode": normalized_mode,
        }

        if self.cache_service is not None:
            try:
                self.cache_service.store_in_cache(
                    query_embedding=query_embedding,
                    result=result,
                    metadata=cache_metadata,
                )
            except Exception:
                # Cache writes must never impact the primary query path.
                logger.debug("Semantic cache write failed", exc_info=True)

        total_cost = self._record_cost_events(
            attempts=routing_details.get("attempts", []),
            usage_records=attempt_usages,
            query=query,
            project_id=project_id,
            latency_ms=result["latency_ms"],
            cache_hit=False,
        )
        routing_details["estimated_cost_usd"] = round(total_cost, 6)
        return result

    @staticmethod
    def _normalize_project_scope(
        allowed_project_ids: list[UUID] | None,
    ) -> tuple[str, ...] | None:
        """Return a stable cache-safe representation of a request project scope."""
        if allowed_project_ids is None:
            return None
        return tuple(sorted({str(project_id) for project_id in allowed_project_ids}))

    @staticmethod
    def _scoped_filters_signature(
        filters_signature: str,
        allowed_project_scope: tuple[str, ...],
    ) -> str:
        """Bind both RAG cache layers to the canonical authorization scope."""
        return f"{filters_signature}|allowed_projects:{','.join(allowed_project_scope)}"

    def _empty_scope_result(self, *, search_mode: str) -> dict[str, Any]:
        """Return a normal empty result without consulting caches or providers."""
        threshold = getattr(
            getattr(self.quality_assessor, "config", None),
            "escalation_threshold",
            settings.tiered_routing_threshold,
        )
        return build_empty_scope_result(
            search_mode=search_mode,
            primary_model=self.primary_model,
            compression_threshold=self.compression_threshold,
            quality_threshold=threshold,
            routing_metrics=self.routing_metrics,
        )

    @staticmethod
    def _quality_filter_signature(
        *,
        min_quality_gates: int | None,
        statuses: list[str] | None,
        allow_pii: bool | None,
        governance_mode: str | None,
    ) -> str:
        """Generate a cache-friendly signature for governance filters."""
        if min_quality_gates is None:
            gates_token = "*"  # noqa: S105 - cache token, not a credential
        else:
            try:
                value = int(min_quality_gates)
            except (TypeError, ValueError):
                value = 0
            gates_token = str(max(0, min(5, value)))

        if statuses:
            normalized = sorted(
                {
                    str(status).strip().lower()
                    for status in statuses
                    if isinstance(status, str) and status.strip()
                }
            )
            status_token = ",".join(normalized) if normalized else "*"
        else:
            status_token = "*"  # noqa: S105 - cache token, not a credential

        pii_token = "no_pii" if allow_pii is False else "any"
        mode = (governance_mode or "strict").strip().lower()
        if mode not in {"strict", "soft", "warn"}:
            mode = "strict"
        return "|".join([gates_token, status_token, pii_token, mode])

    def _build_messages(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        graph_context: str | None = None,
    ) -> list[dict[str, str]]:
        """Compose chat messages incorporating retrieved context."""
        if chunks:
            context_blocks = []
            for chunk in chunks:
                document_id = chunk.get("document_id") or "Unknown"
                chunk_index = chunk.get("chunk_index")
                chunk_label = f"[Document: {document_id}, Chunk: {chunk_index if chunk_index is not None else 'N/A'}]"
                content = (chunk.get("content") or "").strip()
                context_blocks.append(f"{chunk_label}\n{content}")
            context_text = "\n\n".join(context_blocks)
        else:
            context_text = (
                "No relevant context was retrieved. If the query cannot be answered, "
                "state that the repository does not contain sufficient information."
            )

        if graph_context:
            context_text = f"{context_text}\n\n{graph_context}".strip()

        system_prompt = (
            "You are a meticulous research assistant. Use the provided context to answer the query. "
            "Every factual statement must be supported with a citation in the form [Document: <document_id>, Chunk: <chunk_index>]. "
            "If the context is insufficient, explicitly state that the answer cannot be determined."
        )
        user_prompt = (
            f"Query:\n{query.strip()}\n\n"
            "Context:\n"
            f"{context_text}\n\n"
            "Guidelines:\n"
            "- Answer concisely while covering the key points relevant to the query.\n"
            "- Include citations immediately after each sentence or claim that uses context.\n"
            "- Do not fabricate information or citations.\n"
            "- If the context is not helpful, say so and avoid speculation."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_graph_context(
        self,
        *,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> str | None:
        seeds = []
        for chunk in chunks[: self.GRAPH_CONTEXT_SEED_LIMIT]:
            urn = chunk.get("urn")
            if urn:
                seeds.append(str(urn))
                continue
            document_id = chunk.get("document_id")
            chunk_index = chunk.get("chunk_index")
            if document_id is not None and chunk_index is not None:
                urn_value = str(
                    URNGenerator.for_chunk(str(document_id), int(chunk_index))
                )
                seeds.append(urn_value)

        seeds = list(dict.fromkeys(seeds))
        if not seeds:
            return None

        subgraph = self.graph_rag_helper.extract_subgraph(
            seeds,
            depth=self.GRAPH_CONTEXT_DEPTH,
            max_nodes=self.GRAPH_CONTEXT_MAX_NODES,
        )
        if not subgraph.nodes:
            return None

        pruned = self.graph_rag_helper.prune_by_relevance(
            subgraph,
            query=query,
            max_tokens=self.GRAPH_CONTEXT_MAX_TOKENS,
        )
        if not pruned.nodes:
            return None

        rendered = self.graph_rag_helper.linearize(pruned)
        return rendered or None

    def _generate_with_tiered_routing(
        self,
        *,
        query: str,
        messages: list[dict[str, str]],
        chunks: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> tuple[
        str,
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, Any],
        list[dict[str, int] | None],
    ]:
        """Generate an answer using tiered routing and quality assessment."""
        attempts: list[dict[str, Any]] = []
        attempt_usages: list[dict[str, int] | None] = []

        primary_answer, primary_usage = self._generate_answer(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=self.primary_model,
        )
        attempt_usages.append(primary_usage)
        primary_citations = self._extract_citations(primary_answer, chunks)
        primary_quality = self.quality_assessor.assess(
            query=query,
            answer=primary_answer,
            citations=primary_citations,
            context_chunks=chunks,
        )
        attempts.append(
            self._format_attempt_record(
                model=self.primary_model,
                quality=primary_quality,
                citation_count=len(primary_citations),
                usage=primary_usage,
            )
        )

        final_answer = primary_answer
        final_citations = primary_citations
        final_quality = primary_quality
        escalated = False

        if primary_quality.escalate and self.escalation_model:
            escalated = True
            escalation_answer, escalation_usage = self._generate_answer(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                model=self.escalation_model,
            )
            final_answer = escalation_answer
            final_citations = self._extract_citations(escalation_answer, chunks)
            final_quality = self.quality_assessor.assess(
                query=query,
                answer=final_answer,
                citations=final_citations,
                context_chunks=chunks,
            )
            attempt_usages.append(escalation_usage)
            attempts.append(
                self._format_attempt_record(
                    model=self.escalation_model,
                    quality=final_quality,
                    citation_count=len(final_citations),
                    usage=escalation_usage,
                )
            )

        self.routing_metrics["total_queries"] += 1
        if escalated:
            self.routing_metrics["escalations"] += 1
            logger.info(
                "Tiered routing escalation triggered: %.2f (threshold %.2f)",
                primary_quality.composite_score,
                primary_quality.threshold,
            )
        else:
            logger.debug(
                "Tiered routing primary model sufficient: %.2f (threshold %.2f)",
                final_quality.composite_score,
                final_quality.threshold,
            )

        cost_estimate = sum(
            MODEL_COST_ESTIMATES.get(attempt["model"], 0.0) for attempt in attempts
        )
        quality_report: dict[str, Any] = {
            "composite_score": final_quality.composite_score,
            "threshold": final_quality.threshold,
            "pillar_scores": final_quality.pillar_scores,
            "hard_failures": final_quality.hard_failures,
            "reasons": final_quality.reasons,
        }
        if escalated:
            quality_report["pre_escalation_score"] = primary_quality.composite_score

        routing_details = {
            "selected_model": self.escalation_model
            if escalated
            else self.primary_model,
            "escalated": escalated,
            "attempts": attempts,
            "estimated_cost_usd": round(cost_estimate, 6),
            "metrics": dict(self.routing_metrics),
        }

        return (
            final_answer,
            final_citations,
            quality_report,
            routing_details,
            attempt_usages,
        )

    def _generate_answer(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        retry_max: int = 3,
        model: str | None = None,
    ) -> tuple[str, dict[str, int] | None]:
        """Call the OpenAI chat completion API with simple exponential backoff."""
        for attempt in range(retry_max):
            try:
                model_name = model if model is not None else self.primary_model
                is_gpt5 = model_name.lower().startswith(("gpt-5.1", "gpt-5.2"))
                request = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_completion_tokens" if is_gpt5 else "max_tokens": max_tokens,
                }
                if is_gpt5:
                    # GPT-5.1/5.2 support temperature when reasoning_effort is explicitly none.
                    request["reasoning_effort"] = "none"
                response = self.client.chat.completions.create(**request)
                content = (
                    response.choices[0].message.content if response.choices else ""
                )
                usage = self._extract_usage(response)
                return (content or "").strip(), usage
            except (
                RateLimitError,
                APIError,
            ) as exc:  # pragma: no cover - requires live API
                if attempt < retry_max - 1:
                    wait_time = (2**attempt) * 1.5
                    time.sleep(wait_time)
                    continue
                raise exc
        return "", None

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            total = usage.get("total_tokens")
        else:
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
            total = getattr(usage, "total_tokens", None)
        if prompt is None and completion is None and total is None:
            return None
        prompt_int = int(prompt or 0)
        completion_int = int(completion or 0)
        total_int = int(total or (prompt_int + completion_int))
        return {
            "prompt_tokens": prompt_int,
            "completion_tokens": completion_int,
            "total_tokens": total_int,
        }

    def _extract_citations(
        self, answer: str, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Parse citations in the model output and align them with retrieved chunks."""
        citations: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for match in _CITATION_PATTERN.finditer(answer):
            document_label = match.group("document").strip()
            chunk_label = match.group("chunk").strip()
            key = (document_label.lower(), chunk_label.lower())
            if key in seen:
                continue
            seen.add(key)

            chunk = self._match_chunk(document_label, chunk_label, chunks)
            citations.append(self._build_citation(chunk, document_label, chunk_label))

        if not citations and chunks:
            # Provide a fallback citation anchored to the highest-scoring chunk.
            top_chunk = chunks[0]
            citations.append(
                self._build_citation(
                    top_chunk,
                    str(top_chunk.get("document_id") or ""),
                    str(
                        top_chunk.get("chunk_index")
                        if top_chunk.get("chunk_index") is not None
                        else ""
                    ),
                )
            )

        return citations

    @staticmethod
    def _match_chunk(
        document_label: str,
        chunk_label: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Locate the retrieved chunk that matches the citation labels."""
        normalized_document = document_label.strip()
        normalized_chunk = chunk_label.strip()

        for chunk in chunks:
            document_id = (
                str(chunk.get("document_id"))
                if chunk.get("document_id") is not None
                else None
            )
            chunk_index = chunk.get("chunk_index")
            chunk_id = (
                str(chunk.get("chunk_id"))
                if chunk.get("chunk_id") is not None
                else None
            )

            if document_id and document_id == normalized_document:
                if chunk_index is not None and str(chunk_index) == normalized_chunk:
                    return chunk
                if chunk_id and chunk_id == normalized_chunk:
                    return chunk

        return None

    @staticmethod
    def _build_citation(
        chunk: dict[str, Any] | None,
        document_label: str,
        chunk_label: str,
    ) -> dict[str, Any]:
        """Create a structured citation payload."""
        chunk_index: int | None = None
        if chunk is not None:
            chunk_index = chunk.get("chunk_index")
        else:
            try:
                chunk_index = int(chunk_label)
            except (ValueError, TypeError):
                chunk_index = None

        return {
            "document_id": (
                chunk.get("document_id")
                if chunk is not None
                else (document_label or None)
            ),
            "chunk_id": chunk.get("chunk_id") if chunk is not None else None,
            "chunk_index": chunk_index,
            "source_type": chunk.get("source_type") if chunk is not None else None,
            "score": chunk.get("score") if chunk is not None else None,
            "snippet": (
                chunk.get("content")[:280]
                if chunk is not None and chunk.get("content")
                else None
            ),
        }

    def _record_cost_events(
        self,
        *,
        attempts: list[dict[str, Any]],
        usage_records: list[dict[str, int] | None],
        query: str,
        project_id: str | None,
        latency_ms: float,
        cache_hit: bool,
    ) -> float:
        if not attempts:
            return 0.0

        total_cost = 0.0
        effective_usage = usage_records or [
            attempt.get("usage") for attempt in attempts
        ]

        for index, attempt in enumerate(attempts):
            usage = (
                effective_usage[index]
                if index < len(effective_usage)
                else attempt.get("usage")
            )
            model_name = attempt.get("model", self.primary_model)
            estimated_cost = MODEL_COST_ESTIMATES.get(model_name, 0.0)

            if self.cost_monitor is not None:
                try:
                    event = self.cost_monitor.track_usage(
                        model=model_name,
                        prompt_tokens=(usage or {}).get("prompt_tokens")
                        if usage
                        else None,
                        completion_tokens=(usage or {}).get("completion_tokens")
                        if usage
                        else None,
                        total_tokens=(usage or {}).get("total_tokens")
                        if usage
                        else None,
                        latency_ms=latency_ms,
                        cache_hit=cache_hit,
                        project_id=project_id,
                        query=query,
                        route="escalation" if index > 0 else "primary",
                        metadata={
                            "quality_score": attempt.get("quality_score"),
                            "citation_count": attempt.get("citation_count"),
                        },
                        estimated_cost=estimated_cost if usage is None else None,
                    )
                    attempt["usage"] = event["usage"]
                    attempt["cost_usd"] = round(event["cost_usd"], 6)
                    total_cost += event["cost_usd"]
                    continue
                except Exception:  # pragma: no cover - diagnostics only
                    logger.debug("Cost monitor logging failed", exc_info=True)

            if usage is not None:
                attempt["usage"] = usage
            fallback_cost = round(estimated_cost or 0.0, 6)
            attempt["cost_usd"] = fallback_cost
            total_cost += fallback_cost

        return total_cost

    def _record_semantic_cache_hit(self, project_id: str | None) -> None:
        """Increment semantic cache metrics when TTL cache satisfies a query."""
        metrics = (
            getattr(self.cache_service, "metrics", None) if self.cache_service else None
        )
        if metrics and hasattr(metrics, "record_hit"):
            try:
                metrics.record_hit(project_id)
            except Exception:  # pragma: no cover - diagnostics only
                logger.debug("Semantic cache metrics update failed", exc_info=True)

    def _record_cache_hit_event(
        self,
        *,
        query: str,
        project_id: str | None,
        latency_ms: float,
    ) -> None:
        if self.cost_monitor is None:
            return
        try:
            self.cost_monitor.record_cache_hit(
                latency_ms=latency_ms,
                project_id=project_id,
                query=query,
            )
        except Exception:  # pragma: no cover - diagnostics only
            logger.debug("Cost monitor cache logging failed", exc_info=True)

    @staticmethod
    def _format_attempt_record(
        *,
        model: str,
        quality: QualityAssessmentResult,
        citation_count: int,
        usage: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "quality_score": quality.composite_score,
            "below_threshold": quality.composite_score < quality.threshold,
            "hard_failures": quality.hard_failures,
            "citation_count": citation_count,
            "usage": usage,
        }


_rag_service: RagService | None = None


def get_rag_service() -> RagService:
    """Return the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service


def current_rag_service() -> RagService | None:
    """Return the existing RAG service instance without creating a new one."""
    return _rag_service
