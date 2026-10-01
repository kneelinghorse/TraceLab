"""Optional persistence proof on a fixture-owned Qdrant container."""

import pytest

from app.core.config import settings
from app.services.rag_service import build_empty_scope_result
from app.services.semantic_cache import SemanticCacheService


@pytest.mark.integration
def test_disposable_qdrant_cache_round_trip(disposable_qdrant):
    cache = SemanticCacheService(client=disposable_qdrant, enabled=True)
    vector = [1.0] + [0.0] * (settings.openai_embedding_dimension - 1)
    metadata = {"project_id": "isolated-project", "max_tokens": 500}
    cache.store_in_cache(
        vector, build_empty_scope_result(search_mode="semantic"), metadata
    )
    assert disposable_qdrant.count(cache.collection_name).count == 1
    assert cache.check_cache(vector, metadata)["cache"]["hit"]
    assert cache.check_cache(vector, {"project_id": "other-project"}) is None
