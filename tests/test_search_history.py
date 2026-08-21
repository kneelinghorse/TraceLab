"""Tests for search history logging, listing, and replay APIs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.v1 import search as search_router
from app.api.v1 import search_history as history_router
from app.core.config import settings
from app.core.security import (
    ROLE_SERVICE,
    AuthenticatedUser,
    require_authenticated_user,
)
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.project import Project
from app.models.search_history import SearchHistory
from app.models.user import User
from app.services.search_history import SearchHistoryService


class _StubRagService:
    """Minimal fake RAG service returning deterministic payloads."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "answer": "Search results summarized.",
            "citations": [
                {
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.94,
                    "snippet": "Chunk content excerpt.",
                }
            ],
            "sources": [
                {
                    "chunk_id": "chunk-1",
                    "content": "Chunk content excerpt.",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.94,
                }
            ],
            "latency_ms": 42.0,
            "compression": {
                "original_chunks": 3,
                "filtered_chunks": 1,
                "original_tokens": 1200,
                "filtered_tokens": 400,
                "reduction_ratio": 0.666,
                "threshold": 0.7,
                "compression_ms": 5.2,
            },
            "cache": {
                "hit": False,
                "score": None,
                "age_seconds": None,
                "ttl_seconds": None,
            },
            "quality": {
                "composite_score": 0.92,
                "threshold": 0.85,
                "pillar_scores": {
                    "linguistic_uncertainty": 0.93,
                    "answer_integrity": 0.91,
                    "source_provenance": 0.9,
                },
                "hard_failures": [],
                "reasons": [],
                "pre_escalation_score": None,
            },
            "routing": {
                "selected_model": "gpt-test",
                "escalated": False,
                "attempts": [
                    {
                        "model": "gpt-test",
                        "quality_score": 0.92,
                        "below_threshold": False,
                        "hard_failures": [],
                        "citation_count": 1,
                    }
                ],
                "estimated_cost_usd": 0.0002,
                "metrics": {"total_queries": 1, "escalations": 0},
            },
            "search_mode": kwargs.get("search_mode", "semantic"),
        }


class _StubRetrievalService:
    """Return deterministic semantic search results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return [
            {
                "chunk_id": "chunk-1",
                "content": "Chunk content excerpt.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.94,
            }
        ]


def test_search_history_logged_and_listed(monkeypatch, auth_headers):
    """Posting to /search logs a row retrievable via the history endpoint."""
    fake_service = _StubRagService()
    monkeypatch.setattr(search_router, "get_rag_service", lambda: fake_service)

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"query": "What is the policy?", "top_k": 3, "search_mode": "hybrid"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    history_response = client.get(
        "/api/v1/search/history?limit=5", headers=auth_headers
    )
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["entries"], "Expected at least one history entry."
    first = payload["entries"][0]
    assert first["query_text"] == "What is the policy?"
    assert first["search_mode"] == "hybrid"
    assert first["top_k"] == 3
    assert first["result_count"] == 1


def test_replay_endpoint_runs_query_and_logs(monkeypatch, auth_headers):
    """Replay endpoint re-executes the query and records a new history row."""
    service = SearchHistoryService()
    entry = service.record_search(
        query="Replay me",
        search_mode="semantic",
        filters={"project_id": "proj-1", "source_type": "report"},
        top_k=4,
        result_count=1,
        duration_ms=25.0,
        cache_hit=False,
        executed_by="tester",
        top_chunks=["chunk-legacy"],
    )

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(history_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(history_router, "get_retrieval_service", lambda: fake_retrieval)

    client = TestClient(app)
    replay = client.post(f"/api/v1/search/replay/{entry.id}", headers=auth_headers)
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["entry"]["id"] == str(entry.id)
    assert payload["rag"]["answer"] == "Search results summarized."
    assert payload["semantic"]["results"][0]["chunk_id"] == "chunk-1"

    history = client.get("/api/v1/search/history", headers=auth_headers).json()[
        "entries"
    ]
    assert len(history) >= 2, "Expected replay to insert a new entry."
    assert "allowed_project_ids" not in fake_rag.calls[0]
    assert "allowed_project_ids" not in fake_retrieval.calls[0]


def test_clear_history_endpoint(auth_headers):
    """Deleting history empties the table and returns deleted count."""
    service = SearchHistoryService()
    service.record_search(
        query="First query",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=10,
        cache_hit=False,
        executed_by="tester",
        top_chunks=[],
    )
    service.record_search(
        query="Second query",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=10,
        cache_hit=False,
        executed_by="tester",
        top_chunks=[],
    )

    client = TestClient(app)
    delete_resp = client.delete("/api/v1/search/history", headers=auth_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] >= 2

    history = client.get("/api/v1/search/history", headers=auth_headers).json()
    assert history["entries"] == []


def test_retention_globally_purges_expired_other_owner_and_legacy_rows(db_session):
    """Any new search enforces age retention even for inactive/legacy owners."""
    active_user = User(
        id=uuid4(),
        email="retention-active@example.test",
        display_name="Retention Active",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    inactive_user = User(
        id=uuid4(),
        email="retention-inactive@example.test",
        display_name="Retention Inactive",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    expired_at = datetime.utcnow() - timedelta(days=31)
    expired_other = SearchHistory(
        query_text="expired other owner",
        owner_id=inactive_user.id,
        user_label=inactive_user.display_name,
        created_at=expired_at,
        updated_at=expired_at,
    )
    expired_legacy = SearchHistory(
        query_text="expired unresolved legacy",
        owner_id=None,
        user_label="No matching user",
        created_at=expired_at,
        updated_at=expired_at,
    )
    fresh_other = SearchHistory(
        query_text="fresh other owner",
        owner_id=inactive_user.id,
        user_label=inactive_user.display_name,
    )
    db_session.add_all(
        [
            active_user,
            inactive_user,
            expired_other,
            expired_legacy,
            fresh_other,
        ]
    )
    db_session.commit()
    expired_ids = {expired_other.id, expired_legacy.id}

    SearchHistoryService(max_age_days=30).record_search(
        query="trigger retention",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=1,
        cache_hit=False,
        executed_by=active_user.display_name,
        owner_id=active_user.id,
    )

    db_session.expire_all()
    remaining_ids = {
        row.id
        for row in db_session.query(SearchHistory).filter(
            SearchHistory.id.in_([*expired_ids, fresh_other.id])
        )
    }
    assert remaining_ids == {fresh_other.id}


def test_history_uses_stable_owner_ids_and_cross_owner_operations_fail_closed(
    monkeypatch, db_session
):
    """Duplicate labels and unresolved legacy rows never define ordinary ownership."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    first_user = User(
        id=uuid4(),
        email="history-first@example.test",
        display_name="Duplicate History Label",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    second_user = User(
        id=uuid4(),
        email="history-second@example.test",
        display_name="Duplicate History Label",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add_all([first_user, second_user])
    db_session.commit()

    service = SearchHistoryService()
    first = service.record_search(
        query="first history",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=1,
        cache_hit=False,
        executed_by=first_user.display_name,
        owner_id=first_user.id,
    )
    second = service.record_search(
        query="second history",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=1,
        cache_hit=False,
        executed_by=second_user.display_name,
        owner_id=second_user.id,
    )
    unresolved = SearchHistory(
        query_text="unresolved legacy history",
        user_label=first_user.display_name,
        owner_id=None,
    )
    db_session.add(unresolved)
    db_session.commit()

    caller = AuthenticatedUser(
        user_id=first_user.id,
        email=first_user.email,
        display_name=first_user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/search/history")
        replay = client.post(f"/api/v1/search/replay/{second.id}")
        missing_replay = client.post(f"/api/v1/search/replay/{uuid4()}")
        cleared = client.delete("/api/v1/search/history")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert listing.status_code == 200
    assert [entry["id"] for entry in listing.json()["entries"]] == [
        str(first.id)
    ]
    assert listing.json()["entries"][0]["owner_id"] == str(first_user.id)
    assert replay.status_code == 404
    assert missing_replay.status_code == 404
    assert cleared.json() == {"deleted": 1}
    assert service.get_entry(second.id, owner_id=None) is not None
    assert service.get_entry(unresolved.id, owner_id=first_user.id) is None


def test_replay_empty_project_scope_avoids_provider_singletons(
    monkeypatch, db_session
):
    """Replay with no accessible projects does not initialize caches/providers."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="history-empty@example.test",
        display_name="History Empty",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add(user)
    db_session.commit()
    entry = SearchHistoryService().record_search(
        query="must not reach providers",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=4,
        duration_ms=2,
        cache_hit=False,
        executed_by=user.display_name,
        owner_id=user.id,
    )

    def _unexpected_singleton():
        raise AssertionError("empty authorization scope must avoid service singletons")

    monkeypatch.setattr(history_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(
        history_router, "get_retrieval_service", _unexpected_singleton
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        response = TestClient(app).post(f"/api/v1/search/replay/{entry.id}")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert response.status_code == 200, response.text
    assert response.json()["rag"]["sources"] == []
    assert response.json()["semantic"]["results"] == []
    assert response.json()["entry"]["result_count"] == 0


def test_history_list_batch_filters_chunks_through_live_allowed_documents(
    monkeypatch, db_session
):
    """Stored chunk IDs and counts cannot reveal deleted or foreign documents."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="history-visible@example.test",
        display_name="History Visible",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    other_user = User(
        id=uuid4(),
        email="history-foreign@example.test",
        display_name="History Foreign",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    allowed_project = Project(
        id=uuid4(), name="Allowed history project", owner_id=user.id
    )
    foreign_project = Project(
        id=uuid4(), name="Foreign history project", owner_id=other_user.id
    )
    db_session.add_all([user, other_user, allowed_project, foreign_project])
    db_session.flush()

    visible_document = Document(
        id=uuid4(), project_id=allowed_project.id, name="visible"
    )
    deleted_document = Document(
        id=uuid4(),
        project_id=allowed_project.id,
        name="deleted",
        deleted_at=datetime.utcnow(),
    )
    foreign_document = Document(
        id=uuid4(), project_id=foreign_project.id, name="foreign"
    )
    db_session.add_all(
        [visible_document, deleted_document, foreign_document]
    )
    db_session.flush()
    visible_chunk = DocumentChunk(
        id=uuid4(), document_id=visible_document.id, chunk_index=0, content="v"
    )
    deleted_chunk = DocumentChunk(
        id=uuid4(), document_id=deleted_document.id, chunk_index=0, content="d"
    )
    foreign_chunk = DocumentChunk(
        id=uuid4(), document_id=foreign_document.id, chunk_index=0, content="f"
    )
    db_session.add_all([visible_chunk, deleted_chunk, foreign_chunk])
    db_session.commit()

    entry = SearchHistoryService().record_search(
        query="historical visibility",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=9,
        duration_ms=3,
        cache_hit=False,
        executed_by=user.display_name,
        owner_id=user.id,
        top_chunks=[
            str(foreign_chunk.id),
            str(visible_chunk.id),
            str(deleted_chunk.id),
            "not-a-uuid",
        ],
    )

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(history_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        history_router, "get_retrieval_service", lambda: fake_retrieval
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        response = TestClient(app).get("/api/v1/search/history")
        replay = TestClient(app).post(f"/api/v1/search/replay/{entry.id}")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert response.status_code == 200, response.text
    payload = response.json()["entries"]
    assert [item["id"] for item in payload] == [str(entry.id)]
    assert payload[0]["top_chunks"] == [str(visible_chunk.id)]
    assert payload[0]["result_count"] == 1
    assert replay.status_code == 200, replay.text
    assert replay.json()["entry"]["top_chunks"] == [str(visible_chunk.id)]
    assert replay.json()["entry"]["result_count"] == 1


def test_service_principal_has_no_history_namespace_and_search_logs_nothing(
    monkeypatch, db_session
):
    """Machine searches execute without reading, replaying, clearing, or writing history."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner = db_session.query(User).first()
    service = SearchHistoryService()
    entry = service.record_search(
        query="human-only history",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=1,
        cache_hit=False,
        executed_by=owner.display_name,
        owner_id=owner.id,
    )

    def _unexpected_singleton():
        raise AssertionError("empty service scope must not initialize RAG")

    monkeypatch.setattr(search_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(history_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(
        history_router, "get_retrieval_service", _unexpected_singleton
    )
    principal = AuthenticatedUser(
        user_id=uuid4(),
        email="history-service@example.test",
        display_name="history-service",
        role=ROLE_SERVICE,
    )
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/search/history")
        replay = client.post(f"/api/v1/search/replay/{entry.id}")
        cleared = client.delete("/api/v1/search/history")
        search = client.post(
            "/api/v1/search",
            json={"query": "machine query", "search_mode": "semantic"},
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert listing.status_code == 200
    assert listing.json()["entries"] == []
    assert replay.status_code == 404
    assert cleared.json() == {"deleted": 0}
    assert search.status_code == 200, search.text
    remaining = service.list_history(limit=10, owner_id=None)
    assert [row.id for row in remaining] == [entry.id]


def test_service_principal_preserves_flag_off_history_behavior(
    monkeypatch, db_session
):
    """RBAC-off keeps global history, replay, logging, and clear behavior."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    service_user = User(
        id=uuid4(),
        email="history-service-flag-off@example.test",
        display_name="history-service-flag-off",
        password_hash="not-a-real-hash",  # noqa: S106
        role=ROLE_SERVICE,
    )
    db_session.add(service_user)
    db_session.commit()
    history_service = SearchHistoryService()
    existing = history_service.record_search(
        query="legacy global history",
        search_mode="semantic",
        filters={},
        top_k=5,
        result_count=0,
        duration_ms=1,
        cache_hit=False,
        executed_by="legacy human",
        owner_id=None,
    )
    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(search_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(history_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        history_router, "get_retrieval_service", lambda: fake_retrieval
    )
    principal = AuthenticatedUser(
        user_id=service_user.id,
        email=service_user.email,
        display_name=service_user.display_name,
        role=ROLE_SERVICE,
    )
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/search/history")
        replay = client.post(f"/api/v1/search/replay/{existing.id}")
        searched = client.post(
            "/api/v1/search",
            json={"query": "flag-off machine query", "search_mode": "semantic"},
        )
        cleared = client.delete("/api/v1/search/history")
        after_clear = client.get("/api/v1/search/history")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert listing.status_code == 200
    assert str(existing.id) in {entry["id"] for entry in listing.json()["entries"]}
    assert replay.status_code == 200
    assert searched.status_code == 200
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] >= 3
    assert after_clear.json()["entries"] == []
    assert all("allowed_project_ids" not in call for call in fake_rag.calls)
    assert "allowed_project_ids" not in fake_retrieval.calls[0]


def test_replay_passes_request_project_scope_to_both_services(
    monkeypatch, db_session
):
    """Replay binds RAG and semantic retrieval to the same project scope."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="history-scoped@example.test",
        display_name="History Scoped",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    project = Project(id=uuid4(), name="History project", owner_id=user.id)
    db_session.add_all([user, project])
    db_session.commit()
    entry = SearchHistoryService().record_search(
        query="scoped replay",
        search_mode="semantic",
        filters={"project_id": str(project.id)},
        top_k=5,
        result_count=0,
        duration_ms=2,
        cache_hit=False,
        executed_by=user.display_name,
        owner_id=user.id,
    )

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(history_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        history_router, "get_retrieval_service", lambda: fake_retrieval
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        response = TestClient(app).post(f"/api/v1/search/replay/{entry.id}")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert response.status_code == 200, response.text
    assert fake_rag.calls[0]["allowed_project_ids"] == [project.id]
    assert fake_retrieval.calls[0]["allowed_project_ids"] == [project.id]
