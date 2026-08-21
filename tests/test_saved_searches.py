"""Tests covering the saved searches API + execution flow."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.v1 import saved_searches as saved_router
from app.core.config import settings
from app.core.security import (
    ROLE_SERVICE,
    AuthenticatedUser,
    require_authenticated_user,
)
from app.main import app
from app.models.project import Project
from app.models.saved_search import SavedSearch
from app.models.user import User
from app.services import saved_search as saved_service_module
from app.services.saved_search import SavedSearchService


class _StubRagService:
    """Minimal fake RAG service returning deterministic payloads."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "answer": "Saved search results summarized.",
            "citations": [],
            "sources": [
                {
                    "chunk_id": "chunk-001",
                    "content": "Chunk content excerpt.",
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "chunk_index": 0,
                    "source_type": "report",
                    "score": 0.91,
                }
            ],
            "latency_ms": 33.5,
            "compression": {
                "original_chunks": 5,
                "filtered_chunks": 2,
                "original_tokens": 1400,
                "filtered_tokens": 500,
                "reduction_ratio": 0.64,
                "threshold": 0.7,
                "compression_ms": 4.5,
            },
            "cache": {
                "hit": False,
                "score": None,
                "age_seconds": None,
                "ttl_seconds": None,
            },
            "quality": {
                "composite_score": 0.9,
                "threshold": 0.85,
                "pillar_scores": {
                    "linguistic_uncertainty": 0.92,
                    "answer_integrity": 0.88,
                    "source_provenance": 0.89,
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
                        "quality_score": 0.9,
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
                "chunk_id": "chunk-001",
                "content": "Chunk content excerpt.",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "chunk_index": 0,
                "source_type": "report",
                "score": 0.91,
            }
        ]


def test_saved_search_crud_flow(auth_headers):
    """Create, list, update, and delete saved searches through the API."""
    client = TestClient(app)

    create_resp = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Daily briefing",
            "description": "Monitor checkout errors",
            "query_text": "Checkout errors",
            "search_mode": "hybrid",
            "filters": {"project_id": "proj-1"},
            "top_k": 6,
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Daily briefing"
    assert created["use_count"] == 0

    list_resp = client.get("/api/v1/saved-searches", headers=auth_headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["items"][0]["id"] == created["id"]
    assert payload["limit_per_user"] == 50

    update_resp = client.put(
        f"/api/v1/saved-searches/{created['id']}",
        json={"name": "Checkout fallout", "top_k": 10},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Checkout fallout"
    assert updated["top_k"] == 10

    delete_resp = client.delete(
        f"/api/v1/saved-searches/{created['id']}", headers=auth_headers
    )
    assert delete_resp.status_code == 204

    after_delete = client.get("/api/v1/saved-searches", headers=auth_headers).json()
    assert after_delete["items"] == []


def test_execute_saved_search_runs_services(monkeypatch, auth_headers):
    """Executing a saved search calls rag + retrieval services and tracks usage."""
    client = TestClient(app)
    create = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Replay saved search",
            "description": "Quick access",
            "query_text": "Policy updates",
            "search_mode": "semantic",
            "filters": {"project_id": "proj-2", "source_type": "report"},
            "top_k": 4,
        },
        headers=auth_headers,
    )
    saved_id = create.json()["id"]

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(saved_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(saved_router, "get_retrieval_service", lambda: fake_retrieval)

    execute = client.post(
        f"/api/v1/saved-searches/{saved_id}/execute", headers=auth_headers
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["saved_search"]["id"] == saved_id
    assert payload["saved_search"]["use_count"] == 1
    assert payload["rag"]["answer"] == "Saved search results summarized."
    assert payload["semantic"]["results"][0]["chunk_id"] == "chunk-001"

    list_after = client.get("/api/v1/saved-searches", headers=auth_headers).json()
    assert list_after["items"][0]["use_count"] == 1
    assert fake_rag.calls and fake_retrieval.calls
    assert "allowed_project_ids" not in fake_rag.calls[0]
    assert "allowed_project_ids" not in fake_retrieval.calls[0]


def test_saved_search_limit_enforced(monkeypatch, auth_headers):
    """Creating more than the configured limit returns HTTP 400."""
    limited_service = SavedSearchService(max_saved_per_user=1)
    monkeypatch.setattr(saved_service_module, "_saved_search_service", limited_service)
    monkeypatch.setattr(
        saved_router, "get_saved_search_service", lambda: limited_service
    )

    client = TestClient(app)
    first = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "First saved search",
            "query_text": "Query 1",
            "search_mode": "semantic",
            "filters": {},
            "top_k": 5,
        },
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Second saved search",
            "query_text": "Query 2",
            "search_mode": "semantic",
            "filters": {},
            "top_k": 5,
        },
        headers=auth_headers,
    )
    assert second.status_code == 400
    assert "limit" in second.text.lower()


def test_saved_searches_use_stable_owner_ids_and_cross_owner_ids_are_404(
    monkeypatch, db_session
):
    """Duplicate display names cannot merge ownership or expose singular IDs."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    first_user = User(
        id=uuid4(),
        email="saved-first@example.test",
        display_name="Duplicate Display",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    second_user = User(
        id=uuid4(),
        email="saved-second@example.test",
        display_name="Duplicate Display",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add_all([first_user, second_user])
    db_session.commit()

    service = SavedSearchService()
    first = service.create(
        owner_id=first_user.id,
        owner=first_user.display_name,
        name="Same bookmark name",
        query_text="first query",
        search_mode="semantic",
        filters={},
        top_k=5,
    )
    second = service.create(
        owner_id=second_user.id,
        owner=second_user.display_name,
        name="Same bookmark name",
        query_text="second query",
        search_mode="semantic",
        filters={},
        top_k=5,
    )
    db_session.add(
        SavedSearch(
            name="Unresolved legacy row",
            query_text="legacy query",
            owner="Duplicate Display",
            owner_id=None,
        )
    )
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
        listing = client.get("/api/v1/saved-searches")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()["items"]] == [
            str(first.id)
        ]
        assert listing.json()["items"][0]["owner_id"] == str(first_user.id)

        update = client.put(
            f"/api/v1/saved-searches/{second.id}", json={"name": "stolen"}
        )
        delete = client.delete(f"/api/v1/saved-searches/{second.id}")
        execute = client.post(f"/api/v1/saved-searches/{second.id}/execute")
        assert update.status_code == 404
        assert delete.status_code == 404
        assert execute.status_code == 404
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert service.get(second.id, None) is not None
    assert service.get(second.id, first_user.id) is None


def test_missing_saved_search_uuid_is_404_for_every_singular_operation(
    monkeypatch, db_session
):
    """A syntactically valid absent ID fails closed without reaching providers."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="saved-missing@example.test",
        display_name="Saved Missing",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add(user)
    db_session.commit()

    def _unexpected_singleton():
        raise AssertionError("missing saved search must not initialize providers")

    monkeypatch.setattr(saved_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(
        saved_router, "get_retrieval_service", _unexpected_singleton
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
    missing_id = uuid4()
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        client = TestClient(app)
        update = client.put(
            f"/api/v1/saved-searches/{missing_id}",
            json={"name": "still missing"},
        )
        delete = client.delete(f"/api/v1/saved-searches/{missing_id}")
        execute = client.post(f"/api/v1/saved-searches/{missing_id}/execute")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert update.status_code == 404
    assert delete.status_code == 404
    assert execute.status_code == 404


def test_service_principal_cannot_use_saved_search_artifacts(
    monkeypatch, db_session
):
    """Machine identities get no human bookmark namespace or execution surface."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner = db_session.query(User).first()
    entry = SavedSearchService().create(
        owner_id=owner.id,
        owner=owner.display_name,
        name="Human-only bookmark",
        query_text="human query",
        search_mode="semantic",
        filters={},
        top_k=5,
    )

    def _unexpected_singleton():
        raise AssertionError("service principal must not initialize providers")

    monkeypatch.setattr(saved_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(
        saved_router, "get_retrieval_service", _unexpected_singleton
    )
    principal = AuthenticatedUser(
        user_id=uuid4(),
        email="saved-service@example.test",
        display_name="saved-service",
        role=ROLE_SERVICE,
    )
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/saved-searches")
        create = client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Machine bookmark",
                "query_text": "forbidden",
                "search_mode": "semantic",
                "filters": {},
                "top_k": 5,
            },
        )
        update = client.put(
            f"/api/v1/saved-searches/{entry.id}", json={"name": "stolen"}
        )
        delete = client.delete(f"/api/v1/saved-searches/{entry.id}")
        execute = client.post(f"/api/v1/saved-searches/{entry.id}/execute")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert listing.status_code == 200
    assert listing.json()["items"] == []
    assert create.status_code == 403
    assert update.status_code == 404
    assert delete.status_code == 404
    assert execute.status_code == 404
    persisted = SavedSearchService().get(entry.id, None)
    assert persisted is not None
    assert persisted.name == "Human-only bookmark"
    assert persisted.use_count == 0


def test_service_principal_preserves_flag_off_saved_search_behavior(
    monkeypatch, db_session
):
    """RBAC-off keeps caller ownership and the legacy provider call shape."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    limited_service = SavedSearchService(max_saved_per_user=2)
    monkeypatch.setattr(saved_service_module, "_saved_search_service", limited_service)
    service_user = User(
        id=uuid4(),
        email="saved-service-flag-off@example.test",
        display_name="saved-service-flag-off",
        password_hash="not-a-real-hash",  # noqa: S106
        role=ROLE_SERVICE,
    )
    other_user = User(
        id=uuid4(),
        email="saved-other-flag-off@example.test",
        display_name="saved-other-flag-off",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add_all([service_user, other_user])
    db_session.commit()
    foreign = SavedSearchService().create(
        owner_id=other_user.id,
        owner=other_user.display_name,
        name="Foreign flag-off bookmark",
        query_text="must remain private",
        search_mode="semantic",
        filters={},
        top_k=5,
    )
    legacy = SavedSearch(
        name="Legacy flag-off bookmark",
        query_text="legacy caller-owned query",
        owner=service_user.display_name,
        owner_id=None,
    )
    db_session.add(legacy)
    db_session.commit()
    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(saved_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        saved_router, "get_retrieval_service", lambda: fake_retrieval
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
        created = client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Flag-off machine bookmark",
                "query_text": "legacy unrestricted query",
                "search_mode": "semantic",
                "filters": {},
                "top_k": 5,
            },
        )
        assert created.status_code == 201, created.text
        saved_id = created.json()["id"]
        over_limit = client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Over legacy-aware limit",
                "query_text": "must be rejected",
                "search_mode": "semantic",
                "filters": {},
                "top_k": 5,
            },
        )
        listing = client.get("/api/v1/saved-searches")
        updated = client.put(
            f"/api/v1/saved-searches/{saved_id}",
            json={"name": "Updated flag-off machine bookmark"},
        )
        legacy_duplicate = client.put(
            f"/api/v1/saved-searches/{legacy.id}",
            json={"name": "Updated flag-off machine bookmark"},
        )
        executed = client.post(f"/api/v1/saved-searches/{saved_id}/execute")
        foreign_update = client.put(
            f"/api/v1/saved-searches/{foreign.id}",
            json={"name": "stolen"},
        )
        foreign_execute = client.post(
            f"/api/v1/saved-searches/{foreign.id}/execute"
        )
        foreign_delete = client.delete(f"/api/v1/saved-searches/{foreign.id}")
        deleted = client.delete(f"/api/v1/saved-searches/{saved_id}")
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert listing.status_code == 200
    assert over_limit.status_code == 400
    assert "limit" in over_limit.text.lower()
    assert saved_id in {item["id"] for item in listing.json()["items"]}
    assert str(legacy.id) in {item["id"] for item in listing.json()["items"]}
    assert str(foreign.id) not in {item["id"] for item in listing.json()["items"]}
    assert updated.status_code == 200
    assert legacy_duplicate.status_code == 400
    assert "already exists" in legacy_duplicate.text.lower()
    assert executed.status_code == 200
    assert foreign_update.status_code == 404
    assert foreign_execute.status_code == 404
    assert foreign_delete.status_code == 404
    assert deleted.status_code == 204
    assert "allowed_project_ids" not in fake_rag.calls[0]
    assert "allowed_project_ids" not in fake_retrieval.calls[0]


def test_saved_search_empty_project_scope_avoids_provider_singletons(
    monkeypatch, db_session
):
    """A member with no projects gets normal empty payloads without cache/provider IO."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="saved-empty@example.test",
        display_name="Saved Empty",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    db_session.add(user)
    db_session.commit()
    entry = SavedSearchService().create(
        owner_id=user.id,
        owner=user.display_name,
        name="No projects",
        query_text="must not reach providers",
        search_mode="semantic",
        filters={},
        top_k=5,
    )

    def _unexpected_singleton():
        raise AssertionError("empty authorization scope must avoid service singletons")

    monkeypatch.setattr(saved_router, "get_rag_service", _unexpected_singleton)
    monkeypatch.setattr(
        saved_router, "get_retrieval_service", _unexpected_singleton
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        response = TestClient(app).post(
            f"/api/v1/saved-searches/{entry.id}/execute"
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert response.status_code == 200, response.text
    assert response.json()["rag"]["sources"] == []
    assert response.json()["semantic"]["results"] == []


def test_saved_search_execution_passes_request_project_scope_to_both_services(
    monkeypatch, db_session
):
    """Saved execution binds RAG and semantic retrieval to the same live scope."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(),
        email="saved-scoped@example.test",
        display_name="Saved Scoped",
        password_hash="not-a-real-hash",  # noqa: S106
        role="member",
    )
    project = Project(id=uuid4(), name="Owned project", owner_id=user.id)
    db_session.add_all([user, project])
    db_session.commit()
    entry = SavedSearchService().create(
        owner_id=user.id,
        owner=user.display_name,
        name="Scoped execution",
        query_text="stay in scope",
        search_mode="semantic",
        filters={"project_id": str(project.id)},
        top_k=5,
    )

    fake_rag = _StubRagService()
    fake_retrieval = _StubRetrievalService()
    monkeypatch.setattr(saved_router, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        saved_router, "get_retrieval_service", lambda: fake_retrieval
    )
    caller = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role="member",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    try:
        response = TestClient(app).post(
            f"/api/v1/saved-searches/{entry.id}/execute"
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)

    assert response.status_code == 200, response.text
    assert fake_rag.calls[0]["allowed_project_ids"] == [project.id]
    assert fake_retrieval.calls[0]["allowed_project_ids"] == [project.id]
