"""Integration tests for the RAG pipeline orchestration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import rag_service as rag_module
from app.services.quality_assessment import QualityAssessmentResult


class _StubEmbeddingService:
    def __init__(self):
        self.queries = []

    def generate_embedding(self, text: str):
        self.queries.append(text)
        return [float(len(text)), 0.25, 0.5]


class _StubRetrievalService:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def search(self, *, query, **kwargs):
        self.calls.append({"query": query, "kwargs": kwargs})
        return list(self.results)


class _StubCacheService:
    def __init__(self, cached=None):
        self.cached = cached
        self.stored = []
        self.last_metadata = None

    def check_cache(self, *, query_embedding, metadata):
        del query_embedding
        self.last_metadata = dict(metadata)
        if not self.cached:
            return None
        # return a copy so callers cannot mutate in-place
        return dict(self.cached)

    def store_in_cache(self, *, result, **_):
        self.stored.append(result)


class _StubCostMonitor:
    def __init__(self):
        self.usage_events = []
        self.cache_hits = 0

    def track_usage(
        self,
        *,
        model,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        **kwargs,
    ):
        usage = {
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int(
                total_tokens or (prompt_tokens or 0) + (completion_tokens or 0)
            ),
        }
        event = {"model": model, "usage": usage, "cost_usd": 0.00042}
        self.usage_events.append({"event": event, "kwargs": kwargs})
        return {"usage": usage, "cost_usd": event["cost_usd"]}

    def record_cache_hit(self, **_):
        self.cache_hits += 1


class _StubQualityAssessor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def assess(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _StubChatClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.responses) - 1, len(self.calls) - 1)
        return self.responses[index]


def _completion_payload(content: str) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=48, total_tokens=60)
    return SimpleNamespace(choices=[choice], usage=usage)


def _build_service(monkeypatch, *, cache=None, responses=None):
    monkeypatch.setattr(rag_module, "_openai_import_error", None)
    monkeypatch.setattr(
        rag_module.settings, "openai_api_key", "test-key", raising=False
    )
    embedding = _StubEmbeddingService()
    retrieval = _StubRetrievalService(
        [
            {
                "document_id": "doc-1",
                "chunk_index": 0,
                "chunk_id": "chunk-0",
                "content": "Traceability ensures every answer cites a document.",
                "score": 0.92,
                "embedding": [0.1, 0.2, 0.3],
            },
            {
                "document_id": "doc-2",
                "chunk_index": 1,
                "chunk_id": "chunk-1",
                "content": "Load testing requires 100 concurrent RAG queries.",
                "score": 0.84,
                "embedding": [0.2, 0.1, 0.3],
            },
        ]
    )
    cache_service = cache or _StubCacheService()
    cost_monitor = _StubCostMonitor()
    quality_result = QualityAssessmentResult(
        composite_score=0.93,
        threshold=0.85,
        pillar_scores={
            "linguistic_uncertainty": 0.96,
            "answer_integrity": 0.92,
            "source_provenance": 0.95,
        },
        hard_failures=[],
        escalate=False,
        reasons=[],
    )
    assessor = _StubQualityAssessor(quality_result)
    client = _StubChatClient(
        responses or [_completion_payload("Answer [Document: doc-1, Chunk: 0]")]
    )

    service = rag_module.RagService(
        retrieval_service=retrieval,
        embedding_service=embedding,
        cache_service=cache_service,
        client=client,
        quality_assessor=assessor,
        cost_monitor=cost_monitor,
        model="gpt-5.1",
        escalation_model="gpt-5.2",
    )
    return service, embedding, retrieval, cache_service, cost_monitor, assessor, client


@pytest.mark.skip(
    reason="openai/httpx version incompatibility — httpx removed 'proxies' kwarg; needs openai SDK upgrade"
)
def test_rag_pipeline_generates_cited_answer(monkeypatch):
    service, embedding, retrieval, cache_service, cost_monitor, assessor, client = (
        _build_service(monkeypatch)
    )

    result = service.run_query("Summarize Mission Protocol quality gates", top_k=2)

    assert result["answer"].startswith("Answer")
    assert result["citations"][0]["document_id"] == "doc-1"
    assert result["cache"]["hit"] is False
    assert result["routing"]["attempts"][0]["usage"]["prompt_tokens"] == 12
    assert (
        retrieval.calls
        and retrieval.calls[0]["query"] == "Summarize Mission Protocol quality gates"
    )
    assert embedding.queries == ["Summarize Mission Protocol quality gates"]
    assert cache_service.stored, "Result should be cached for future hits"
    assert cost_monitor.usage_events, "Usage telemetry should be recorded"
    assert assessor.calls and assessor.calls[0]["query"].startswith("Summarize Mission")
    assert client.calls and client.calls[0]["messages"]


@pytest.mark.skip(
    reason="openai/httpx version incompatibility — httpx removed 'proxies' kwarg; needs openai SDK upgrade"
)
def test_rag_pipeline_returns_cached_payload(monkeypatch):
    cached = {
        "answer": "Cached answer",
        "sources": [],
        "citations": [],
    }
    cache_service = _StubCacheService(cached=cached)
    service, embedding, retrieval, cache_service, cost_monitor, _, _ = _build_service(
        monkeypatch,
        cache=cache_service,
    )

    result = service.run_query("Use cache please")

    assert result["answer"] == "Cached answer"
    assert result["cache"]["hit"] is True
    assert not cache_service.stored
    assert not retrieval.calls
    assert embedding.queries == ["Use cache please"]
    assert cost_monitor.cache_hits == 1
