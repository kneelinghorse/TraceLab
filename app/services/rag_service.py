"""RAG service that orchestrates retrieval, compression, and answer generation."""
import logging
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.cache_manager import get_cache_manager
from app.services.context_compression import compress_context
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.cost_monitor import CostMonitor, get_cost_monitor
from app.services.faceted_search import FacetFilters
from app.services.hybrid_search import HybridSearchService
from app.services.retrieval_service import RetrievalService, get_retrieval_service
from app.services.semantic_cache import SemanticCacheService, get_semantic_cache_service
from app.services.quality_assessment import (
    QualityAssessor,
    QualityAssessmentConfig,
    QualityAssessmentResult,
)

try:  # pragma: no cover - allow import without OpenAI SDK in some environments
    from openai import OpenAI
    from openai import APIError, RateLimitError
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
    "gpt-4o-mini": 0.00018,
    "gpt-4o": 0.00075,
}


class RagService:
    """Compose semantic retrieval with GPT answer generation."""

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        hybrid_search_service: Optional[HybridSearchService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        cache_service: Optional[SemanticCacheService] = None,
        client: Optional[OpenAI] = None,  # type: ignore[name-defined]
        model: Optional[str] = None,
        escalation_model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        quality_assessor: Optional[QualityAssessor] = None,
        cost_monitor: Optional[CostMonitor] | object = _UNSET,
    ) -> None:
        if _openai_import_error is not None:
            raise RuntimeError(
                "The OpenAI SDK is required for RAG answer generation. "
                "Install dependencies from requirements.txt."
            ) from _openai_import_error

        if client is None:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY must be set for RAG answer generation.")
            client = OpenAI(api_key=settings.openai_api_key)

        self.client = client
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.hybrid_search_service = hybrid_search_service or HybridSearchService(
            retrieval_service=self.retrieval_service
        )
        self.embedding_service = embedding_service or get_embedding_service()
        self.cache_service = (
            cache_service
            if cache_service is not None
            else (get_semantic_cache_service() if settings.semantic_cache_enabled else None)
        )
        self.primary_model = model or settings.openai_chat_model
        self.model = self.primary_model  # maintain backwards compatibility for callers accessing .model
        self.escalation_model = escalation_model or getattr(settings, "openai_escalation_model", "gpt-4o")
        self.default_temperature = (
            default_temperature if default_temperature is not None else settings.openai_chat_temperature
        )
        self.default_max_tokens = settings.rag_default_max_tokens
        self.compression_threshold = settings.rag_context_threshold
        if quality_assessor is None:
            quality_config = QualityAssessmentConfig(
                escalation_threshold=getattr(settings, "tiered_routing_threshold", 0.85),
                linguistic_weight=getattr(settings, "tiered_weight_linguistic", 0.35),
                integrity_weight=getattr(settings, "tiered_weight_integrity", 0.35),
                provenance_weight=getattr(settings, "tiered_weight_provenance", 0.30),
            )
            quality_assessor = QualityAssessor(quality_config)
        self.quality_assessor = quality_assessor
        self.routing_metrics = {"total_queries": 0, "escalations": 0}
        self.cost_monitor = get_cost_monitor() if cost_monitor is _UNSET else cost_monitor
        self.cache_manager = get_cache_manager()

    def run_query(
        self,
        query: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        search_mode: str = "semantic",
        min_quality_gates: Optional[int] = None,
        status_filters: Optional[List[str]] = None,
        allow_pii: Optional[bool] = True,
    ) -> Dict[str, Any]:
        """
        Execute a full RAG workflow: retrieve context and synthesize an answer.
        """
        normalized_mode = (search_mode or "semantic").strip().lower()
        filters = FacetFilters.from_kwargs(
            project_id=project_id,
            document_types=document_types,
            source_types=source_types,
            source_type=source_type,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
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
            filters_signature=filters.signature(),
            quality_signature=self._quality_filter_signature(
                min_quality_gates=min_quality_gates,
                statuses=status_filters,
                allow_pii=allow_pii,
            ),
        )
        start = time.perf_counter()

        def _loader() -> Dict[str, Any]:
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
            )

        result, hit = self.cache_manager.cached_value("rag_query_results", cache_key, _loader)
        cache_info = result.setdefault("cache", {})
        cache_info.setdefault("layer", "ttl")
        cache_info["ttl_seconds"] = self.cache_manager.ttl_seconds("rag_query_results")
        result.setdefault("search_mode", normalized_mode)

        if hit:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            cache_info["hit"] = True
            cache_info["source"] = "application_ttl"
            result["latency_ms"] = latency_ms
            self._record_cache_hit_event(query=query, project_id=project_id, latency_ms=latency_ms)
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
        project_id: Optional[str],
        document_id: Optional[str],
        source_type: Optional[str],
        document_types: Optional[List[str]],
        source_types: Optional[List[str]],
        date_from: Optional[date],
        date_to: Optional[date],
        tags: Optional[List[str]],
        hnsw_ef: Optional[int],
        temperature: Optional[float],
        max_tokens: Optional[int],
        search_mode: str,
        min_quality_gates: Optional[int],
        status_filters: Optional[List[str]],
        allow_pii: Optional[bool],
    ) -> Dict[str, Any]:
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
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
            "search_mode": normalized_mode,
            "filters_signature": FacetFilters.from_kwargs(
                project_id=project_id,
                document_types=document_types,
                source_types=source_types,
                source_type=source_type,
                tags=tags,
                date_from=date_from,
                date_to=date_to,
            ).signature(),
            "min_quality_gates": min_quality_gates,
            "status_filters": list(status_filters or []),
            "allow_pii": allow_pii if allow_pii is not None else True,
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

        retrieved_chunks = self.hybrid_search_service.search(
            query=query,
            top_k=top_k,
            search_mode=normalized_mode,
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
            include_embeddings=True,
            min_quality_gates=min_quality_gates,
            status_filters=status_filters,
            allow_pii=allow_pii,
        )

        compressed_chunks, compression_metrics = compress_context(
            chunks=retrieved_chunks,
            query_embedding=query_embedding,
            threshold=self.compression_threshold,
        )

        messages = self._build_messages(query=query, chunks=compressed_chunks)
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
            temperature=temperature if temperature is not None else self.default_temperature,
            max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
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
                pass

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
    def _quality_filter_signature(
        *,
        min_quality_gates: Optional[int],
        statuses: Optional[List[str]],
        allow_pii: Optional[bool],
    ) -> str:
        """Generate a cache-friendly signature for governance filters."""
        if min_quality_gates is None:
            gates_token = "*"
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
            status_token = "*"

        pii_token = "no_pii" if allow_pii is False else "any"
        return "|".join([gates_token, status_token, pii_token])

    def _build_messages(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
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

    def _generate_with_tiered_routing(
        self,
        *,
        query: str,
        messages: List[Dict[str, str]],
        chunks: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, List[Dict[str, Any]], Dict[str, Any], Dict[str, Any], List[Optional[Dict[str, int]]]]:
        """Generate an answer using tiered routing and quality assessment."""
        attempts: List[Dict[str, Any]] = []
        attempt_usages: List[Optional[Dict[str, int]]] = []

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

        cost_estimate = sum(MODEL_COST_ESTIMATES.get(attempt["model"], 0.0) for attempt in attempts)
        quality_report: Dict[str, Any] = {
            "composite_score": final_quality.composite_score,
            "threshold": final_quality.threshold,
            "pillar_scores": final_quality.pillar_scores,
            "hard_failures": final_quality.hard_failures,
            "reasons": final_quality.reasons,
        }
        if escalated:
            quality_report["pre_escalation_score"] = primary_quality.composite_score

        routing_details = {
            "selected_model": self.escalation_model if escalated else self.primary_model,
            "escalated": escalated,
            "attempts": attempts,
            "estimated_cost_usd": round(cost_estimate, 6),
            "metrics": dict(self.routing_metrics),
        }

        return final_answer, final_citations, quality_report, routing_details, attempt_usages

    def _generate_answer(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        retry_max: int = 3,
        model: Optional[str] = None,
    ) -> tuple[str, Optional[Dict[str, int]]]:
        """Call the OpenAI chat completion API with simple exponential backoff."""
        for attempt in range(retry_max):
            try:
                response = self.client.chat.completions.create(
                    model=model if model is not None else self.primary_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content if response.choices else ""
                usage = self._extract_usage(response)
                return (content or "").strip(), usage
            except (RateLimitError, APIError) as exc:  # pragma: no cover - requires live API
                if attempt < retry_max - 1:
                    wait_time = (2 ** attempt) * 1.5
                    time.sleep(wait_time)
                    continue
                raise exc
        return "", None

    @staticmethod
    def _extract_usage(response: Any) -> Optional[Dict[str, int]]:
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

    def _extract_citations(self, answer: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse citations in the model output and align them with retrieved chunks."""
        citations: List[Dict[str, Any]] = []
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
                    str(top_chunk.get("chunk_index") if top_chunk.get("chunk_index") is not None else ""),
                )
            )

        return citations

    @staticmethod
    def _match_chunk(
        document_label: str,
        chunk_label: str,
        chunks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Locate the retrieved chunk that matches the citation labels."""
        normalized_document = document_label.strip()
        normalized_chunk = chunk_label.strip()

        for chunk in chunks:
            document_id = str(chunk.get("document_id")) if chunk.get("document_id") is not None else None
            chunk_index = chunk.get("chunk_index")
            chunk_id = str(chunk.get("chunk_id")) if chunk.get("chunk_id") is not None else None

            if document_id and document_id == normalized_document:
                if chunk_index is not None and str(chunk_index) == normalized_chunk:
                    return chunk
                if chunk_id and chunk_id == normalized_chunk:
                    return chunk

        return None

    @staticmethod
    def _build_citation(
        chunk: Optional[Dict[str, Any]],
        document_label: str,
        chunk_label: str,
    ) -> Dict[str, Any]:
        """Create a structured citation payload."""
        chunk_index: Optional[int] = None
        if chunk is not None:
            chunk_index = chunk.get("chunk_index")
        else:
            try:
                chunk_index = int(chunk_label)
            except (ValueError, TypeError):
                chunk_index = None

        return {
            "document_id": (chunk.get("document_id") if chunk is not None else (document_label or None)),
            "chunk_id": chunk.get("chunk_id") if chunk is not None else None,
            "chunk_index": chunk_index,
            "source_type": chunk.get("source_type") if chunk is not None else None,
            "score": chunk.get("score") if chunk is not None else None,
            "snippet": (chunk.get("content")[:280] if chunk is not None and chunk.get("content") else None),
        }

    def _record_cost_events(
        self,
        *,
        attempts: List[Dict[str, Any]],
        usage_records: List[Optional[Dict[str, int]]],
        query: str,
        project_id: Optional[str],
        latency_ms: float,
        cache_hit: bool,
    ) -> float:
        if not attempts:
            return 0.0

        total_cost = 0.0
        effective_usage = usage_records or [attempt.get("usage") for attempt in attempts]

        for index, attempt in enumerate(attempts):
            usage = effective_usage[index] if index < len(effective_usage) else attempt.get("usage")
            model_name = attempt.get("model", self.primary_model)
            estimated_cost = MODEL_COST_ESTIMATES.get(model_name, 0.0)

            if self.cost_monitor is not None:
                try:
                    event = self.cost_monitor.track_usage(
                        model=model_name,
                        prompt_tokens=(usage or {}).get("prompt_tokens") if usage else None,
                        completion_tokens=(usage or {}).get("completion_tokens") if usage else None,
                        total_tokens=(usage or {}).get("total_tokens") if usage else None,
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

    def _record_semantic_cache_hit(self, project_id: Optional[str]) -> None:
        """Increment semantic cache metrics when TTL cache satisfies a query."""
        metrics = getattr(self.cache_service, "metrics", None) if self.cache_service else None
        if metrics and hasattr(metrics, "record_hit"):
            try:
                metrics.record_hit(project_id)
            except Exception:  # pragma: no cover - diagnostics only
                logger.debug("Semantic cache metrics update failed", exc_info=True)

    def _record_cache_hit_event(
        self,
        *,
        query: str,
        project_id: Optional[str],
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
        usage: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        return {
            "model": model,
            "quality_score": quality.composite_score,
            "below_threshold": quality.composite_score < quality.threshold,
            "hard_failures": quality.hard_failures,
            "citation_count": citation_count,
            "usage": usage,
        }


_rag_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    """Return the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service


def current_rag_service() -> Optional[RagService]:
    """Return the existing RAG service instance without creating a new one."""
    return _rag_service
