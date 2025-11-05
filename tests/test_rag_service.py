"""Tests for the RAG service orchestration and API endpoint."""
import time

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import search as search_router
from app.main import app
from app.core.config import settings
from app.services import rag_service as rag_module
from app.services.cache_metrics import CacheMetrics


class _FakeEmbeddingService:
    def __init__(self):
        self.requests = []

    def generate_embedding(self, text):
        self.requests.append(text)
        return [1.0, 0.0, 0.0]


class _FakeRetrievalService:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs.get("include_embeddings") is True
        return [
            {
                "chunk_id": "chunk-1",
                "content": "Policy frameworks emphasize iterative experimentation and measurement.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.93,
                "embedding": [0.92, 0.2, 0.0],
            },
            {
                "chunk_id": "chunk-2",
                "content": "Programs pair semantic search with lightweight LLM orchestration.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 1,
                "source_type": "report",
                "score": 0.61,
                "embedding": [0.61, 0.8, 0.0],
            },
        ]


class _FakeChatCompletions:
    def __init__(self, content):
        self._content = content
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = type("Message", (), {"content": self._content})
        choice = type("Choice", (), {"message": message})
        return type("Response", (), {"choices": [choice]})


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeChatCompletions(content)


class _FakeOpenAIClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


class _NoOpCacheService:
    def __init__(self):
        self.checked = 0
        self.stored = 0

    def check_cache(self, **_kwargs):
        self.checked += 1
        return None

    def store_in_cache(self, **_kwargs):
        self.stored += 1


class _HitCacheService:
    def __init__(self, cached_response):
        self.cached_response = cached_response
        self.checked = 0

    def check_cache(self, **_kwargs):
        self.checked += 1
        return self.cached_response

    def store_in_cache(self, **_kwargs):  # pragma: no cover - should not be called
        raise AssertionError("Cache store should not be invoked on hit")


class _WorkloadCacheService:
    def __init__(self):
        self.metrics = CacheMetrics()
        self._entries: dict[str, dict] = {}
        self.store_calls = 0

    def check_cache(self, *, metadata, **_kwargs):
        query = metadata.get("query")
        entry = self._entries.get(query)
        if entry is None:
            self.metrics.record_miss(metadata.get("project_id"))
            self.metrics.observe_lookup(0.0001)
            return None

        age_seconds = max(0.0, time.time() - entry["created_at"])
        cached_response = dict(entry["payload"])
        cached_response["cache"] = dict(cached_response["cache"])
        cached_response["cache"].update({"hit": True, "age_seconds": round(age_seconds, 3)})
        self.metrics.record_hit(metadata.get("project_id"))
        self.metrics.observe_lookup(0.0001)
        return cached_response

    def store_in_cache(self, *, metadata, result, **_kwargs):
        self.store_calls += 1
        payload = {
            "answer": result["answer"],
            "citations": result["citations"],
            "sources": result["sources"],
            "compression": result["compression"],
            "cache": {"hit": True, "score": 0.99, "age_seconds": 0.0, "ttl_seconds": None},
        }
        self._entries[metadata.get("query")] = {
            "payload": payload,
            "created_at": time.time(),
        }


def test_rag_service_run_query(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "The repository embraces iterative delivery. [Document: doc-1, Chunk: 0]"
    )

    cache = _NoOpCacheService()
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        retrieval_service=fake_retrieval,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
    )

    result = service.run_query(
        query="How does the repository describe experiment-driven delivery?",
        top_k=5,
        project_id="proj-1",
    )

    assert result["answer"].startswith("The repository embraces iterative delivery")
    assert result["citations"][0]["document_id"] == "doc-1"
    assert result["citations"][0]["chunk_index"] == 0
    assert result["citations"][0]["chunk_id"] == "chunk-1"
    assert result["sources"][0]["chunk_id"] == "chunk-1"
    assert result["compression"]["original_chunks"] == 2
    assert result["compression"]["filtered_chunks"] == 1
    assert result["compression"]["threshold"] == settings.rag_context_threshold
    assert fake_embedding.requests == [
        "How does the repository describe experiment-driven delivery?"
    ]
    assert fake_retrieval.calls[0]["project_id"] == "proj-1"
    assert result["latency_ms"] >= 0.0
    assert result["cache"]["hit"] is False
    assert cache.checked == 1
    assert cache.stored == 1


def test_rag_service_uses_cache_hit(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient("Cache should satisfy this query.")

    cached_payload = {
        "answer": "Cached results already contain the answer. [Document: doc-42, Chunk: 2]",
        "citations": [
            {
                "document_id": "doc-42",
                "chunk_id": "chunk-007",
                "chunk_index": 2,
                "score": 0.98,
            }
        ],
        "sources": [
            {
                "chunk_id": "chunk-007",
                "content": "Markdown ingestion cache entry.",
                "document_id": "doc-42",
                "project_id": "proj-1",
                "chunk_index": 2,
                "score": 0.98,
            }
        ],
        "compression": {
            "original_chunks": 1,
            "filtered_chunks": 1,
            "original_tokens": 120,
            "filtered_tokens": 120,
            "reduction_ratio": 0.0,
            "threshold": settings.rag_context_threshold,
            "compression_ms": 0.1,
        },
        "cache": {"hit": True, "score": 0.98, "age_seconds": 4.2},
    }

    cache = _HitCacheService(cached_payload)
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        retrieval_service=fake_retrieval,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
    )

    result = service.run_query(
        query="What is the cached guidance?",
        top_k=3,
        project_id="proj-1",
    )

    assert result["answer"].startswith("Cached results already contain the answer")
    assert result["cache"]["hit"] is True
    assert fake_retrieval.calls == []
    assert cache.checked == 1


class _FakeRagService:
    def __init__(self):
        self.calls = []

    def run_query(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "answer": "Insights synthesized. [Document: doc-2, Chunk: 3]",
            "citations": [
                {
                    "document_id": "doc-2",
                    "chunk_id": "chunk-99",
                    "chunk_index": 3,
                    "source_type": "brief",
                    "score": 0.87,
                    "snippet": "A concise excerpt of the supporting evidence.",
                }
            ],
            "sources": [
                {
                    "chunk_id": "chunk-99",
                    "content": "Supporting evidence content for the answer.",
                    "document_id": "doc-2",
                    "project_id": "proj-2",
                    "chunk_index": 3,
                    "source_type": "brief",
                    "score": 0.87,
                }
            ],
            "latency_ms": 128.4,
            "compression": {
                "original_chunks": 3,
                "filtered_chunks": 2,
                "original_tokens": 3000,
                "filtered_tokens": 1200,
                "reduction_ratio": 0.6,
                "threshold": 0.7,
                "compression_ms": 12.4,
            },
            "cache": {"hit": False, "score": None, "age_seconds": None, "ttl_seconds": None},
        }


def test_rag_search_endpoint(monkeypatch):
    fake_service = _FakeRagService()
    monkeypatch.setattr(
        search_router, "get_rag_service", lambda: fake_service
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "query": "Summarize the governance approach.",
            "top_k": 4,
            "project_id": "44a8f4ba-13c4-4efc-8705-8c620be4e9dd",
            "temperature": 0.25,
            "max_tokens": 256,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Insights synthesized")
    assert body["citations"][0]["document_id"] == "doc-2"
    assert body["sources"][0]["chunk_id"] == "chunk-99"
    assert fake_service.calls[0]["top_k"] == 4
    assert fake_service.calls[0]["project_id"] == "44a8f4ba-13c4-4efc-8705-8c620be4e9dd"
    assert fake_service.calls[0]["temperature"] == 0.25
    assert fake_service.calls[0]["max_tokens"] == 256
    assert body["cache"]["hit"] is False


def test_semantic_cache_hit_rate_reaches_target(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "Markdown corpus insights. [Document: doc-9, Chunk: 1]"
    )
    workload_cache = _WorkloadCacheService()

    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        retrieval_service=fake_retrieval,
        embedding_service=fake_embedding,
        cache_service=workload_cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
    )

    queries = [
        "Markdown ingestion coverage status?",
        "Cache telemetry thresholds?",
        "Markdown ingestion coverage status?",
        "How to monitor cache evictions?",
        "Semantic cache TTL defaults?",
        "Onboarding metadata alignment?",
        "Semantic cache TTL defaults?",
        "Context compression interplay?",
        "Cache warm start guidance?",
        "Markdown ingestion pipeline QA?",
    ]

    for query in queries:
        service.run_query(query=query, top_k=5, project_id="proj-9")

    hit_rate = workload_cache.metrics.hit_rate()
    assert 0.15 <= hit_rate <= 0.25
    assert len(fake_retrieval.calls) == 8
