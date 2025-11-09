"""Tests for the OpenAI embedding service wrappers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import embedding_service


class _DummyClient:
    def __init__(self, embeddings):
        self.embeddings = embeddings


def _configure_openai(monkeypatch, embeddings_api):
    class _FakeRateLimitError(Exception):
        pass

    class _FakeAPIError(Exception):
        pass

    monkeypatch.setattr(embedding_service, "_openai_import_error", None)
    monkeypatch.setattr(embedding_service, "OpenAI", lambda api_key: _DummyClient(embeddings_api))
    monkeypatch.setattr(embedding_service, "RateLimitError", _FakeRateLimitError)
    monkeypatch.setattr(embedding_service, "APIError", _FakeAPIError)
    monkeypatch.setattr(embedding_service.settings, "openai_api_key", "test-key", raising=False)
    monkeypatch.setattr(embedding_service.settings, "openai_embedding_model", "text-embedding-test", raising=False)
    monkeypatch.setattr(embedding_service.settings, "openai_embedding_dimension", 4, raising=False)
    monkeypatch.setattr(embedding_service, "_embedding_service", None)


def test_generate_embedding_retries_on_ratelimit(monkeypatch):
    """generate_embedding should retry through RateLimitError and return the first payload."""

    class _EmbeddingsAPI:
        def __init__(self):
            self.calls = 0

        def create(self, *, model, input):
            del model, input
            self.calls += 1
            if self.calls < 2:
                raise embedding_service.RateLimitError("limit")
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3, 0.4])])

    embeddings_api = _EmbeddingsAPI()
    _configure_openai(monkeypatch, embeddings_api)
    monkeypatch.setattr(embedding_service.time, "sleep", lambda _: None)

    service = embedding_service.EmbeddingService()
    vector = service.generate_embedding("hello world", retry_max=3)

    assert embeddings_api.calls == 2
    assert vector == [0.1, 0.2, 0.3, 0.4]


def test_generate_embeddings_batch_handles_api_retry(monkeypatch):
    """Batch generation should retry on API errors and preserve ordering."""

    class _EmbeddingsAPI:
        def __init__(self):
            self.calls = 0
            self.request_sizes = []

        def create(self, *, model, input):
            self.calls += 1
            self.request_sizes.append(len(input))
            if self.calls == 1:
                raise embedding_service.APIError("server error")
            response_vectors = []
            for text in input:
                response_vectors.append(SimpleNamespace(embedding=[float(len(text)), 1.0]))
            return SimpleNamespace(data=response_vectors)

    embeddings_api = _EmbeddingsAPI()
    _configure_openai(monkeypatch, embeddings_api)
    monkeypatch.setattr(embedding_service.time, "sleep", lambda _: None)

    service = embedding_service.EmbeddingService()
    batch = service.generate_embeddings_batch(["alpha", "beta", "gamma"], batch_size=2, retry_max=2)

    assert embeddings_api.calls == 3
    assert embeddings_api.request_sizes == [2, 2, 1]
    assert batch == [[5.0, 1.0], [4.0, 1.0], [5.0, 1.0]]
