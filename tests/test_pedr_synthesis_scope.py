"""PEDR-1B authorization boundaries for synthesis inputs and cache entries."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.api.v1.synthesize import get_synthesis_service_factory, synthesize
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    AuthenticatedUser,
    require_authenticated_user,
)
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.schemas.synthesis import SynthesizeRequest
from app.services import synthesis as synthesis_module
from app.services.synthesis import SynthesisService


def _principal(*, role: str = ROLE_MEMBER) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email=f"{role}@example.com",
        display_name=role,
        role=role,
    )


def _completion(content: str = "Authorized finding [1].") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = MagicMock(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    return response


def _service(*, cache_service=None, enable_cache: bool = True) -> tuple[SynthesisService, MagicMock]:
    client = MagicMock()
    client.chat.completions.create.return_value = _completion()
    service = SynthesisService(
        session_factory=SessionLocal,
        client=client,
        cache_service=cache_service,
        enable_cache=enable_cache,
        cost_monitor=MagicMock(),
    )
    return service, client


def _project(db, *, name: str) -> Project:
    project = Project(name=name)
    db.add(project)
    db.flush()
    return project


def _chunk(
    db,
    *,
    project_id: UUID,
    content: str,
    deleted: bool = False,
) -> DocumentChunk:
    document = Document(
        project_id=project_id,
        name=f"{content} document",
        deleted_at=datetime.utcnow() if deleted else None,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        content_tsv=text("''"),
    )
    db.add(chunk)
    db.flush()
    return chunk


class _RecordingService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "content": "Legacy result",
            "citations": [],
            "tokens_used": 0,
            "truncated": False,
            "chunk_count": 0,
            "cache_hit": False,
        }


class _ExplodingDB:
    def query(self, *_args, **_kwargs):
        raise AssertionError("unrestricted synthesis must not resolve a project scope")

    def get(self, *_args, **_kwargs):
        raise AssertionError("unrestricted synthesis must keep collection loading in the service")


@pytest.mark.parametrize(
    ("rbac_enabled", "role"),
    [(False, ROLE_MEMBER), (True, ROLE_ADMIN), (True, ROLE_OWNER)],
)
def test_unrestricted_route_preserves_legacy_service_call(
    monkeypatch, rbac_enabled: bool, role: str
):
    """Flag-off and privileged callers retain the exact pre-scope call shape."""
    monkeypatch.setattr(settings, "rbac_enabled", rbac_enabled)
    service = _RecordingService()
    collection_id = uuid4()

    response = synthesize(
        SynthesizeRequest(collection_id=collection_id, prompt="  Keep case  "),
        current_user=_principal(role=role),
        db=_ExplodingDB(),
        service_factory=lambda: service,
    )

    assert response.content == "Legacy result"
    assert service.calls == [
        {
            "collection_id": collection_id,
            "chunk_ids": None,
            "prompt": "  Keep case  ",
            "output_format": "markdown",
        }
    ]


class _RecordingCache:
    def __init__(self) -> None:
        self.get_calls: list[dict] = []
        self.set_calls: list[dict] = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return None

    def set(self, **kwargs):
        self.set_calls.append(kwargs)
        return "cache-id"


class _ExplodingSessionFactory:
    def __call__(self):
        raise AssertionError("an empty project scope must not query synthesis inputs")


def test_empty_scope_short_circuits_before_database_cache_and_llm():
    """No project grant yields the established empty 200 payload without side effects."""
    cache = _RecordingCache()
    client = MagicMock()
    service = SynthesisService(
        session_factory=_ExplodingSessionFactory(),
        client=client,
        cache_service=cache,
        cost_monitor=MagicMock(),
    )

    result = service.synthesize(
        chunk_ids=[uuid4()],
        accessible_project_ids=[],
    )

    assert result == {
        "content": "No content available for synthesis. The collection or chunks are empty.",
        "citations": [],
        "tokens_used": 0,
        "truncated": False,
        "chunk_count": 0,
        "cache_hit": False,
        "effective_chunk_ids": [],
    }
    assert cache.get_calls == []
    assert cache.set_calls == []
    client.chat.completions.create.assert_not_called()


def test_direct_chunk_scope_uses_one_authoritative_join_and_prunes_invalid_rows(
    db_session,
):
    """Only live chunks whose joined document belongs to an allowed project reach the LLM."""
    allowed_project = _project(db_session, name="Allowed")
    foreign_project = _project(db_session, name="Foreign")
    allowed = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="authorized source",
    )
    foreign = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign secret",
    )
    deleted = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="deleted secret",
        deleted=True,
    )
    db_session.commit()
    allowed_project_id = allowed_project.id
    requested_ids = [allowed.id, foreign.id, deleted.id, uuid4()]

    service, client = _service(enable_cache=False)
    select_statements: list[str] = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    try:
        result = service.synthesize(
            chunk_ids=requested_ids,
            accessible_project_ids=[allowed_project_id],
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert result["chunk_count"] == 1
    assert result["effective_chunk_ids"] == [str(allowed.id)]
    assert [citation["chunk_id"] for citation in result["citations"]] == [
        str(allowed.id)
    ]
    prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "authorized source" in prompt
    assert "foreign secret" not in prompt
    assert "deleted secret" not in prompt
    assert len(select_statements) == 1
    assert "JOIN documents" in select_statements[0]


def test_disjoint_direct_scope_returns_empty_without_cache_or_llm(db_session):
    """A non-empty but disjoint grant is just as fail-closed as an empty grant."""
    allowed_project = _project(db_session, name="Allowed")
    foreign_project = _project(db_session, name="Foreign")
    foreign = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign secret",
    )
    db_session.commit()
    cache = _RecordingCache()
    service, client = _service(cache_service=cache)

    result = service.synthesize(
        chunk_ids=[foreign.id],
        accessible_project_ids=[allowed_project.id],
    )

    assert result["chunk_count"] == 0
    assert result["effective_chunk_ids"] == []
    assert cache.get_calls == []
    assert cache.set_calls == []
    client.chat.completions.create.assert_not_called()


def test_disjoint_route_scope_prunes_before_openai_client_initialization(
    monkeypatch, db_session
):
    """A cold service can authorize by DB and return empty without a usable provider."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller = _principal()
    allowed_project = Project(name="Caller project", owner_id=caller.user_id)
    foreign_project = _project(db_session, name="Foreign")
    db_session.add(allowed_project)
    db_session.flush()
    foreign = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign secret",
    )
    db_session.commit()
    cache = _RecordingCache()
    service = SynthesisService(
        session_factory=SessionLocal,
        client=None,
        cache_service=cache,
        cost_monitor=MagicMock(),
    )
    monkeypatch.setattr(
        synthesis_module,
        "_openai_import_error",
        ModuleNotFoundError("provider deliberately unavailable"),
    )
    app.dependency_overrides[require_authenticated_user] = lambda: caller
    app.dependency_overrides[get_synthesis_service_factory] = lambda: lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/synthesize",
            json={"chunk_ids": [str(foreign.id)]},
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)
        app.dependency_overrides.pop(get_synthesis_service_factory, None)

    assert response.status_code == 200
    assert response.json()["chunk_count"] == 0
    assert response.json()["citations"] == []
    assert service.client is None
    assert cache.get_calls == []
    assert cache.set_calls == []


def test_collection_scope_filters_each_item_by_authoritative_document_project(
    db_session,
):
    """Owning a mixed collection never grants access to its foreign document chunks."""
    allowed_project = _project(db_session, name="Allowed")
    foreign_project = _project(db_session, name="Foreign")
    allowed = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="authorized collection source",
    )
    foreign = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign collection secret",
    )
    collection = Collection(name="Mixed")
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionItem(collection_id=collection.id, chunk_id=allowed.id),
            CollectionItem(collection_id=collection.id, chunk_id=foreign.id),
        ]
    )
    db_session.commit()

    service, client = _service(enable_cache=False)
    result = service.synthesize(
        collection_id=collection.id,
        accessible_project_ids=[allowed_project.id],
    )

    assert result["effective_chunk_ids"] == [str(allowed.id)]
    assert result["chunk_count"] == 1
    prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "authorized collection source" in prompt
    assert "foreign collection secret" not in prompt


def test_collection_is_authorized_before_scoped_synthesis(monkeypatch, db_session):
    """A caller cannot use synthesis to read a collection they cannot read per-id."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    collection = Collection(name="Foreign collection")
    db_session.add(collection)
    db_session.commit()
    user = _principal()
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_synthesis_service_factory] = lambda: (
        lambda: pytest.fail("denied collection constructed the synthesis service")
    )
    try:
        response = TestClient(app).post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id)},
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)
        app.dependency_overrides.pop(get_synthesis_service_factory, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have access to this resource."}


def test_missing_collection_is_404_before_scoped_synthesis(monkeypatch):
    """Scoped collection lookup follows the existing per-id 404 convention."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = _principal()
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_synthesis_service_factory] = lambda: (
        lambda: pytest.fail("missing collection constructed the synthesis service")
    )
    try:
        response = TestClient(app).post(
            "/api/v1/synthesize",
            json={"collection_id": str(uuid4())},
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)
        app.dependency_overrides.pop(get_synthesis_service_factory, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Collection not found."}


def test_empty_route_scope_does_not_construct_synthesis_service(monkeypatch):
    """FastAPI must resolve an empty scope before touching the OpenAI-backed singleton."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = _principal()
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_synthesis_service_factory] = lambda: (
        lambda: pytest.fail("empty scope constructed the synthesis service")
    )
    try:
        response = TestClient(app).post(
            "/api/v1/synthesize",
            json={"chunk_ids": [str(uuid4())]},
        )
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)
        app.dependency_overrides.pop(get_synthesis_service_factory, None)

    assert response.status_code == 200
    assert response.json()["chunk_count"] == 0
    assert response.json()["content"].startswith("No content available")


def test_scope_signature_is_canonical_and_isolates_cache_entries(monkeypatch):
    """Equivalent scopes share a key; different scopes cannot share cached synthesis."""
    cache = _RecordingCache()
    service, _client = _service(cache_service=cache)
    chunk_id = uuid4()
    project_a = uuid4()
    project_b = uuid4()
    chunk = {
        "chunk_id": str(chunk_id),
        "document_id": str(uuid4()),
        "document_name": "Source",
        "chunk_index": 0,
        "content": "Authorized source",
    }
    monkeypatch.setattr(service, "_fetch_chunks_by_ids", lambda *_args, **_kwargs: ([chunk], False))

    service.synthesize(
        chunk_ids=[chunk_id],
        accessible_project_ids=[project_b, project_a, project_a],
    )
    service.synthesize(
        chunk_ids=[chunk_id],
        accessible_project_ids=[project_a, project_b],
    )
    service.synthesize(
        chunk_ids=[chunk_id],
        accessible_project_ids=[project_a],
    )

    first_ids = cache.get_calls[0]["chunk_ids"]
    second_ids = cache.get_calls[1]["chunk_ids"]
    third_ids = cache.get_calls[2]["chunk_ids"]
    assert first_ids == second_ids
    assert first_ids != third_ids
    assert first_ids[0] == chunk_id
    assert len(first_ids) == 2


def test_none_scope_keeps_legacy_cache_identity(monkeypatch):
    """Unrestricted calls pass only the original effective IDs to cache unchanged."""
    cache = _RecordingCache()
    service, _client = _service(cache_service=cache)
    chunk_id = uuid4()
    chunk = {
        "chunk_id": str(chunk_id),
        "document_id": str(uuid4()),
        "document_name": "Source",
        "chunk_index": 0,
        "content": "Legacy source",
    }
    monkeypatch.setattr(service, "_fetch_chunks_by_ids", lambda *_args, **_kwargs: ([chunk], False))

    result = service.synthesize(chunk_ids=[chunk_id])

    assert cache.get_calls[0]["chunk_ids"] == [chunk_id]
    assert cache.set_calls[0]["chunk_ids"] == [chunk_id]
    assert "effective_chunk_ids" not in result
