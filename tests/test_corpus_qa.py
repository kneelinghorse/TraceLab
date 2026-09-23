"""QA-1: the corpus Q&A service, the one path from a question to a cited answer.

Rule 2 of the Librarian roadmap: a claim about the corpus carries a citation that
resolves, or it is not made. These tests hold the service to that: every citation
it returns names a chunk the model read, in a document that still exists and
opens at /documents/{id}; an answer that cites nothing is refused, never shown;
and a caller gets nothing from a project they cannot read, exactly as POST
/search gives them nothing.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

import app.core.authorization as authorization
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.document import Document
from app.services import corpus_qa
from app.services import rag_service as rag_module
from app.services.corpus_qa import answer_question
from app.services.pedr.search_orchestrator import (
    LayerTimings,
    PEDRMetadata,
    PEDRSearchResponse,
    PEDRSearchResult,
)

READER = AuthenticatedUser(user_id=uuid.uuid4(), email="reader@tracelab.local", display_name="r", role="owner")
USAGE = {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}


class _FakeRag:
    """Stands in for RagService.run_query and records what it was asked."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def run_query(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _document(db, project, name="qdrant-on-railway.md") -> Document:
    document = Document(project_id=project.id, name=name, mime_type="text/markdown")
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _source(document: Document, index: int, similarity: float = 0.63) -> dict[str, Any]:
    return {
        "chunk_id": str(uuid.uuid4()),
        "content": f"Chunk {index} of {document.name}: the Hobby plan costs $48-$63 a month.",
        "document_id": str(document.id),
        "project_id": str(document.project_id),
        "chunk_index": index,
        "score": 0.03,
        "similarity": similarity,
    }


def _label(source: dict[str, Any]) -> str:
    return f"[Document: {source['document_id']}, Chunk: {source['chunk_index']}]"


def _result(answer: str, sources: list[dict[str, Any]], *, cache_hit: bool = False) -> dict[str, Any]:
    return {
        "answer": answer,
        "citations": [],
        "sources": sources,
        "cache": {"hit": cache_hit},
        "routing": {"selected_model": "gpt-test", "attempts": [{"model": "gpt-test", "usage": USAGE}]},
        "no_evidence": False,
    }


def _install(monkeypatch, result: dict[str, Any]) -> _FakeRag:
    fake = _FakeRag(result)
    monkeypatch.setattr(corpus_qa, "get_rag_service", lambda: fake)
    return fake


def test_each_passage_cites_only_chunks_the_model_read(monkeypatch, db_session, project):
    document = _document(db_session, project)
    first, second = _source(document, 8), _source(document, 9)
    fabricated = f"[Document: {uuid.uuid4()}, Chunk: 3]"
    answer = (
        f"The report estimates **$48–$63** a month on the Hobby plan. {_label(first)} {_label(second)}\n\n"
        "Managed hosting usually costs more.\n\n"
        f"Budgets doubled last year. {fabricated}"
    )
    fake = _install(monkeypatch, _result(answer, [first, second]))

    result = answer_question(db_session, READER, project.id, "  What does self-hosting Qdrant cost?  ", max_tokens=600)

    assert [passage.text for passage in result.passages] == [
        "The report estimates **$48–$63** a month on the Hobby plan.",
        "Managed hosting usually costs more.",
        "Budgets doubled last year.",
    ]
    assert result.passages[0].citations == [first["chunk_id"], second["chunk_id"]]
    # Uncited, and a label that names no retrieved chunk is dropped: neither passage cites.
    assert result.passages[1].citations == []
    assert result.passages[2].citations == []
    assert result.no_evidence is False
    assert [citation.chunk_id for citation in result.citations] == [first["chunk_id"], second["chunk_id"]]
    citation = result.citations[0]
    assert citation.document_id == str(document.id)
    assert citation.document_name == "qdrant-on-railway.md"
    assert citation.chunk_index == 8
    assert citation.href == f"/documents/{document.id}?chunk={first['chunk_id']}&index=8"
    assert citation.snippet.startswith("Chunk 8 of qdrant-on-railway.md")
    assert set(result.source_chunk_ids) == {first["chunk_id"], second["chunk_id"]}
    assert result.usage == [("gpt-test", USAGE)]
    assert fake.calls == [
        {
            "query": "What does self-hosting Qdrant cost?",
            "top_k": 5,
            "project_id": str(project.id),
            "max_tokens": 600,
            "refuse_unsupported": True,
        }
    ]


def test_a_paragraph_of_labels_lends_them_to_the_paragraph_before_it(monkeypatch, db_session, project):
    """Otherwise the fact above them reads as uncited and a supported answer is refused."""
    document = _document(db_session, project)
    source = _source(document, 14)
    _install(monkeypatch, _result(f"92% of 32-token inputs were recovered.\n\n{_label(source)}", [source]))

    result = answer_question(db_session, READER, project.id, "How much short text was recovered?")

    assert [(passage.text, passage.citations) for passage in result.passages] == [
        ("92% of 32-token inputs were recovered.", [source["chunk_id"]])
    ]
    assert result.no_evidence is False


def test_a_label_naming_several_chunks_cites_each_and_leaves_no_raw_text(monkeypatch, db_session, project):
    """Production, QA-1 acceptance: a synthesis closed with "[Document: <id>, Chunks: 9–10]",
    which the pipeline's pattern does not read, so the label showed as raw text."""
    document = _document(db_session, project)
    ninth, tenth, twelfth = _source(document, 9), _source(document, 10), _source(document, 12)
    answer = (
        f"It recommends a hybrid, project-bounded model. [Document: {document.id}, Chunks: 9–10]\n\n"
        f"Option 4 adds an admin warning gate. [Document: {document.id}, Chunk: 10, 12]"
    )
    _install(monkeypatch, _result(answer, [ninth, tenth, twelfth]))

    result = answer_question(db_session, READER, project.id, "Which option does the research recommend?")

    assert [(passage.text, passage.citations) for passage in result.passages] == [
        ("It recommends a hybrid, project-bounded model.", [ninth["chunk_id"], tenth["chunk_id"]]),
        ("Option 4 adds an admin warning gate.", [tenth["chunk_id"], twelfth["chunk_id"]]),
    ]
    assert "Document:" not in result.answer


def test_an_answer_that_cites_nothing_is_refused_not_shown(monkeypatch, db_session, project):
    """The model read chunks at the floor and cited none: nothing the user could open backs it."""
    document = _document(db_session, project)
    _install(
        monkeypatch,
        _result("Kubernetes scales pods on CPU by default.", [_source(document, 2, similarity=0.41)]),
    )

    result = answer_question(db_session, READER, project.id, "How does pod autoscaling work?")

    assert result.no_evidence is True
    assert result.answer == "Nothing in this project answers that question."
    assert [passage.citations for passage in result.passages] == [[]]
    assert result.citations == []
    assert "Kubernetes" not in result.answer
    # The model was still paid for, so the caller can meter it.
    assert result.usage == [("gpt-test", USAGE)]


def test_the_pipelines_nothing_found_result_is_the_refusal(monkeypatch, db_session, project):
    fake = _install(
        monkeypatch,
        {
            "answer": "Nothing in this project answers that question.",
            "citations": [],
            "sources": [],
            "cache": {"hit": False},
            "routing": {"selected_model": "gpt-test", "attempts": []},
            "no_evidence": True,
        },
    )

    result = answer_question(db_session, READER, project.id, "What is sourdough?", max_tokens=2000)

    assert result.no_evidence is True
    assert result.answer == "Nothing in this project answers that question."
    assert result.citations == []
    assert result.usage == []
    assert fake.calls[0]["refuse_unsupported"] is True
    assert fake.calls[0]["max_tokens"] == 2000


def test_a_citation_into_a_deleted_document_is_dropped(monkeypatch, db_session, project):
    """Its link would open nothing, so it is not a citation; with nothing else cited, the answer is refused."""
    document = _document(db_session, project)
    source = _source(document, 1)
    document.soft_delete(deleted_by="test")
    db_session.commit()
    _install(monkeypatch, _result(f"The cost is $48. {_label(source)}", [source]))

    result = answer_question(db_session, READER, project.id, "What is the cost?")

    assert result.citations == []
    assert result.no_evidence is True


def test_an_answer_from_a_cache_reports_no_paid_usage(monkeypatch, db_session, project):
    document = _document(db_session, project)
    source = _source(document, 1)
    _install(monkeypatch, _result(f"The cost is $48. {_label(source)}", [source], cache_hit=True))

    result = answer_question(db_session, READER, project.id, "What is the cost?")

    assert result.no_evidence is False
    assert result.usage == []


def test_a_blank_question_is_rejected(monkeypatch, db_session, project):
    fake = _install(monkeypatch, _result("", []))
    with pytest.raises(ValueError):
        answer_question(db_session, READER, project.id, "   ")
    assert fake.calls == []


class TestScope:
    """The search route's scope rule, applied to the one Q&A path."""

    @pytest.fixture(autouse=True)
    def _rbac_on(self, monkeypatch):
        monkeypatch.setattr(authorization.settings, "rbac_enabled", True, raising=False)

    def test_a_member_cannot_get_an_answer_from_a_project_they_cannot_read(self, monkeypatch, db_session, project):
        document = _document(db_session, project)
        source = _source(document, 1)
        fake = _install(monkeypatch, _result(f"The cost is $48. {_label(source)}", [source]))
        stranger = AuthenticatedUser(user_id=uuid.uuid4(), email="guest@tracelab.local", display_name="g", role="member")

        result = answer_question(db_session, stranger, project.id, "What is the cost?")

        assert fake.calls == [], "the pipeline is never asked for a project outside the caller's scope"
        assert result.no_evidence is True
        assert result.citations == []
        assert result.answer == "No accessible sources were found for this query."

    def test_a_member_who_can_read_the_project_is_answered_within_their_scope(self, monkeypatch, db_session, project):
        owner = AuthenticatedUser(user_id=uuid.uuid4(), email="member@tracelab.local", display_name="m", role="member")
        project.owner_id = owner.user_id
        db_session.commit()
        document = _document(db_session, project)
        source = _source(document, 1)
        fake = _install(monkeypatch, _result(f"The cost is $48. {_label(source)}", [source]))

        result = answer_question(db_session, owner, project.id, "What is the cost?")

        assert result.no_evidence is False
        assert fake.calls[0]["allowed_project_ids"] == [project.id]


# ---------------------------------------------------------------- through the real pipeline


class _FakePEDR:
    def __init__(self, results: list[dict[str, Any]]):
        self.results = results

    def search(self, **kwargs) -> PEDRSearchResponse:
        results = [PEDRSearchResult(**result) for result in self.results]
        metadata = PEDRMetadata(
            query=kwargs.get("query", ""),
            intent="factual",
            intent_confidence=0.9,
            detected_type=None,
            type_confidence=0.0,
            layers_used=["semantic"],
            layer_weights={"semantic": 0.35},
            timings=LayerTimings(total_ms=5.0),
            total_candidates=len(results),
            result_count=len(results),
            cache_hit=False,
        )
        return PEDRSearchResponse(results=results, metadata=metadata)


class _FakeOpenAI:
    def __init__(self, content: str):
        self.requests: list[dict[str, Any]] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.requests.append(kwargs)
                message = type("Message", (), {"content": content})
                choice = type("Choice", (), {"message": message})
                usage = type("Usage", (), {"prompt_tokens": 800, "completion_tokens": 90, "total_tokens": 890})
                return type("Response", (), {"choices": [choice], "usage": usage})

        self.chat = type("Chat", (), {"completions": _Completions()})()


class _Embedding:
    def generate_embedding(self, text):
        return [1.0, 0.0, 0.0]


class _NoCache:
    """RagService reads cache_service=None as "use the shared Qdrant cache", which a
    local .env points at a real Qdrant; a test must never reach it."""

    def check_cache(self, **_kwargs):
        return None

    def store_in_cache(self, **_kwargs):
        return None


def _pipeline(monkeypatch, results, content) -> _FakeOpenAI:
    client = _FakeOpenAI(content)
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    monkeypatch.setattr(rag_module, "OpenAI", object, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=_FakePEDR(results),
        embedding_service=_Embedding(),
        cache_service=_NoCache(),
        client=client,
        model="gpt-test",
        default_temperature=0.0,
        cost_monitor=None,
    )
    monkeypatch.setattr(corpus_qa, "get_rag_service", lambda: service)
    return client


def _pedr_result(document: Document, index: int, embedding: list[float]) -> dict[str, Any]:
    return {
        "chunk_id": str(uuid.uuid4()),
        "content": f"Chunk {index}: the Hobby plan bill is $48-$63 a month.",
        "document_id": str(document.id),
        "project_id": str(document.project_id),
        "chunk_index": index,
        "rrf_score": 0.03,
        "embedding": embedding,
    }


def test_through_the_pipeline_a_supported_question_is_answered_with_resolving_citations(
    monkeypatch, db_session, project
):
    document = _document(db_session, project)
    answering = _pedr_result(document, 8, [0.63, 0.78, 0.0])  # cosine 0.63, production's answering range
    client = _pipeline(monkeypatch, [answering], f"The bill is $48-$63 a month. [Document: {document.id}, Chunk: 8]")

    result = answer_question(db_session, READER, project.id, "What is the monthly bill?", max_tokens=600)

    assert result.no_evidence is False
    assert [citation.chunk_id for citation in result.citations] == [answering["chunk_id"]]
    assert result.citations[0].href == f"/documents/{document.id}?chunk={answering['chunk_id']}&index=8"
    request = client.requests[0]
    assert request["max_tokens"] == 600
    assert "within about 150 words" in request["messages"][1]["content"]


def test_through_the_pipeline_an_unsupported_question_is_refused_before_the_model(monkeypatch, db_session, project):
    """RAG-4 measured an unsupported in-domain question at 0.374, below the 0.4 floor."""
    document = _document(db_session, project)
    nearest = _pedr_result(document, 3, [0.374, 0.927, 0.0])
    client = _pipeline(monkeypatch, [nearest], f"Pods scale on CPU. [Document: {document.id}, Chunk: 3]")

    result = answer_question(db_session, READER, project.id, "How does Kubernetes autoscale pods?")

    assert settings.rag_context_threshold == pytest.approx(0.4)
    assert client.requests == [], "the model is never asked"
    assert result.no_evidence is True
    assert result.answer == "Nothing in this project answers that question."
    assert result.usage == []
