"""MCP-6: corpus Q&A over the MCP, POST /api/v1/search/ask (tracelab_search ask).

An agent asks a question of one project's research and gets what the Librarian's
answer mode gives a person: an answer whose every citation opens a chunk the
model read, or an explicit nothing-found result. It goes through QA-1's one Q&A
service and nothing else (decision #543), and a caller never gets an answer from
a project they cannot read.

MCP Contract Guard: the npm client sends POST /api/v1/search/ask with an
X-API-Key, so these tests read that verb and path from the client source and
call the route with an X-API-Key, as TestMissionVerbContract does for missions.

DB-backed (not @pytest.mark.unit) so the autouse fixtures reset the database.
"""

from __future__ import annotations

import pathlib
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.v1.search as search_api
from app.core.config import settings
from app.core.security import (
    ROLE_MEMBER,
    ROLE_SERVICE,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.document import Document
from app.models.usage_record import USAGE_KIND_SEARCH_ASK, UsageRecord
from app.models.user import User
from app.services import corpus_qa

_HASH = "placeholder-not-a-real-hash"
_REPO = pathlib.Path(__file__).resolve().parents[1]
ASK_URL = "/api/v1/search/ask"
USAGE = {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}
REFUSAL = "Nothing in this project answers that question."


class _FakeRag:
    """Stands in for RagService.run_query and records what it was asked."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def run_query(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_parallel_path(monkeypatch):
    """The route must reach the pipeline only through corpus_qa.answer_question.

    A direct call would build the real RagService, whose shared cache is the Qdrant
    a local .env points at (learning #256), so it fails here instead.
    """

    def _refuse():
        raise AssertionError("POST /search/ask reached the RAG service outside corpus_qa.answer_question")

    monkeypatch.setattr(search_api, "get_rag_service", _refuse)


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _rag(monkeypatch, answer: str, sources: list[dict[str, Any]], *, no_evidence=False, cache_hit=False, attempts=None):
    fake = _FakeRag(
        {
            "answer": answer,
            "citations": [],
            "sources": sources,
            "cache": {"hit": cache_hit},
            "routing": {
                "selected_model": "gpt-test",
                "attempts": attempts if attempts is not None else [{"model": "gpt-test", "usage": USAGE}],
            },
            "no_evidence": no_evidence,
        }
    )
    monkeypatch.setattr(corpus_qa, "get_rag_service", lambda: fake)
    return fake


def _user(db, name, role=ROLE_MEMBER) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        display_name=name,
        password_hash=_HASH,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _api_key(db, user) -> dict[str, str]:
    """The MCP's credential: a user API key sent as X-API-Key."""
    plain = generate_api_key()
    db.add(APIKey(user_id=user.id, name="MCP", key_hash=hash_api_key(plain), key_prefix=get_key_prefix(plain)))
    db.commit()
    return {"X-API-Key": plain}


def _chunk(db, project, index=9) -> tuple[Document, dict[str, Any]]:
    document = Document(project_id=project.id, name="qdrant-on-railway.md", mime_type="text/markdown")
    db.add(document)
    db.commit()
    db.refresh(document)
    source = {
        "chunk_id": str(uuid.uuid4()),
        "content": "The Hobby plan bill is approximately $48-$63 a month.",
        "document_id": str(document.id),
        "project_id": str(project.id),
        "chunk_index": index,
        "similarity": 0.63,
    }
    return document, source


def _label(source: dict[str, Any]) -> str:
    return f"[Document: {source['document_id']}, Chunk: {source['chunk_index']}]"


def _ask(client, project_id, headers, question="What does it cost?", **extra):
    return client.post(ASK_URL, json={"project_id": str(project_id), "question": question, **extra}, headers=headers)


def _owned(db, project) -> tuple[User, dict[str, str]]:
    owner = _user(db, "Project owner")
    project.owner_id = owner.id
    db.commit()
    return owner, _api_key(db, owner)


class TestMcpContract:
    """The verb and path the npm client sends are the ones the server serves."""

    def test_the_npm_client_asks_through_post_search_ask(self):
        client_ts = _REPO / "packages" / "tracelab-mcp" / "src" / "api-client.ts"
        index_ts = _REPO / "packages" / "tracelab-mcp" / "src" / "index.ts"
        if not client_ts.exists():
            pytest.skip("npm MCP client source not present in this checkout")
        assert "this.request<AskResponse>('POST', '/api/v1/search/ask', query)" in client_ts.read_text()
        source = index_ts.read_text()
        handler = source.split("async function handleSearchAsk", 1)[1].split("\n}\n", 1)[0]
        assert "client.askQuestion(" in handler
        dispatcher = source.split("export async function handleTracelabSearch", 1)[1].split("\n}\n", 1)[0]
        assert "case 'ask':\n      return await handleSearchAsk(args);" in dispatcher

    def test_verb_contract(self, client):
        assert client.get(ASK_URL).status_code == 405
        response = client.post(ASK_URL, json={"project_id": str(uuid.uuid4()), "question": "What does it cost?"})
        assert response.status_code == 401


@pytest.mark.usefixtures("rbac_on")
class TestAccess:
    """The caller's own scope, exactly as the Librarian's answer mode applies it."""

    def test_a_caller_cannot_get_an_answer_from_a_project_they_cannot_read(
        self, client, monkeypatch, db_session, project
    ):
        _owned(db_session, project)
        _, source = _chunk(db_session, project)
        rag = _rag(monkeypatch, f"The bill is $48-$63 a month. {_label(source)}", [source])
        stranger = _api_key(db_session, _user(db_session, "Stranger"))

        response = _ask(client, project.id, stranger)

        assert response.status_code == 403, response.text
        assert rag.calls == [], "retrieval never runs for a project outside the caller's scope"
        assert "48" not in response.text

    def test_the_projects_owner_gets_an_answer_whose_citations_resolve(self, client, monkeypatch, db_session, project):
        _, headers = _owned(db_session, project)
        document, source = _chunk(db_session, project)
        fabricated = f"[Document: {uuid.uuid4()}, Chunk: 3]"
        rag = _rag(
            monkeypatch,
            f"The bill is **$48–$63** a month. {_label(source)}\n\nManaged hosting costs more. {fabricated}",
            [source],
        )

        response = _ask(client, project.id, headers, "  What does self-hosting Qdrant cost?  ", max_tokens=2000)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["no_evidence"] is False
        assert body["passages"] == [
            {"text": "The bill is **$48–$63** a month.", "citations": [source["chunk_id"]]},
            # A label naming no chunk the model read is dropped, never shown as a citation.
            {"text": "Managed hosting costs more.", "citations": []},
        ]
        assert body["answer"] == "The bill is **$48–$63** a month.\n\nManaged hosting costs more."
        assert body["citations"] == [
            {
                "chunk_id": source["chunk_id"],
                "document_id": str(document.id),
                "document_name": "qdrant-on-railway.md",
                "chunk_index": 9,
                "snippet": source["content"],
                "href": f"/documents/{document.id}?chunk={source['chunk_id']}&index=9",
            }
        ]
        assert body["model"] == "gpt-test"
        assert rag.calls == [
            {
                "query": "What does self-hosting Qdrant cost?",
                "top_k": 5,
                "project_id": str(project.id),
                "max_tokens": 2000,
                "refuse_unsupported": True,
                "allowed_project_ids": [project.id],
            }
        ]

    def test_a_service_principal_is_refused(self, client, monkeypatch, db_session, project):
        rag = _rag(monkeypatch, "The bill is $48.", [])
        service = _api_key(db_session, _user(db_session, "DeepSearch", role=ROLE_SERVICE))

        response = _ask(client, project.id, service)

        assert response.status_code == 403, response.text
        assert rag.calls == []

    def test_an_unknown_or_deleted_project_is_404(self, client, monkeypatch, db_session, project):
        _, headers = _owned(db_session, project)
        rag = _rag(monkeypatch, "The bill is $48.", [])
        assert _ask(client, uuid.uuid4(), headers).status_code == 404
        project.soft_delete(deleted_by="test")
        db_session.commit()
        assert _ask(client, project.id, headers).status_code == 404
        assert rag.calls == []


class TestAnswer:
    def test_nothing_found_is_the_refusal_and_asserts_nothing(self, client, monkeypatch, db_session, project):
        _, headers = _owned(db_session, project)
        rag = _rag(monkeypatch, REFUSAL, [], no_evidence=True, attempts=[])

        response = _ask(client, project.id, headers, "How does Kubernetes autoscale pods?")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["no_evidence"] is True
        assert body["answer"] == REFUSAL
        assert body["passages"] == [{"text": REFUSAL, "citations": []}]
        assert body["citations"] == []
        # Omitted, the budget is the server's default: the service receives None.
        assert rag.calls[0]["max_tokens"] is None
        assert db_session.query(UsageRecord).filter(UsageRecord.project_id == project.id).count() == 0

    def test_an_answer_that_cites_nothing_is_refused_not_shown(self, client, monkeypatch, db_session, project):
        _, headers = _owned(db_session, project)
        _, source = _chunk(db_session, project)
        _rag(monkeypatch, "Kubernetes scales pods on CPU by default.", [source])

        body = _ask(client, project.id, headers, "Autoscaling?").json()

        assert body["no_evidence"] is True
        assert body["answer"] == REFUSAL
        assert body["citations"] == []
        assert "Kubernetes" not in str(body)

    def test_request_rules(self, client, monkeypatch, db_session, project):
        _, headers = _owned(db_session, project)
        rag = _rag(monkeypatch, "The bill is $48.", [])
        cases = [
            {"question": "What does it cost?"},
            {"project_id": "not-a-uuid", "question": "What does it cost?"},
            {"project_id": str(project.id)},
            {"project_id": str(project.id), "question": "   "},
            {"project_id": str(project.id), "question": "x" * 20_001},
            {"project_id": str(project.id), "question": "Cost?", "max_tokens": 63},
            {"project_id": str(project.id), "question": "Cost?", "max_tokens": 4001},
            {"project_id": str(project.id), "question": "Cost?", "max_tokens": 600.5},
        ]
        for payload in cases:
            response = client.post(ASK_URL, json=payload, headers=headers)
            assert response.status_code == 422, (payload, response.text)
        assert rag.calls == []

    def test_each_paid_call_is_metered_to_the_caller_and_a_cached_answer_is_not(
        self, client, monkeypatch, db_session, project
    ):
        owner, headers = _owned(db_session, project)
        _, source = _chunk(db_session, project)
        answer = f"The bill is $48. {_label(source)}"
        escalated = [
            {"model": "gpt-5.1", "usage": USAGE},
            {"model": "gpt-5.2", "usage": {"prompt_tokens": 950, "completion_tokens": 140, "total_tokens": 1090}},
        ]
        _rag(monkeypatch, answer, [source], attempts=escalated)

        assert _ask(client, project.id, headers).status_code == 200

        rows = db_session.query(UsageRecord).filter(UsageRecord.project_id == project.id).all()
        # The literal kind, so asks stay apart from the Librarian's librarian_turn rows in any usage query.
        assert USAGE_KIND_SEARCH_ASK == "search_ask"
        assert sorted((row.kind, row.user_id, row.model, row.total_tokens, row.requests) for row in rows) == [
            ("search_ask", owner.id, "gpt-5.1", 1020, 1),
            ("search_ask", owner.id, "gpt-5.2", 1090, 1),
        ]

        _rag(monkeypatch, answer, [source], cache_hit=True, attempts=escalated)
        assert _ask(client, project.id, headers).status_code == 200
        assert db_session.query(UsageRecord).filter(UsageRecord.project_id == project.id).count() == 2
