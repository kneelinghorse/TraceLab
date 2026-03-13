# ABOUTME: Adapter bridging EmbeddingService to the EmbeddingPort protocol.
# ABOUTME: Wraps the existing OpenAI-based embedding service with a clean interface.

from __future__ import annotations

from app.services.embedding_service import EmbeddingService


class OpenAIEmbeddingAdapter:
    """Adapter bridging EmbeddingService to EmbeddingPort protocol."""

    def __init__(self, service: EmbeddingService):
        self._service = service

    def generate_embedding(self, text: str) -> list[float]:
        return self._service.generate_embedding(text)

    def generate_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        return self._service.generate_embeddings_batch(texts, batch_size=batch_size)
