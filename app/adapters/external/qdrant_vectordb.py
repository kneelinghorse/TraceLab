# ABOUTME: Adapter bridging QdrantService to the VectorDBPort protocol.
# ABOUTME: Wraps the existing Qdrant client service with a clean interface.

from __future__ import annotations

from typing import Any

from app.services.qdrant_service import QdrantService


class QdrantVectorDBAdapter:
    """Adapter bridging QdrantService to VectorDBPort protocol."""

    def __init__(self, service: QdrantService):
        self._service = service

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> None:
        self._service.upsert_chunks(chunks, batch_size=batch_size)

    def search_chunks(
        self,
        query_vector: list[float],
        top_k: int = 5,
        project_id: str | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._service.search_chunks(
            query_vector,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
        )

    def delete_chunks(self, document_id: str) -> None:
        raise NotImplementedError("QdrantService does not yet support delete_chunks_for_document")
