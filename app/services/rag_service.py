"""RAG service that orchestrates retrieval, compression, and answer generation."""
import re
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.context_compression import compress_context
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.retrieval_service import RetrievalService, get_retrieval_service
from app.services.semantic_cache import SemanticCacheService, get_semantic_cache_service

try:  # pragma: no cover - allow import without OpenAI SDK in some environments
    from openai import OpenAI
    from openai import APIError, RateLimitError
except ModuleNotFoundError as exc:  # pragma: no cover
    OpenAI = None  # type: ignore
    APIError = RateLimitError = Exception  # type: ignore
    _openai_import_error = exc
else:
    _openai_import_error = None


_CITATION_PATTERN = re.compile(
    r"\[Document:\s*(?P<document>[^\],]+),\s*Chunk:\s*(?P<chunk>[^\]]+)\]",
    re.IGNORECASE,
)


class RagService:
    """Compose semantic retrieval with GPT answer generation."""

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        cache_service: Optional[SemanticCacheService] = None,
        client: Optional[OpenAI] = None,  # type: ignore[name-defined]
        model: Optional[str] = None,
        default_temperature: Optional[float] = None,
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
        self.embedding_service = embedding_service or get_embedding_service()
        self.cache_service = (
            cache_service
            if cache_service is not None
            else (get_semantic_cache_service() if settings.semantic_cache_enabled else None)
        )
        self.model = model or settings.openai_chat_model
        self.default_temperature = (
            default_temperature if default_temperature is not None else settings.openai_chat_temperature
        )
        self.default_max_tokens = settings.rag_default_max_tokens
        self.compression_threshold = settings.rag_context_threshold

    def run_query(
        self,
        query: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        hnsw_ef: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full RAG workflow: retrieve context and synthesize an answer.
        """
        start = time.perf_counter()
        query_embedding = self.embedding_service.generate_embedding(query)
        cache_metadata = {
            "query": query,
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "top_k": top_k,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
        }

        if self.cache_service is not None:
            cached_result = self.cache_service.check_cache(
                query_embedding=query_embedding,
                metadata=cache_metadata,
            )
            if cached_result:
                response = dict(cached_result)
                response["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
                cache_info = response.get("cache") or {}
                cache_info["hit"] = True
                response["cache"] = cache_info
                return response

        retrieved_chunks = self.retrieval_service.search(
            query=query,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            hnsw_ef=hnsw_ef,
            query_embedding=query_embedding,
            include_embeddings=True,
        )

        compressed_chunks, compression_metrics = compress_context(
            chunks=retrieved_chunks,
            query_embedding=query_embedding,
            threshold=self.compression_threshold,
        )

        messages = self._build_messages(query=query, chunks=compressed_chunks)
        answer = self._generate_answer(
            messages=messages,
            temperature=temperature if temperature is not None else self.default_temperature,
            max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
        )

        citations = self._extract_citations(answer, compressed_chunks)
        latency_ms = (time.perf_counter() - start) * 1000

        result = {
            "answer": answer,
            "citations": citations,
            "sources": compressed_chunks,
            "latency_ms": round(latency_ms, 2),
            "compression": compression_metrics,
            "cache": {"hit": False},
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

        return result

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

    def _generate_answer(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        retry_max: int = 3,
    ) -> str:
        """Call the OpenAI chat completion API with simple exponential backoff."""
        for attempt in range(retry_max):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content if response.choices else ""
                return (content or "").strip()
            except (RateLimitError, APIError) as exc:  # pragma: no cover - requires live API
                if attempt < retry_max - 1:
                    wait_time = (2 ** attempt) * 1.5
                    time.sleep(wait_time)
                    continue
                raise exc
        return ""

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


_rag_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    """Return the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service
