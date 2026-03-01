"""Tests for the RAG service orchestration and API endpoint."""
import copy
import time
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import search as search_router
from app.main import app
from app.core.config import settings
from app.services import rag_service as rag_module
from app.services.cache_metrics import CacheMetrics
from app.services.pedr.search_orchestrator import (
    PEDRSearchResponse,
    PEDRSearchResult,
    PEDRMetadata,
    LayerTimings,
)


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


class _FakePEDROrchestrator:
    """Fake PEDR orchestrator that returns PEDRSearchResponse objects."""

    def __init__(self, results: Optional[List[Dict[str, Any]]] = None):
        self.calls: List[Dict[str, Any]] = []
        default_results = results or [
            {
                "chunk_id": "chunk-1",
                "content": "Policy frameworks emphasize iterative experimentation and measurement.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "rrf_score": 0.93,
                "embedding": [0.92, 0.2, 0.0],
            },
            {
                "chunk_id": "chunk-2",
                "content": "Programs pair semantic search with lightweight LLM orchestration.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 1,
                "source_type": "report",
                "rrf_score": 0.61,
                "embedding": [0.61, 0.8, 0.0],
            },
        ]
        self._results = default_results

    def search(self, **kwargs) -> PEDRSearchResponse:
        self.calls.append(kwargs)
        # Build PEDRSearchResult objects from our test data
        results = [
            PEDRSearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                document_id=r.get("document_id"),
                project_id=r.get("project_id"),
                chunk_index=r.get("chunk_index"),
                source_type=r.get("source_type"),
                rrf_score=r.get("rrf_score", r.get("score", 0.0)),
                embedding=r.get("embedding"),
            )
            for r in self._results
        ]
        metadata = PEDRMetadata(
            query=kwargs.get("query", ""),
            intent="factual",
            intent_confidence=0.9,
            detected_type=None,
            type_confidence=0.0,
            layers_used=["lexical", "semantic"],
            layer_weights={"lexical": 0.25, "semantic": 0.35},
            timings=LayerTimings(total_ms=50.0),
            total_candidates=len(results),
            result_count=len(results),
            cache_hit=False,
        )
        return PEDRSearchResponse(results=results, metadata=metadata)


class _FakeChatCompletions:
    def __init__(self, content):
        self._content = content
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = type("Message", (), {"content": self._content})
        choice = type("Choice", (), {"message": message})
        usage = type(
            "Usage",
            (),
            {"prompt_tokens": 120, "completion_tokens": 64, "total_tokens": 184},
        )
        return type("Response", (), {"choices": [choice], "usage": usage})


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeChatCompletions(content)


class _FakeOpenAIClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


class _TieredFakeChatCompletions:
    def __init__(self, responses):
        self._responses = responses
        self.requests = []

    def create(self, **kwargs):
        model = kwargs.get("model")
        content = self._responses.get(model, "")
        self.requests.append({"model": model})
        message = type("Message", (), {"content": content})
        choice = type("Choice", (), {"message": message})
        usage = type(
            "Usage",
            (),
            {
                "prompt_tokens": 100 if model == settings.openai_chat_model else 140,
                "completion_tokens": 60 if model == settings.openai_chat_model else 90,
                "total_tokens": 0,
            },
        )
        return type("Response", (), {"choices": [choice], "usage": usage})


class _TieredFakeChat:
    def __init__(self, responses):
        self.completions = _TieredFakeChatCompletions(responses)


class _TieredFakeOpenAIClient:
    def __init__(self, responses):
        self.chat = _TieredFakeChat(responses)


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
            "quality": copy.deepcopy(result["quality"]),
            "routing": copy.deepcopy(result["routing"]),
        }
        self._entries[metadata.get("query")] = {
            "payload": payload,
            "created_at": time.time(),
        }


class _FakeCostMonitor:
    def __init__(self, cost: float = 0.001):
        self.cost = cost
        self.usage_events = []
        self.cache_hits = []

    def track_usage(self, **kwargs):
        prompt = kwargs.get("prompt_tokens") or 0
        completion = kwargs.get("completion_tokens") or 0
        usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": kwargs.get("total_tokens") or (prompt + completion),
        }
        event = {
            "model": kwargs.get("model"),
            "route": kwargs.get("route"),
            "project_id": kwargs.get("project_id"),
        }
        self.usage_events.append(event)
        return {"usage": usage, "cost_usd": self.cost, "event": event}

    def record_cache_hit(self, **kwargs):
        self.cache_hits.append(kwargs)


def test_rag_service_run_query(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "The repository embraces iterative delivery. [Document: doc-1, Chunk: 0]"
    )

    cache = _NoOpCacheService()
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=None,
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
    assert fake_pedr.calls[0]["project_id"] == "proj-1"
    assert result["latency_ms"] >= 0.0
    assert result["cache"]["hit"] is False
    assert cache.checked == 1
    assert cache.stored == 1
    assert result["quality"]["composite_score"] >= settings.tiered_routing_threshold
    assert result["quality"]["hard_failures"] == []
    assert result["routing"]["selected_model"] == "gpt-test"
    assert result["routing"]["estimated_cost_usd"] == 0.0
    assert result["routing"]["metrics"]["total_queries"] == 1
    assert result["routing"]["metrics"]["escalations"] == 0
    assert result["search_mode"] == "semantic"


def test_rag_service_sets_reasoning_effort_for_gpt5_models(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "Model compatibility check. [Document: doc-1, Chunk: 0]"
    )

    cache = _NoOpCacheService()
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-5.1",
        default_temperature=0.2,
        cost_monitor=None,
    )

    service.run_query(query="Validate GPT-5 chat params", top_k=2, project_id="proj-1")

    request = fake_client.chat.completions.requests[0]
    assert request["model"] == "gpt-5.1"
    assert request["reasoning_effort"] == "none"
    assert request["temperature"] == 0.2
    assert request["max_tokens"] == settings.rag_default_max_tokens


def test_rag_service_respects_search_mode(monkeypatch):
    # PEDR doesn't use search_mode directly - it uses RRF fusion across layers
    # This test verifies search_mode is passed through to the response
    fake_pedr = _FakePEDROrchestrator(results=[
        {
            "chunk_id": "chunk-h",
            "content": "Keyword weighted content about governance hybrids.",
            "document_id": "doc-h",
            "project_id": "proj-h",
            "chunk_index": 0,
            "source_type": "report",
            "rrf_score": 0.78,
            "embedding": [0.11, 0.22, 0.33],
        }
    ])
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "Hybrid search ensures coverage. [Document: doc-h, Chunk: 0]"
    )
    cache = _NoOpCacheService()
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=None,
    )

    result = service.run_query(
        query="Explain hybrid scoring benefits.",
        top_k=2,
        search_mode="keyword",
    )

    # PEDR is called (search_mode not passed to PEDR - it uses RRF)
    assert len(fake_pedr.calls) == 1
    assert result["search_mode"] == "keyword"
    assert result["sources"][0]["chunk_id"] == "chunk-h"
    assert cache.checked == 1
    assert cache.stored == 1


def test_rag_service_uses_cache_hit(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
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
        "quality": {
            "composite_score": 0.92,
            "threshold": settings.tiered_routing_threshold,
            "pillar_scores": {
                "linguistic_uncertainty": 0.95,
                "answer_integrity": 0.9,
                "source_provenance": 0.92,
            },
            "hard_failures": [],
            "reasons": [],
            "pre_escalation_score": None,
        },
        "routing": {
            "selected_model": settings.openai_chat_model,
            "escalated": False,
            "attempts": [
                {
                    "model": settings.openai_chat_model,
                    "quality_score": 0.92,
                    "below_threshold": False,
                    "hard_failures": [],
                    "citation_count": 1,
                }
            ],
            "estimated_cost_usd": 0.00018,
            "metrics": {"total_queries": 5, "escalations": 1},
        },
    }

    cache = _HitCacheService(cached_payload)
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=None,
    )

    result = service.run_query(
        query="What is the cached guidance?",
        top_k=3,
        project_id="proj-1",
    )

    assert result["answer"].startswith("Cached results already contain the answer")
    assert result["cache"]["hit"] is True
    assert fake_pedr.calls == []  # PEDR should not be called on cache hit
    assert cache.checked == 1
    assert result["quality"]["composite_score"] == pytest.approx(0.92)
    assert result["routing"]["selected_model"] == settings.openai_chat_model
    assert result["routing"]["escalated"] is False
    assert result["search_mode"] == "semantic"


def test_tiered_routing_escalates_on_low_quality(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
    fake_embedding = _FakeEmbeddingService()
    responses = {
        settings.openai_chat_model: "I'm sorry, I cannot help with that request.",
        settings.openai_escalation_model: (
            "Tiered routing ensures high quality answers while controlling cost. "
            "[Document: doc-1, Chunk: 0]"
        ),
    }
    fake_client = _TieredFakeOpenAIClient(responses)
    cache = _NoOpCacheService()

    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)

    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model=settings.openai_chat_model,
        escalation_model=settings.openai_escalation_model,
        default_temperature=0.0,
        cost_monitor=None,
    )

    result = service.run_query(
        query="Explain how tiered routing improves quality.",
        top_k=3,
        project_id="proj-1",
    )

    assert result["routing"]["escalated"] is True
    assert result["routing"]["selected_model"] == settings.openai_escalation_model
    assert result["quality"]["pre_escalation_score"] is not None
    assert result["quality"]["pre_escalation_score"] < settings.tiered_routing_threshold
    assert result["quality"]["composite_score"] >= settings.tiered_routing_threshold
    assert any(
        entry["model"] == settings.openai_escalation_model
        for entry in fake_client.chat.completions.requests
    )
    assert cache.checked == 1
    assert cache.stored == 1
    assert result["search_mode"] == "semantic"


def test_rag_service_emits_cost_metrics(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "Performance metrics with telemetry. [Document: doc-1, Chunk: 0]"
    )
    cache = _NoOpCacheService()
    monitor = _FakeCostMonitor(cost=0.002)

    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)

    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=monitor,
    )

    result = service.run_query(query="Record telemetry?", top_k=2, project_id="proj-telemetry")

    assert result["routing"]["estimated_cost_usd"] == pytest.approx(0.002)
    assert result["routing"]["attempts"][0]["cost_usd"] == pytest.approx(0.002)
    assert monitor.usage_events[0]["project_id"] == "proj-telemetry"
    assert result["search_mode"] == "semantic"


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
            "quality": {
                "composite_score": 0.93,
                "threshold": settings.tiered_routing_threshold,
                "pillar_scores": {
                    "linguistic_uncertainty": 0.96,
                    "answer_integrity": 0.92,
                    "source_provenance": 0.91,
                },
                "hard_failures": [],
                "reasons": [],
                "pre_escalation_score": None,
            },
            "routing": {
                "selected_model": settings.openai_chat_model,
                "escalated": False,
                "attempts": [
                    {
                        "model": settings.openai_chat_model,
                        "quality_score": 0.93,
                        "below_threshold": False,
                        "hard_failures": [],
                        "citation_count": 1,
                    }
                ],
                "estimated_cost_usd": 0.00018,
                "metrics": {"total_queries": 4, "escalations": 0},
            },
            "search_mode": kwargs.get("search_mode", "semantic"),
        }


def test_rag_search_endpoint(monkeypatch, auth_headers):
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
            "search_mode": "hybrid",
        },
        headers=auth_headers,
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
    assert fake_service.calls[0]["search_mode"] == "hybrid"
    assert body["search_mode"] == "hybrid"
    assert body["cache"]["hit"] is False
    assert body["quality"]["composite_score"] == pytest.approx(0.93)
    assert body["routing"]["selected_model"] == settings.openai_chat_model
    assert body["routing"]["escalated"] is False


def test_semantic_cache_hit_rate_reaches_target(monkeypatch):
    fake_pedr = _FakePEDROrchestrator()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "Markdown corpus insights. [Document: doc-9, Chunk: 1]"
    )
    workload_cache = _WorkloadCacheService()

    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=fake_pedr,
        embedding_service=fake_embedding,
        cache_service=workload_cache,
        client=fake_client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=None,
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
    assert len(fake_pedr.calls) == 8  # 8 cache misses = 8 PEDR calls
