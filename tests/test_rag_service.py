"""Tests for the RAG service orchestration and API endpoint."""
from fastapi.testclient import TestClient

from app.api.v1 import search as search_router
from app.main import app
from app.core.config import settings
from app.services import rag_service as rag_module


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


def test_rag_service_run_query(monkeypatch):
    fake_retrieval = _FakeRetrievalService()
    fake_embedding = _FakeEmbeddingService()
    fake_client = _FakeOpenAIClient(
        "The repository embraces iterative delivery. [Document: doc-1, Chunk: 0]"
    )

    service = rag_module.RagService(
        retrieval_service=fake_retrieval,
        embedding_service=fake_embedding,
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
