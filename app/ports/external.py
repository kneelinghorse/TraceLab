# ABOUTME: Protocol interfaces for external service boundaries.
# ABOUTME: Defines contracts for embedding, vector DB, LLM, and search services.

from __future__ import annotations

from typing import Any, Protocol


class EmbeddingPort(Protocol):
    """Generate vector embeddings from text."""

    def generate_embedding(self, text: str) -> list[float]: ...

    def generate_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]: ...


class VectorDBPort(Protocol):
    """Upsert, search, and delete vectors in a vector store."""

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> None: ...

    def search_chunks(
        self,
        query_vector: list[float],
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def delete_chunks(
        self,
        document_id: str,
    ) -> None:
        """Remove all chunks for a document. Not yet implemented in QdrantService."""
        ...


class LLMPort(Protocol):
    """Text generation via a large language model."""

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str: ...


class SearchPort(Protocol):
    """Hybrid search combining vector and keyword retrieval."""

    def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...
