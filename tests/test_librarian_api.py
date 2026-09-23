"""LIB-1: the Librarian's three routes, driven end to end against a scripted model.

Covers the criteria that need a database: citations resolving to real evidence
entries the tool returned, the repair-then-withhold path, the same authorize()
path as the user (criterion 7), the compiled-and-linted draft, and creation that
is explicit, marked as Librarian-authored, and idempotent.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.v1.librarian as librarian_api
import app.core.authorization as authorization
import app.services.corpus_qa as corpus_qa
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.main import app
from app.models.document import Document
from app.models.user import User
from app.schemas.evidence_ledger import CaptureItem, CaptureRequest
from app.services.evidence_ledger import EvidenceLedgerService
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply, ModelToolCall


class ScriptedModel:
    """Returns pre-scripted replies in order and records every request it saw."""

    model_name = "fake-librarian"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, messages, *, tools=None, json_mode=False, max_tokens=1500):
        self.calls.append({"messages": list(messages), "tools": tools, "json_mode": json_mode})
        if not self.replies:
            raise AssertionError("The scripted model ran out of replies.")
        return self.replies.pop(0)


def _usage(prompt=10, completion=5):
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


def _json_reply(segments, suggested_action=None):
    return ModelReply(
        content=json.dumps({"segments": segments, "suggested_action": suggested_action}),
        usage=_usage(),
    )


def _tool_call_reply(query="onboarding"):
    return ModelReply(
        content=None,
        tool_calls=[ModelToolCall(id="call_1", name="search_evidence", arguments={"query": query})],
        usage=_usage(),
    )


VALID_DRAFT = {
    "mission_id": "ONBOARD-1",
    "title": "Onboarding friction for new design teams",
    "objective": "Find where new design teams drop off during onboarding to a research tool and why.",
    "success_criteria": [
        "Name the top three onboarding drop-off points",
        "Cite at least two sources for each drop-off point",
        "Distinguish demonstrated causes from proposed ones",
    ],
    "required_entities": ["onboarding", "activation"],
    "constraints": ["Prefer sources published in 2025 or 2026"],
    "deliverable_format": "Markdown report with one section per criterion",
    "tags": ["onboarding"],
}


@pytest.fixture
def librarian(monkeypatch):
    """Install a scripted model behind the real service; yield a way to script it."""
    holder: dict[str, ScriptedModel] = {}

    def install(*replies):
        model = ScriptedModel(replies)
        holder["model"] = model
        app.dependency_overrides[librarian_api.get_librarian_service] = lambda: LibrarianService(
            model_factory=lambda: model
        )
        return model

    yield install
    app.dependency_overrides.pop(librarian_api.get_librarian_service, None)
    app.dependency_overrides.pop(require_authenticated_user, None)


def _seed_user(db_session) -> User:
    return db_session.query(User).first()


def _capture_entry(db_session, project, claim="Three interviews mention onboarding confusion."):
    owner = _seed_user(db_session)
    entries = EvidenceLedgerService().capture(
        db_session,
        CaptureRequest(
            project_id=project.id,
            session_key="agent:test",
            entries=[
                CaptureItem(
                    claim=claim,
                    source_url="https://example.test/onboarding-interviews",
                    disposition="supporting",
                )
            ],
        ),
        owner_id=owner.id,
        workspace_id=None,
    )
    db_session.commit()
    return entries[0]


def _messages(*contents):
    roles = ["user", "assistant"]
    ordered = list(contents)
    # Alternate so the last message is always the user's.
    messages = []
    for index, content in enumerate(reversed(ordered)):
        messages.append({"role": roles[index % 2], "content": content})
    return list(reversed(messages))


class TestTurn:
    def test_corpus_claim_cites_evidence_the_tool_returned(self, librarian, db_session, project, auth_headers):
        entry = _capture_entry(db_session, project)
        model = librarian(
            _tool_call_reply(),
            _json_reply(
                [
                    {"kind": "prose", "text": "Onboarding research usually starts with the audience.", "citations": []},
                    {"kind": "corpus_claim", "text": "Your project already notes confusion.", "citations": [str(entry.id)]},
                ],
                suggested_action="draft_mission",
            ),
        )
        client = TestClient(app)
        response = client.post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("What do we know about onboarding?")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert [segment["kind"] for segment in body["segments"]] == ["prose", "corpus_claim"]
        assert body["segments"][1]["citations"] == [str(entry.id)]
        assert body["withheld_count"] == 0
        assert body["suggested_action"] == "draft_mission"
        assert body["evidence"] == [
            {
                "id": str(entry.id),
                "claim": entry.claim,
                "source_url": entry.source_url,
                "disposition": "supporting",
                "href": f"/evidence/{entry.id}",
            }
        ]
        assert body["usage"]["total_tokens"] == 30
        assert body["model"] == "fake-librarian"
        # The tool was offered, executed against the ledger, and its result fed back.
        assert model.calls[0]["tools"][0]["function"]["name"] == "search_evidence"
        tool_message = model.calls[1]["messages"][-1]
        assert tool_message["role"] == "tool"
        assert str(entry.id) in tool_message["content"]

    def test_fabricated_citation_is_withheld_after_one_repair(self, librarian, db_session, project, auth_headers):
        _capture_entry(db_session, project)
        fabricated = str(uuid.uuid4())
        model = librarian(
            _json_reply([{"kind": "corpus_claim", "text": "Your corpus proves X.", "citations": [fabricated]}]),
            _json_reply([{"kind": "corpus_claim", "text": "Your corpus proves X.", "citations": [fabricated]}]),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Does the corpus prove X?")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["withheld_count"] == 1
        assert body["segments"][0]["kind"] == "withheld"
        assert body["segments"][0]["citations"] == []
        assert "Your corpus proves X." not in response.text
        assert fabricated not in response.text
        assert body["evidence"] == []
        repair_prompt = model.calls[1]["messages"][-1]
        assert repair_prompt["role"] == "user"
        assert "provenance" in repair_prompt["content"]
        assert fabricated in repair_prompt["content"]

    def test_uncited_corpus_claim_is_repaired_into_prose(self, librarian, project, auth_headers):
        model = librarian(
            _json_reply([{"kind": "corpus_claim", "text": "Your project covers onboarding.", "citations": []}]),
            _json_reply([{"kind": "prose", "text": "I could not find onboarding evidence in this project.", "citations": []}]),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("What do we have on onboarding?")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["withheld_count"] == 0
        assert body["segments"] == [
            {"kind": "prose", "text": "I could not find onboarding evidence in this project.", "citations": []}
        ]
        assert "uncited_corpus_claim" in model.calls[1]["messages"][-1]["content"]

    def test_free_text_reply_is_rendered_as_prose(self, librarian, project, auth_headers):
        librarian(ModelReply(content="Sure, tell me who the research is for.", usage=_usage()))
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Help me plan a mission.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["segments"] == [
            {"kind": "prose", "text": "Sure, tell me who the research is for.", "citations": []}
        ]

    def test_without_a_project_no_tool_is_offered(self, librarian, auth_headers):
        model = librarian(_json_reply([{"kind": "prose", "text": "Let us shape the question first."}]))
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": None, "messages": _messages("I want to research onboarding.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert model.calls[0]["tools"] is None
        assert "planning mode" in model.calls[0]["messages"][0]["content"]

    def test_last_message_must_come_from_the_user(self, librarian, auth_headers):
        librarian()
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": None, "messages": [{"role": "assistant", "content": "Hello"}]},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unknown_project_is_404_before_the_model_runs(self, librarian, auth_headers):
        model = librarian()
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(uuid.uuid4()), "messages": _messages("Hi")},
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert model.calls == []

    def test_service_principal_is_refused(self, librarian, project, auth_headers):
        model = librarian()
        service = AuthenticatedUser(user_id=uuid.uuid4(), email="svc@tracelab.local", display_name="svc", role="service")
        app.dependency_overrides[require_authenticated_user] = lambda: service
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Hi")},
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert model.calls == []

    def test_user_cannot_reach_a_project_through_the_librarian_they_cannot_reach_directly(
        self, librarian, db_session, project, auth_headers, monkeypatch
    ):
        """Criterion 7: the Librarian runs authorize() with its user's principal, never a service role."""
        monkeypatch.setattr(authorization.settings, "rbac_enabled", True, raising=False)
        project.owner_id = _seed_user(db_session).id
        db_session.commit()
        stranger = AuthenticatedUser(user_id=uuid.uuid4(), email="guest@tracelab.local", display_name="g", role="member")
        app.dependency_overrides[require_authenticated_user] = lambda: stranger
        model = librarian()
        client = TestClient(app)
        for path, extra in (("turns", {}), ("drafts", {}), ("missions", {"draft": VALID_DRAFT})):
            payload = {"project_id": str(project.id), **extra}
            if path != "missions":
                payload["messages"] = _messages("Hi")
            response = client.post(f"/api/v1/librarian/{path}", json=payload, headers=auth_headers)
            assert response.status_code == 403, (path, response.text)
        assert model.calls == []

    def test_verb_contract(self, librarian, auth_headers):
        librarian()
        client = TestClient(app)
        assert client.get("/api/v1/librarian/turns", headers=auth_headers).status_code == 405
        assert client.post("/api/v1/librarian/turns", json={"messages": _messages("Hi")}).status_code == 401


class TestDraft:
    def test_invalid_draft_is_repaired_then_compiled_and_linted(self, librarian, project, auth_headers):
        broken = {**VALID_DRAFT, "objective": "short", "success_criteria": []}
        model = librarian(
            ModelReply(content=json.dumps(broken), usage=_usage()),
            ModelReply(content=json.dumps(VALID_DRAFT), usage=_usage()),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/drafts",
            json={"project_id": str(project.id), "messages": _messages("Draft a mission about onboarding.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["draft"]["mission_id"] == "ONBOARD-1"
        assert body["draft"]["success_criteria"] == VALID_DRAFT["success_criteria"]
        assert body["preview"] is not None
        assert body["preview"]["fidelity"] == "structural_only"
        assert len(body["preview"]["objectives"]) >= 1
        assert body["preview_error"] is None
        assert isinstance(body["lint_errors"], list) and isinstance(body["lint_warnings"], list)
        assert body["usage"]["total_tokens"] == 30
        assert all(call["json_mode"] for call in model.calls)
        repair = model.calls[1]["messages"][-1]["content"]
        assert "failed validation" in repair and "objective" in repair

    def test_unrecoverable_draft_is_422(self, librarian, project, auth_headers):
        librarian(ModelReply(content="not json", usage=_usage()), ModelReply(content="{}", usage=_usage()))
        response = TestClient(app).post(
            "/api/v1/librarian/drafts",
            json={"project_id": str(project.id), "messages": _messages("Draft it.")},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "could not produce a valid mission draft" in response.json()["detail"]

    def test_long_criteria_are_flagged_in_notes(self, librarian, project, auth_headers):
        verbose = {**VALID_DRAFT, "success_criteria": ["x" * 250, "Short criterion"]}
        librarian(ModelReply(content=json.dumps(verbose), usage=_usage()))
        response = TestClient(app).post(
            "/api/v1/librarian/drafts",
            json={"project_id": str(project.id), "messages": _messages("Draft it.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert any("200 characters" in note for note in response.json()["notes"])


class TestCreate:
    def test_creates_a_pristine_librarian_marked_draft_idempotently(self, librarian, project, auth_headers):
        librarian()
        client = TestClient(app)
        payload = {"project_id": str(project.id), "draft": VALID_DRAFT}
        first = client.post("/api/v1/librarian/missions", json=payload, headers=auth_headers)
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["created"] is True
        mission = body["mission"]
        assert mission["mission_id"] == "ONBOARD-1"
        assert mission["status"] == "draft"
        assert mission["project_id"] == str(project.id)
        assert mission["created_by"] == "librarian"
        assert mission["tags"] == ["onboarding", "librarian"]
        assert mission["required_entities"] == ["onboarding", "activation"]
        assert mission["constraints"] == ["Prefer sources published in 2025 or 2026"]

        second = client.post("/api/v1/librarian/missions", json=payload, headers=auth_headers)
        assert second.status_code == 200, second.text
        assert second.json()["created"] is False
        assert second.json()["mission"]["id"] == mission["id"]

        clash = client.post(
            "/api/v1/librarian/missions",
            json={"project_id": str(project.id), "draft": {**VALID_DRAFT, "title": "A different mission"}},
            headers=auth_headers,
        )
        assert clash.status_code == 409

        # The mission is a normal mission: the existing surface reads it and can preview it.
        assert client.get(f"/api/v1/missions/{mission['id']}", headers=auth_headers).status_code == 200
        preview = client.get(f"/api/v1/missions/{mission['id']}/contract-preview", headers=auth_headers)
        assert preview.status_code == 200, preview.text

    def test_draft_validation_uses_mission_rules(self, librarian, project, auth_headers):
        librarian()
        response = TestClient(app).post(
            "/api/v1/librarian/missions",
            json={"project_id": str(project.id), "draft": {**VALID_DRAFT, "mission_id": "bad id!"}},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "mission_id" in response.text


def test_usage_is_recorded_for_metering(librarian, project, auth_headers):
    """Usage is recorded under route 'librarian' so METER-0 has something to read."""
    from app.services.cost_monitor import get_cost_monitor

    librarian(_json_reply([{"kind": "prose", "text": "Hello"}]))
    TestClient(app).post(
        "/api/v1/librarian/turns",
        json={"project_id": str(project.id), "messages": _messages("Hi")},
        headers=auth_headers,
    )
    recent = get_cost_monitor().summary()["recent"]
    matching = [event for event in recent if event.get("route") == "librarian"]
    assert matching, recent
    # Most recent first: the monitor is a process singleton shared with earlier tests.
    assert matching[0]["model"] == "fake-librarian"
    assert matching[0]["project_id"] == str(project.id)


class TestTruncatedTurns:
    """The first production run cut two replies at the token cap and showed raw JSON. Never again."""

    TRUNCATED = '{"segments":[{"kind":"prose","text":"A long comparison of Notion, Figma and","citations":[]},{"kind":"pro'

    def test_truncated_reply_is_retried_once_concisely(self, librarian, project, auth_headers):
        model = librarian(
            ModelReply(content=self.TRUNCATED, usage=_usage(), finish_reason="length"),
            _json_reply([{"kind": "prose", "text": "Short version: compare grant models first.", "citations": []}]),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Compare sharing models.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["segments"] == [
            {"kind": "prose", "text": "Short version: compare grant models first.", "citations": []}
        ]
        retry_prompt = model.calls[1]["messages"][-1]
        assert retry_prompt["role"] == "user"
        assert "cut off" in retry_prompt["content"]
        assert model.calls[1]["tools"] is None

    def test_twice_truncated_reply_shows_salvaged_prose_not_json(self, librarian, project, auth_headers):
        librarian(
            ModelReply(content=self.TRUNCATED, usage=_usage(), finish_reason="length"),
            ModelReply(content=self.TRUNCATED, usage=_usage(), finish_reason="length"),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Compare sharing models.")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        segments = response.json()["segments"]
        assert len(segments) == 1 and segments[0]["kind"] == "prose"
        assert segments[0]["text"] == "A long comparison of Notion, Figma and"
        assert "{" not in segments[0]["text"]

    def test_unparsed_json_without_length_signal_is_also_retried(self, librarian, project, auth_headers):
        """Some providers do not report finish_reason; the broken shape alone must trigger the retry."""
        model = librarian(
            ModelReply(content=self.TRUNCATED, usage=_usage(), finish_reason=None),
            _json_reply([{"kind": "prose", "text": "Recovered.", "citations": []}]),
        )
        response = TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages("Compare sharing models.")},
            headers=auth_headers,
        )
        assert response.json()["segments"][0]["text"] == "Recovered."
        assert len(model.calls) == 2


class TestAnswer:
    """QA-1: a turn in answer mode goes to the corpus Q&A service, never the Librarian's model.

    Every citation it renders opens a chunk the answer was written from, and a
    question the project cannot support is refused with nothing asserted.
    """

    USAGE = {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}

    class FakeRag:
        def __init__(self, result):
            self.result = result
            self.calls: list[dict] = []

        def run_query(self, **kwargs):
            self.calls.append(kwargs)
            return self.result

    def _rag(self, monkeypatch, answer, sources, *, no_evidence=False, cache_hit=False, attempts=None):
        fake = self.FakeRag(
            {
                "answer": answer,
                "citations": [],
                "sources": sources,
                "cache": {"hit": cache_hit},
                "routing": {
                    "selected_model": "gpt-test",
                    "attempts": attempts if attempts is not None else [{"model": "gpt-test", "usage": self.USAGE}],
                },
                "no_evidence": no_evidence,
            }
        )
        monkeypatch.setattr(corpus_qa, "get_rag_service", lambda: fake)
        return fake

    @staticmethod
    def _chunk(db_session, project, index=9):
        document = Document(project_id=project.id, name="qdrant-on-railway.md", mime_type="text/markdown")
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        source = {
            "chunk_id": str(uuid.uuid4()),
            "content": "The Hobby plan bill is approximately $48-$63 a month.",
            "document_id": str(document.id),
            "chunk_index": index,
            "similarity": 0.63,
        }
        return document, source

    @staticmethod
    def _ask(project, headers, question="What does self-hosting Qdrant cost?", **extra):
        return TestClient(app).post(
            "/api/v1/librarian/turns",
            json={"project_id": str(project.id), "messages": _messages(question), "mode": "answer", **extra},
            headers=headers,
        )

    def test_routes_to_the_qa_service_and_renders_cited_passages(
        self, librarian, monkeypatch, db_session, project, auth_headers
    ):
        model = librarian()
        document, source = self._chunk(db_session, project)
        rag = self._rag(
            monkeypatch,
            f"The bill is **$48–$63** a month. [Document: {document.id}, Chunk: 9]\n\nManaged hosting costs more.",
            [source],
        )

        response = self._ask(project, auth_headers, max_tokens=2000)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["segments"] == [
            {"kind": "corpus_claim", "text": "The bill is **$48–$63** a month.", "citations": [source["chunk_id"]]},
            {"kind": "prose", "text": "Managed hosting costs more.", "citations": []},
        ]
        assert body["chunks"] == [
            {
                "id": source["chunk_id"],
                "document_id": str(document.id),
                "document_name": "qdrant-on-railway.md",
                "chunk_index": 9,
                "snippet": source["content"],
                "href": f"/documents/{document.id}?chunk={source['chunk_id']}&index=9",
            }
        ]
        assert body["no_evidence"] is False
        assert body["evidence"] == []
        assert body["withheld_count"] == 0
        assert body["model"] == "gpt-test"
        assert model.calls == [], "answer mode never calls the Librarian's model"
        assert rag.calls[0]["query"] == "What does self-hosting Qdrant cost?"
        assert rag.calls[0]["max_tokens"] == 2000
        assert rag.calls[0]["refuse_unsupported"] is True

    def test_every_rendered_citation_passes_the_provenance_validator(
        self, librarian, monkeypatch, db_session, project, auth_headers
    ):
        from app.schemas.librarian import AssistantReply, ReplySegment
        from app.services.librarian import validate_provenance

        librarian()
        document, source = self._chunk(db_session, project)
        other_document, other = self._chunk(db_session, project, index=10)
        self._rag(
            monkeypatch,
            f"Cost is $48. [Document: {document.id}, Chunk: 9]\n\n"
            f"Quantization cuts memory. [Document: {other_document.id}, Chunk: 10] [Document: {document.id}, Chunk: 9]",
            [source, other],
        )

        body = self._ask(project, auth_headers).json()

        reply = AssistantReply(segments=[ReplySegment(**segment) for segment in body["segments"]])
        assert validate_provenance(reply, {source["chunk_id"], other["chunk_id"]}) == []
        rendered = {citation for segment in body["segments"] for citation in segment["citations"]}
        assert rendered == {chunk["id"] for chunk in body["chunks"]}

    def test_a_citation_the_answer_was_not_written_from_is_withheld(self, librarian, monkeypatch, project, auth_headers):
        """The validator runs on answer turns too, whatever the service hands back."""
        import app.services.librarian as librarian_service
        from app.services.corpus_qa import AnswerCitation, AnswerPassage, CorpusAnswer

        librarian()
        stray = str(uuid.uuid4())
        monkeypatch.setattr(
            librarian_service,
            "answer_question",
            lambda *args, **kwargs: CorpusAnswer(
                passages=[AnswerPassage(text="Budgets doubled.", citations=[stray])],
                citations=[AnswerCitation(stray, str(uuid.uuid4()), "x.md", 1, None, "/documents/x")],
                no_evidence=False,
                source_chunk_ids=[str(uuid.uuid4())],
            ),
        )

        body = self._ask(project, auth_headers).json()

        assert body["withheld_count"] == 1
        assert body["segments"][0]["kind"] == "withheld"
        assert "Budgets doubled." not in str(body)
        assert body["chunks"] == []

    def test_nothing_found_renders_the_refusal_and_asserts_nothing(self, librarian, monkeypatch, project, auth_headers):
        librarian()
        self._rag(monkeypatch, "Nothing in this project answers that question.", [], no_evidence=True, attempts=[])

        body = self._ask(project, auth_headers, "How does Kubernetes autoscale pods?").json()

        assert body["no_evidence"] is True
        assert body["segments"] == [
            {"kind": "prose", "text": "Nothing in this project answers that question.", "citations": []}
        ]
        assert body["chunks"] == [] and body["evidence"] == []
        assert body["usage"] is None

    def test_request_rules(self, librarian, project, auth_headers):
        model = librarian()
        client = TestClient(app)
        cases = [
            {"project_id": None, "messages": _messages("What does it cost?"), "mode": "answer"},
            {"project_id": str(project.id), "messages": _messages("   "), "mode": "answer"},
            {"project_id": str(project.id), "messages": _messages("Hi"), "max_tokens": 600},
            {"project_id": str(project.id), "messages": _messages("Hi"), "mode": "answer", "max_tokens": 63},
            {"project_id": str(project.id), "messages": _messages("Hi"), "mode": "answer", "max_tokens": 4001},
            {"project_id": str(project.id), "messages": _messages("Hi"), "mode": "search"},
        ]
        for payload in cases:
            response = client.post("/api/v1/librarian/turns", json=payload, headers=auth_headers)
            assert response.status_code == 422, (payload, response.text)
        assert model.calls == []

    def test_a_project_the_user_cannot_read_is_403_before_retrieval(
        self, librarian, monkeypatch, db_session, project, auth_headers
    ):
        monkeypatch.setattr(authorization.settings, "rbac_enabled", True, raising=False)
        project.owner_id = _seed_user(db_session).id
        db_session.commit()
        stranger = AuthenticatedUser(user_id=uuid.uuid4(), email="guest@tracelab.local", display_name="g", role="member")
        app.dependency_overrides[require_authenticated_user] = lambda: stranger
        librarian()
        rag = self._rag(monkeypatch, "The bill is $48.", [])

        response = self._ask(project, auth_headers)

        assert response.status_code == 403
        assert rag.calls == []

    def test_each_paid_call_is_metered_and_a_cached_answer_is_not(
        self, librarian, monkeypatch, db_session, project, auth_headers
    ):
        from app.models.usage_record import USAGE_KIND_LIBRARIAN_TURN, UsageRecord

        librarian()
        document, source = self._chunk(db_session, project)
        answer = f"The bill is $48. [Document: {document.id}, Chunk: 9]"
        escalated = [
            {"model": "gpt-5.1", "usage": self.USAGE},
            {"model": "gpt-5.2", "usage": {"prompt_tokens": 950, "completion_tokens": 140, "total_tokens": 1090}},
        ]
        self._rag(monkeypatch, answer, [source], attempts=escalated)

        body = self._ask(project, auth_headers).json()

        rows = (
            db_session.query(UsageRecord)
            .filter(UsageRecord.project_id == project.id, UsageRecord.kind == USAGE_KIND_LIBRARIAN_TURN)
            .all()
        )
        assert sorted((row.model, row.total_tokens, row.requests) for row in rows) == [
            ("gpt-5.1", 1020, 1),
            ("gpt-5.2", 1090, 1),
        ]
        assert body["usage"] == {"prompt_tokens": 1850, "completion_tokens": 260, "total_tokens": 2110}

        self._rag(monkeypatch, answer, [source], cache_hit=True, attempts=escalated)
        assert self._ask(project, auth_headers, "What does it cost to self-host?").json()["usage"] is None
        assert db_session.query(UsageRecord).filter(UsageRecord.project_id == project.id).count() == 2
