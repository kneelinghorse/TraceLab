"""Validate retrieval service and API plumbing."""
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import retrieval as retrieval_router
from app.services import retrieval_service as retrieval_module


class _FakeEmbeddingService:
    def __init__(self):
        self.requests = []

    def generate_embedding(self, text):
        self.requests.append(text)
        return [0.1, 0.2, 0.3]


class _FakeQdrantService:
    def __init__(self):
        self.calls = []

    def search_chunks(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "chunk_id": "chunk-1",
                "content": "Example content",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.42,
            }
        ]


def test_retrieval_service_search(monkeypatch):
    fake_embedding = _FakeEmbeddingService()
    fake_qdrant = _FakeQdrantService()
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: fake_embedding
    )
    monkeypatch.setattr(
        retrieval_module, "get_qdrant_service", lambda: fake_qdrant
    )

    service = retrieval_module.RetrievalService()
    results = service.search(
        query="climate policy trends",
        top_k=3,
        project_id="proj-1",
        document_id=None,
        source_type="report",
        hnsw_ef=256,
    )

    assert fake_embedding.requests == ["climate policy trends"]
    assert fake_qdrant.calls[0]["top_k"] == 3
    assert fake_qdrant.calls[0]["project_id"] == "proj-1"
    assert fake_qdrant.calls[0]["source_type"] == "report"
    assert fake_qdrant.calls[0]["hnsw_ef"] == 256
    assert results[0]["chunk_id"] == "chunk-1"


def test_retrieval_service_auto_hnsw(monkeypatch):
    fake_embedding = _FakeEmbeddingService()
    fake_qdrant = _FakeQdrantService()
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: fake_embedding
    )
    monkeypatch.setattr(
        retrieval_module, "get_qdrant_service", lambda: fake_qdrant
    )

    service = retrieval_module.RetrievalService()
    results = service.search(
        query="what is the impact of hnsw tuning?",
        top_k=20,
        project_id=None,
        document_id=None,
        source_type=None,
    )

    expected_hnsw = service.recommend_hnsw_ef(20)
    assert fake_qdrant.calls[0]["hnsw_ef"] == expected_hnsw
    assert results[0]["chunk_id"] == "chunk-1"


def test_retrieval_api_endpoint(monkeypatch, auth_headers):
    fake_embedding = _FakeEmbeddingService()
    fake_qdrant = _FakeQdrantService()
    monkeypatch.setattr(
        retrieval_router, "get_retrieval_service", lambda: retrieval_module.RetrievalService()
    )
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: fake_embedding
    )
    monkeypatch.setattr(
        retrieval_module, "get_qdrant_service", lambda: fake_qdrant
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "renewable energy subsidies",
            "top_k": 5,
            "project_id": "8f2f1c4e-22a6-4a4d-8b91-6f7f2bc5d1cc",
            "source_type": "report",
            "hnsw_ef": 64,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["chunk_id"] == "chunk-1"
    assert fake_embedding.requests == ["renewable energy subsidies"]
    assert fake_qdrant.calls[0]["hnsw_ef"] == 64
