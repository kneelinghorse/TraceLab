"""Controlled cache proof in a unique, temporary collection; no model calls.

Run on the deployed service with ``python -m scripts.cache_diagnostic``.
Never clears or writes the configured application/cache collections. Output is
limited to fixture identity, check outcomes and bounded process-local counters.
"""

import json
import sys
import uuid

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client
from app.services.cache_metrics import CacheMetrics
from app.services.rag_service import build_empty_scope_result
from app.services.semantic_cache import SemanticCacheService


def run_diagnostic(client) -> dict:
    collection = f"s62-cache-diagnostic-{uuid.uuid4().hex}"
    if collection in {settings.qdrant_collection_name, settings.semantic_cache_collection_name}:
        raise RuntimeError("Diagnostic collection must be isolated")
    cache = SemanticCacheService(client=client, enabled=False)
    cache.collection_name = collection
    cache.enabled = True
    cache.metrics = CacheMetrics()
    created = False
    try:
        # Initialize only after replacing the configured collection with our
        # generated fixture name. No process-wide settings are changed.
        cache._ensure_collection()
        created = True
        vector = [1.0] + [0.0] * (settings.openai_embedding_dimension - 1)
        metadata = {"project_id": "s62-isolated-diagnostic", "max_tokens": 500}
        cache.store_in_cache(vector, build_empty_scope_result(search_mode="semantic"), metadata)
        replay = cache.check_cache(vector, metadata)
        other_scope = cache.check_cache(vector, {**metadata, "project_id": "other-diagnostic-project"})
        count = client.count(collection_name=collection, exact=True).count
        if count != 1 or not replay or not replay["cache"]["hit"] or other_scope is not None or cache.metrics.error_count:
            raise RuntimeError("Isolated cache persistence or scope check failed")
        return {"collection": collection, "points_written": count, "replay_hit": True, "other_scope_missed": True, "configured_collections_untouched": True, "model_calls": 0, "metrics": cache.metrics.snapshot()}
    finally:
        if created:
            # Deletion is restricted to this invocation's generated collection.
            client.delete_collection(collection_name=collection)


if __name__ == "__main__":
    try:
        receipt = run_diagnostic(get_qdrant_client())
    except Exception as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        sys.exit(1)
    print(json.dumps({"passed": True, "fixture_cleaned_up": True, **receipt}))
