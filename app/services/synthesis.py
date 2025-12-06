"""Synthesis service for generating LLM-powered summaries with citations."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.services.cost_monitor import CostMonitor, get_cost_monitor

try:
    from openai import OpenAI
    from openai import APIError, RateLimitError
except ModuleNotFoundError as exc:
    OpenAI = None  # type: ignore
    APIError = RateLimitError = Exception  # type: ignore
    _openai_import_error = exc
else:
    _openai_import_error = None


logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

MAX_CHUNKS_PER_REQUEST = 50
MAX_CONTEXT_CHARS = 100_000  # Approximate ~25k tokens


FORMAT_INSTRUCTIONS = {
    "markdown": (
        "Write a cohesive prose summary that synthesizes the key information from the provided sources. "
        "Organize the content logically by topic rather than by source. Use markdown formatting."
    ),
    "summary": (
        "Write a cohesive prose summary that synthesizes the key information from the provided sources. "
        "Organize the content logically by topic rather than by source."
    ),
    "report": (
        "Write a structured report with clear sections and headings. "
        "Include an executive summary at the start, followed by detailed sections covering the main topics."
    ),
    "bullets": (
        "Create a comprehensive bullet-point list of the key findings and information. "
        "Group related points under topic headings where appropriate."
    ),
}


class SynthesisService:
    """Generate LLM-powered summaries from collections or chunks with citations."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        client: Optional["OpenAI"] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        cost_monitor: Optional[CostMonitor] = None,
    ) -> None:
        if _openai_import_error is not None:
            raise RuntimeError(
                "The OpenAI SDK is required for synthesis. "
                "Install dependencies from requirements.txt."
            ) from _openai_import_error

        if client is None:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY must be set for synthesis.")
            client = OpenAI(api_key=settings.openai_api_key)

        self.client = client
        self.session_factory = session_factory
        self.model = model or settings.openai_chat_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cost_monitor = cost_monitor if cost_monitor is not None else get_cost_monitor()

    def synthesize(
        self,
        *,
        collection_id: Optional[UUID] = None,
        chunk_ids: Optional[List[UUID]] = None,
        prompt: Optional[str] = None,
        output_format: Literal["markdown", "summary", "report", "bullets"] = "markdown",
    ) -> Dict[str, Any]:
        """Generate a synthesis from collection or chunk IDs.

        Args:
            collection_id: UUID of collection to synthesize (mutually exclusive with chunk_ids)
            chunk_ids: List of chunk UUIDs to synthesize (mutually exclusive with collection_id)
            prompt: Custom instruction (default: format-specific instruction)
            output_format: Output format - summary, report, or bullets

        Returns:
            Dict with content, citations, tokens_used, truncated, chunk_count
        """
        start_time = time.perf_counter()

        # Fetch chunks
        if collection_id is not None:
            chunks, truncated = self._fetch_collection_chunks(collection_id)
        elif chunk_ids:
            chunks, truncated = self._fetch_chunks_by_ids(chunk_ids)
        else:
            raise ValueError("Either collection_id or chunk_ids must be provided.")

        if not chunks:
            return {
                "content": "No content available for synthesis. The collection or chunks are empty.",
                "citations": [],
                "tokens_used": 0,
                "truncated": False,
                "chunk_count": 0,
            }

        # Build context with source markers
        context_text, citation_map, was_truncated = self._build_context(chunks)
        truncated = truncated or was_truncated

        # Generate synthesis
        messages = self._build_messages(
            context=context_text,
            prompt=prompt,
            output_format=output_format,
        )
        content, usage = self._generate_completion(messages)

        # Post-process to map citations
        final_content, used_citations = self._process_citations(content, citation_map)

        # Track cost
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._track_cost(usage=usage, latency_ms=latency_ms)

        return {
            "content": final_content,
            "citations": used_citations,
            "tokens_used": (usage or {}).get("total_tokens", 0),
            "truncated": truncated,
            "chunk_count": len(chunks),
        }

    def _fetch_collection_chunks(
        self, collection_id: UUID
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch all chunks from a collection."""
        session = self.session_factory()
        try:
            # Verify collection exists
            collection = (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .one_or_none()
            )
            if collection is None:
                raise ValueError(f"Collection {collection_id} not found.")

            # Get items with chunks
            items = (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .order_by(CollectionItem.added_at.asc())
                .all()
            )

            truncated = len(items) > MAX_CHUNKS_PER_REQUEST
            items = items[:MAX_CHUNKS_PER_REQUEST]

            # Gather document info
            doc_ids = set()
            for item in items:
                if item.chunk and item.chunk.document_id:
                    doc_ids.add(str(item.chunk.document_id))

            documents: Dict[str, Document] = {}
            if doc_ids:
                docs = session.query(Document).filter(Document.id.in_(doc_ids)).all()
                documents = {str(d.id): d for d in docs}

            # Build chunk data
            chunks = []
            for item in items:
                if item.chunk:
                    doc = documents.get(str(item.chunk.document_id))
                    chunks.append({
                        "chunk_id": str(item.chunk.id),
                        "document_id": str(item.chunk.document_id),
                        "document_name": doc.name if doc else None,
                        "chunk_index": item.chunk.chunk_index,
                        "content": item.chunk.content or "",
                    })

            return chunks, truncated
        finally:
            session.close()

    def _fetch_chunks_by_ids(
        self, chunk_ids: List[UUID]
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch specific chunks by their IDs."""
        session = self.session_factory()
        try:
            truncated = len(chunk_ids) > MAX_CHUNKS_PER_REQUEST
            chunk_ids_to_fetch = chunk_ids[:MAX_CHUNKS_PER_REQUEST]

            # Fetch chunks
            db_chunks = (
                session.query(DocumentChunk)
                .filter(DocumentChunk.id.in_([str(cid) for cid in chunk_ids_to_fetch]))
                .all()
            )

            if not db_chunks:
                return [], False

            # Gather document info
            doc_ids = {str(c.document_id) for c in db_chunks if c.document_id}
            documents: Dict[str, Document] = {}
            if doc_ids:
                docs = session.query(Document).filter(Document.id.in_(doc_ids)).all()
                documents = {str(d.id): d for d in docs}

            # Build chunk data
            chunks = []
            for chunk in db_chunks:
                doc = documents.get(str(chunk.document_id))
                chunks.append({
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "document_name": doc.name if doc else None,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content or "",
                })

            return chunks, truncated
        finally:
            session.close()

    def _build_context(
        self, chunks: List[Dict[str, Any]]
    ) -> Tuple[str, Dict[int, Dict[str, Any]], bool]:
        """Build context string with source markers and truncation handling.

        Returns:
            Tuple of (context_text, citation_map, was_truncated)
        """
        context_parts = []
        citation_map: Dict[int, Dict[str, Any]] = {}
        total_chars = 0
        truncated = False

        for idx, chunk in enumerate(chunks, start=1):
            marker = f"[{idx}]"
            content = chunk.get("content", "").strip()

            # Check if adding this chunk would exceed limit
            chunk_text = f"{marker}\n{content}\n"
            if total_chars + len(chunk_text) > MAX_CONTEXT_CHARS:
                truncated = True
                break

            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

            # Store citation info
            citation_map[idx] = {
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk.get("document_id"),
                "excerpt": content[:100] if content else "",
            }

        return "\n".join(context_parts), citation_map, truncated

    def _build_messages(
        self,
        *,
        context: str,
        prompt: Optional[str],
        output_format: Literal["summary", "report", "bullets"],
    ) -> List[Dict[str, str]]:
        """Build chat messages for the LLM."""
        format_instruction = FORMAT_INSTRUCTIONS.get(output_format, FORMAT_INSTRUCTIONS["summary"])
        user_instruction = prompt or "Summarize the following documents."

        system_prompt = (
            "You are a research assistant that synthesizes information from multiple sources. "
            "Your task is to create a cohesive synthesis that accurately represents the source material. "
            f"{format_instruction}\n\n"
            "IMPORTANT: Cite sources using the numbered markers (e.g., [1], [2]) that appear before each source. "
            "Every significant claim or piece of information should have a citation. "
            "Place citations immediately after the relevant statement. "
            "You may combine multiple citations like [1][3] when information comes from multiple sources."
        )

        user_prompt = (
            f"**Task:** {user_instruction}\n\n"
            f"**Sources:**\n\n{context}\n\n"
            "Please synthesize the above sources, citing them appropriately using [1], [2], etc."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _generate_completion(
        self, messages: List[Dict[str, str]]
    ) -> Tuple[str, Optional[Dict[str, int]]]:
        """Call OpenAI API and return content with usage stats."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content if response.choices else ""
            usage = self._extract_usage(response)
            return (content or "").strip(), usage
        except (RateLimitError, APIError) as exc:
            logger.error("OpenAI API error during synthesis: %s", exc)
            raise

    @staticmethod
    def _extract_usage(response: Any) -> Optional[Dict[str, int]]:
        """Extract token usage from API response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None

        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens", 0)
            completion = usage.get("completion_tokens", 0)
            total = usage.get("total_tokens", prompt + completion)
        else:
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            completion = getattr(usage, "completion_tokens", 0) or 0
            total = getattr(usage, "total_tokens", prompt + completion) or (prompt + completion)

        return {
            "prompt_tokens": int(prompt),
            "completion_tokens": int(completion),
            "total_tokens": int(total),
        }

    def _process_citations(
        self,
        content: str,
        citation_map: Dict[int, Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Extract used citations and build citation list.

        Returns:
            Tuple of (content, list of citation dicts)
        """
        import re

        # Find all citation markers used in content
        used_markers = set(int(m) for m in re.findall(r"\[(\d+)\]", content))

        # Build citation list for used markers only
        citations = []
        for marker in sorted(used_markers):
            if marker in citation_map:
                info = citation_map[marker]
                citations.append({
                    "chunk_id": info["chunk_id"],
                    "document_id": info.get("document_id"),
                    "excerpt": info.get("excerpt", ""),
                })

        return content, citations

    def _track_cost(
        self,
        *,
        usage: Optional[Dict[str, int]],
        latency_ms: float,
    ) -> None:
        """Track token usage for cost monitoring."""
        if self.cost_monitor is None or usage is None:
            return

        try:
            self.cost_monitor.track_usage(
                model=self.model,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                latency_ms=latency_ms,
                cache_hit=False,
                route="synthesis",
                metadata={"endpoint": "/api/v1/synthesize"},
            )
        except Exception:
            logger.debug("Cost tracking failed", exc_info=True)


_synthesis_service: Optional[SynthesisService] = None


def get_synthesis_service() -> SynthesisService:
    """Return the singleton synthesis service instance."""
    global _synthesis_service
    if _synthesis_service is None:
        _synthesis_service = SynthesisService()
    return _synthesis_service
