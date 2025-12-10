"""Qdrant client singleton with connection pre-warming.

This module provides a centralized, pre-warmed Qdrant client to eliminate
the 60+ second cold-start penalty on first query. The client is initialized
once at application startup and shared across all services.

Usage:
    from app.core.qdrant_client import get_qdrant_client, prewarm_qdrant

    # In FastAPI startup event:
    await prewarm_qdrant()

    # In services:
    client = get_qdrant_client()
"""
import logging
from typing import Optional

from app.core.config import settings

try:  # pragma: no cover - defensive import for environments without Qdrant SDK
    from qdrant_client import QdrantClient
except ModuleNotFoundError as exc:  # pragma: no cover
    QdrantClient = None  # type: ignore
    _qdrant_import_error = exc
else:
    _qdrant_import_error = None

logger = logging.getLogger(__name__)

# Singleton client instance
_client: Optional[QdrantClient] = None

# Pre-warm status
_is_prewarmed: bool = False


def get_qdrant_client() -> QdrantClient:
    """Get or create the singleton Qdrant client instance.

    Returns:
        The shared QdrantClient instance configured from settings.

    Raises:
        RuntimeError: If qdrant-client package is not installed.
        ValueError: If QDRANT_URL is not configured.
    """
    global _client

    if _qdrant_import_error is not None:
        raise RuntimeError(
            "The qdrant-client package is required for vector storage interactions. "
            "Install dependencies from requirements.txt."
        ) from _qdrant_import_error

    if _client is None:
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL must be configured before using Qdrant client")

        # Validate HTTPS when API key is set
        if settings.qdrant_api_key and settings.qdrant_url.startswith("http://"):
            raise ValueError(
                "QDRANT_URL must use HTTPS when QDRANT_API_KEY is set. "
                "See docs/qdrant-railway-setup.md for configuration guidance."
            )

        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
            prefer_grpc=settings.qdrant_prefer_grpc,
            timeout=settings.qdrant_timeout_seconds,
        )
        logger.info(
            "Qdrant client initialized",
            extra={"url": settings.qdrant_url, "prefer_grpc": settings.qdrant_prefer_grpc}
        )

    return _client


async def prewarm_qdrant() -> bool:
    """Pre-warm Qdrant connection by running a dummy query.

    This should be called during FastAPI startup to eliminate the 60+ second
    cold-start penalty on the first real query. The function:
    1. Initializes the client connection pool
    2. Runs a dummy search to warm the connection
    3. Verifies Qdrant is responding before accepting requests

    Returns:
        True if pre-warm succeeded, False if it failed.
    """
    global _is_prewarmed

    try:
        client = get_qdrant_client()

        # First, verify we can connect by listing collections
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]
        logger.info(
            "Qdrant connection verified",
            extra={"collections_count": len(collection_names)}
        )

        # Run a dummy search to fully warm the connection
        # Only if the main collection exists
        if settings.qdrant_collection_name in collection_names:
            # Use a zero vector to avoid actual results - just warming the path
            dummy_vector = [0.0] * settings.openai_embedding_dimension
            client.search(
                collection_name=settings.qdrant_collection_name,
                query_vector=dummy_vector,
                limit=1
            )
            logger.info("Qdrant search path pre-warmed")
        else:
            logger.warning(
                f"Collection '{settings.qdrant_collection_name}' not found - "
                "skipping search pre-warm (collection may not exist yet)"
            )

        _is_prewarmed = True
        return True

    except Exception as e:
        logger.error(f"Qdrant pre-warm failed: {e}")
        _is_prewarmed = False
        return False


def is_qdrant_ready() -> bool:
    """Check if Qdrant has been pre-warmed and is ready for queries.

    Returns:
        True if prewarm_qdrant() succeeded, False otherwise.
    """
    return _is_prewarmed


def get_qdrant_health() -> dict:
    """Get detailed Qdrant health status.

    Returns:
        Dict with status, collections count, and any error message.
    """
    try:
        client = get_qdrant_client()
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        return {
            "status": "healthy",
            "prewarmed": _is_prewarmed,
            "collections_count": len(collection_names),
            "collections": collection_names,
            "url": settings.qdrant_url,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "prewarmed": _is_prewarmed,
            "error": str(e),
            "url": settings.qdrant_url,
        }


def reset_client() -> None:
    """Reset the singleton client (useful for testing).

    WARNING: This should only be used in tests, not in production code.
    """
    global _client, _is_prewarmed
    _client = None
    _is_prewarmed = False
