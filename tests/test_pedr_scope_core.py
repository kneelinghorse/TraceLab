"""Core project-scope tests for relational and Qdrant retrieval boundaries."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from qdrant_client.models import MatchAny, MatchValue

from app.api.v1 import retrieval as retrieval_router
from app.core.authorization import accessible_project_ids
from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    AuthenticatedUser,
)
from app.main import app
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.services import retrieval_service as retrieval_module
from app.services.qdrant_service import QdrantService

_PASSWORD_HASH = "not-a-real-password-hash"  # noqa: S105


def _principal(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _user(db, *, email: str, role: str = ROLE_MEMBER) -> User:
    user = User(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
        password_hash=_PASSWORD_HASH,
        role=role,
    )
    db.add(user)
    db.flush()
    return user


class _ExplodingDB:
    def query(self, *_args, **_kwargs):
        raise AssertionError("unrestricted/service scope must not query the database")


@pytest.mark.parametrize("role", [ROLE_OWNER, ROLE_ADMIN])
def test_accessible_project_ids_privileged_scope_is_unrestricted(monkeypatch, role):
    """Owner/admin access remains unrestricted without touching relational scope."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    principal = AuthenticatedUser(uuid4(), "p@example.com", "p", role)

    assert accessible_project_ids(principal, _ExplodingDB()) is None


def test_accessible_project_ids_rbac_off_is_byte_identical(monkeypatch):
    """The feature flag's OFF state emits no project restriction for any role."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    principal = AuthenticatedUser(
        uuid4(), "service@example.com", "service", ROLE_SERVICE
    )

    assert accessible_project_ids(principal, _ExplodingDB()) is None


def test_accessible_project_ids_combines_ownership_and_space_membership(
    monkeypatch, db_session
):
    """A human caller can search owned projects and projects shared through Space."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller = _user(db_session, email="caller@example.com")
    outsider = _user(db_session, email="outsider@example.com")
    shared_space = Workspace(name="Caller Space")
    foreign_space = Workspace(name="Foreign Space")
    db_session.add_all([shared_space, foreign_space])
    db_session.flush()
    db_session.add(
        SpaceMember(workspace_id=shared_space.id, user_id=caller.id, role=ROLE_MEMBER)
    )
    owned = Project(name="Owned without Space", owner_id=caller.id)
    shared = Project(name="Shared through Space", workspace_id=shared_space.id)
    foreign = Project(
        name="Foreign", owner_id=outsider.id, workspace_id=foreign_space.id
    )
    db_session.add_all([owned, shared, foreign])
    db_session.commit()

    result = accessible_project_ids(_principal(caller), db_session)

    assert result is not None
    assert set(result) == {owned.id, shared.id}
    assert foreign.id not in result


def test_accessible_project_ids_service_and_ungranted_callers_fail_closed(
    monkeypatch, db_session
):
    """Machine identities and humans with no grant receive an explicit empty scope."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    service = _user(db_session, email="service@example.com", role=ROLE_SERVICE)
    ungranted = _user(db_session, email="ungranted@example.com")
    db_session.add(Project(name="Service-owned anomaly", owner_id=service.id))
    db_session.commit()

    assert accessible_project_ids(_principal(service), db_session) == []
    assert accessible_project_ids(_principal(ungranted), db_session) == []


class _RecordingQdrantClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return []


def _qdrant_service(client: _RecordingQdrantClient) -> QdrantService:
    return QdrantService(client=client, collection_name="test", vector_size=3)


def test_qdrant_none_scope_preserves_legacy_filters():
    """None retains the pre-scope MatchValue behavior and unfiltered query shape."""
    project_id = uuid4()
    filtered_client = _RecordingQdrantClient()
    _qdrant_service(filtered_client).search_chunks(
        query_vector=[0.1, 0.2, 0.3],
        project_id=str(project_id),
        allowed_project_ids=None,
    )

    condition = filtered_client.calls[0]["query_filter"].must[0]
    assert isinstance(condition.match, MatchValue)
    assert condition.match.value == str(project_id)

    unfiltered_client = _RecordingQdrantClient()
    _qdrant_service(unfiltered_client).search_chunks(
        query_vector=[0.1, 0.2, 0.3], allowed_project_ids=None
    )
    assert unfiltered_client.calls[0]["query_filter"] is None


def test_qdrant_allowed_scope_uses_match_any_and_intersects_explicit_project():
    """A requested project narrows, rather than replaces, the caller's allow-list."""
    allowed, other, document_id = uuid4(), uuid4(), uuid4()
    all_allowed_client = _RecordingQdrantClient()
    _qdrant_service(all_allowed_client).search_chunks(
        query_vector=[0.1, 0.2, 0.3],
        allowed_project_ids=[allowed, other],
    )
    all_allowed_match = all_allowed_client.calls[0]["query_filter"].must[0].match
    assert isinstance(all_allowed_match, MatchAny)
    assert all_allowed_match.any == [str(allowed), str(other)]

    client = _RecordingQdrantClient()
    _qdrant_service(client).search_chunks(
        query_vector=[0.1, 0.2, 0.3],
        project_id=str(other),
        document_id=str(document_id),
        source_type="report",
        allowed_project_ids=[allowed, other],
    )

    conditions = client.calls[0]["query_filter"].must
    assert isinstance(conditions[0].match, MatchAny)
    assert conditions[0].match.any == [str(other)]
    assert isinstance(conditions[1].match, MatchValue)
    assert conditions[1].match.value == str(document_id)
    assert isinstance(conditions[2].match, MatchValue)
    assert conditions[2].match.value == "report"


@pytest.mark.parametrize(
    ("allowed_project_ids", "project_id"),
    [([], None), ([uuid4()], str(uuid4()))],
)
def test_qdrant_empty_or_disjoint_scope_never_calls_live_client(
    allowed_project_ids: list[UUID], project_id: str | None
):
    """Empty scopes and explicit cross-scope filters fail closed before Qdrant."""
    client = _RecordingQdrantClient()

    results = _qdrant_service(client).search_chunks(
        query_vector=[0.1, 0.2, 0.3],
        project_id=project_id,
        allowed_project_ids=allowed_project_ids,
    )

    assert results == []
    assert client.calls == []


class _FailIfEmbedded:
    def generate_embedding(self, _query):
        raise AssertionError("a denied scope must not generate an embedding")


class _FailIfSearched:
    def search_chunks(self, **_kwargs):
        raise AssertionError("a denied scope must not reach Qdrant")


class _StaticEmbedding:
    def generate_embedding(self, _query):
        return [0.1, 0.2, 0.3]


class _ScopeIgnoringQdrant:
    def __init__(self, results):
        self.results = results

    def search_chunks(self, **_kwargs):
        return list(self.results)


class _PassThroughFacets:
    def filter_chunks(self, chunks, _filters):
        return list(chunks)


def test_retrieval_service_fails_closed_before_embedding(monkeypatch):
    """The service short-circuits a disjoint explicit project before external I/O."""
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: _FailIfEmbedded()
    )
    monkeypatch.setattr(
        retrieval_module, "get_qdrant_service", lambda: _FailIfSearched()
    )
    service = retrieval_module.RetrievalService(faceted_service=_PassThroughFacets())

    result = service.search(
        query="private material",
        project_id=str(uuid4()),
        allowed_project_ids=[uuid4()],
    )

    assert result == []


def test_retrieval_service_post_filters_backend_scope_violations(monkeypatch):
    """Backend rows that omit or violate project scope are dropped fail-closed."""
    allowed_project_id = uuid4()
    rows = [
        {"chunk_id": "allowed", "project_id": str(allowed_project_id)},
        {"chunk_id": "foreign", "project_id": str(uuid4())},
        {"chunk_id": "missing"},
        {"chunk_id": "malformed", "project_id": "not-a-project-id"},
    ]
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: _StaticEmbedding()
    )
    monkeypatch.setattr(
        retrieval_module,
        "get_qdrant_service",
        lambda: _ScopeIgnoringQdrant(rows),
    )
    service = retrieval_module.RetrievalService(faceted_service=_PassThroughFacets())

    results = service.search(
        query="scope must be enforced twice",
        allowed_project_ids=[allowed_project_id],
    )

    assert results == [rows[0]]
    assert service.search(query="legacy unrestricted", allowed_project_ids=None) == rows


def test_retrieval_service_post_filter_intersects_explicit_project_and_document(
    monkeypatch,
):
    """Backend rows must satisfy both caller filters even inside an allowed Space."""
    requested_project_id, other_allowed_project_id = uuid4(), uuid4()
    requested_document_id, other_document_id = uuid4(), uuid4()
    rows = [
        {
            "chunk_id": "expected",
            "project_id": str(requested_project_id),
            "document_id": str(requested_document_id),
        },
        {
            "chunk_id": "wrong-allowed-project",
            "project_id": str(other_allowed_project_id),
            "document_id": str(requested_document_id),
        },
        {
            "chunk_id": "wrong-document",
            "project_id": str(requested_project_id),
            "document_id": str(other_document_id),
        },
        {
            "chunk_id": "missing-document",
            "project_id": str(requested_project_id),
        },
        {
            "chunk_id": "malformed-document",
            "project_id": str(requested_project_id),
            "document_id": "not-a-document-id",
        },
    ]
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: _StaticEmbedding()
    )
    monkeypatch.setattr(
        retrieval_module,
        "get_qdrant_service",
        lambda: _ScopeIgnoringQdrant(rows),
    )
    service = retrieval_module.RetrievalService(faceted_service=_PassThroughFacets())

    results = service.search(
        query="apply every explicit boundary",
        project_id=str(requested_project_id),
        document_id=str(requested_document_id),
        allowed_project_ids=[requested_project_id, other_allowed_project_id],
    )

    assert results == [rows[0]]


def test_retrieval_route_computes_scope_once_and_disjoint_filter_returns_200(
    monkeypatch, auth_headers
):
    """The HTTP route resolves one request scope and returns an empty safe response."""
    allowed_project_id = uuid4()
    requested_project_id = uuid4()
    scope_calls: list[tuple[AuthenticatedUser, object]] = []

    def _scope(user, db):
        scope_calls.append((user, db))
        return [allowed_project_id]

    monkeypatch.setattr(retrieval_router, "accessible_project_ids", _scope)
    monkeypatch.setattr(
        retrieval_module, "get_embedding_service", lambda: _FailIfEmbedded()
    )
    monkeypatch.setattr(
        retrieval_module, "get_qdrant_service", lambda: _FailIfSearched()
    )
    service = retrieval_module.RetrievalService(faceted_service=_PassThroughFacets())
    monkeypatch.setattr(retrieval_router, "get_retrieval_service", lambda: service)

    response = TestClient(app).post(
        "/api/v1/retrieval/search",
        headers=auth_headers,
        json={
            "query": "cross-project request",
            "project_id": str(requested_project_id),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}
    assert len(scope_calls) == 1
    assert isinstance(scope_calls[0][0], AuthenticatedUser)
