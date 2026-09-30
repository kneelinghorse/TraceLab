"""LIB-4: the human-reviewed preview, not a second generation, is the artifact."""

import json
import socket
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.librarian import get_librarian_service
from app.core.config import settings
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.idempotency import IdempotencyRecord
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.usage_record import UsageRecord
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply


@pytest.fixture
def reviewed_report(monkeypatch, auth_headers, db_session, project):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Report review tests cannot contact outbound services")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    doc = Document(name="Interview", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    chunks = [DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Finding {i}: researchers need visible source context.") for i in range(3)]
    db_session.add_all(chunks)
    db_session.commit()
    model = Mock(model_name="isolated-report-review")
    model.complete.return_value = ModelReply(content=json.dumps({"content": "# Findings\n\nSource context matters [1] [3]."}),
                                            usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20})
    app.dependency_overrides[get_librarian_service] = lambda: LibrarianService(model_factory=lambda: model)
    client = TestClient(app)
    client.headers.update(auth_headers)
    yield client, model, project, doc, chunks
    app.dependency_overrides.pop(get_librarian_service, None)


def source_list(client, project, **params):
    response = client.get("/api/v1/librarian/reports/sources", params={"project_id": str(project.id), **params})
    assert response.status_code == 200, response.text
    return response.json()


def draft(client, project, sources=None, **changes):
    sources = sources or source_list(client, project)
    return client.post("/api/v1/librarian/reports/draft", json={
        "project_id": str(project.id), "source_token": sources["source_token"],
        "chunk_ids": [s["chunk_id"] for s in sources["members"]], "reviewed_sources": True,
        "title": "Reviewed feedback", "prompt": "Summarise the source navigation feedback", "format": "report", **changes,
    })


def accept(client, project, proposal, **changes):
    return client.post("/api/v1/librarian/reports/accept", json={"project_id": str(project.id), "proposal_token": proposal["proposal_token"], **changes})


def test_preview_then_exact_save_and_retry_never_generate_again(reviewed_report, db_session):
    client, model, project, _, chunks = reviewed_report
    response = draft(client, project)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert db_session.query(Report).count() == db_session.query(ReportSource).count() == 0
    assert db_session.query(UsageRecord).count() == 1
    saved = accept(client, project, preview)
    assert saved.status_code == 200, saved.text
    assert accept(client, project, preview).json() == saved.json()
    db_session.expire_all()
    row = db_session.query(Report).one()
    assert row.content == preview["content"]
    assert row.title == preview["title"] and row.status == "draft"
    assert row.generation_provenance["origin"] == "librarian"
    assert row.generation_provenance["accepted_by"] == str(row.owner_id)
    assert [c["marker"] for c in row.citation_manifest] == [1, 3]
    assert {str(s.source_id) for s in row.sources} == {str(c.id) for c in chunks}
    detail = client.get(f"/api/v1/reports/{row.id}").json()
    assert detail["content"] == preview["content"]
    assert detail["citations"] == preview["citations"]
    assert model.complete.call_count == db_session.query(UsageRecord).count() == 1


def test_foreign_project_chunks_never_reach_preview_or_model(reviewed_report, db_session):
    client, model, project, _, _ = reviewed_report
    other = Project(name="Outside chosen project")
    db_session.add(other)
    db_session.flush()
    doc = Document(name="Private other context", project_id=other.id)
    db_session.add(doc)
    db_session.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="Outside context")
    db_session.add(chunk)
    db_session.commit()
    sources = source_list(client, project)
    assert str(chunk.id) not in json.dumps(sources)
    response = draft(client, project, sources, chunk_ids=[str(chunk.id)])
    assert response.status_code == 422
    assert model.complete.call_count == 0
    assert db_session.query(Report).count() == 0


@pytest.mark.parametrize("failure", ["empty", "uncited", "unknown", "malformed", "truncated", "overlong", "extra"])
def test_refused_or_incomplete_generation_counts_once_without_artifact(reviewed_report, db_session, failure):
    client, model, project, _, _ = reviewed_report
    content = {"empty": "", "uncited": "Unsubstantiated conclusion.", "unknown": "Wrong source [999].", "overlong": "x" * 12001}.get(failure, "Supported [1].")
    body = {"content": content}
    if failure == "extra":
        body["create_report"] = True
    model.complete.return_value.content = "not json" if failure == "malformed" else json.dumps(body)
    if failure == "truncated":
        model.complete.return_value.finish_reason = "length"
    assert draft(client, project).status_code == 422
    assert model.complete.call_count == db_session.query(UsageRecord).count() == 1
    assert db_session.query(Report).count() == db_session.query(IdempotencyRecord).count() == 0


@pytest.mark.parametrize("change", ["token", "content", "owner", "project", "expired", "user"])
def test_unsigned_or_wrong_principal_acceptance_cannot_write(reviewed_report, db_session, monkeypatch, change):
    from jose import jwt

    from app.core.security import AuthenticatedUser, require_authenticated_user
    from app.services.librarian_reports import REPORT_AUDIENCE

    client, _, project, _, _ = reviewed_report
    proposal = draft(client, project).json()
    changes = {}
    if change == "token":
        changes["proposal_token"] = "forged"  # noqa: S105 — deliberately invalid signature
    elif change == "content":
        changes["content"] = "Unreviewed replacement [1]."
    elif change == "owner":
        changes["owner_id"] = str(uuid4())
    elif change == "project":
        other = Project(name="Other")
        db_session.add(other)
        db_session.commit()
        changes["project_id"] = str(other.id)
    elif change == "expired":
        value = jwt.decode(proposal["proposal_token"], settings.secret_key, algorithms=[settings.jwt_algorithm], audience=REPORT_AUDIENCE)
        value["exp"] = 1
        changes["proposal_token"] = jwt.encode(value, settings.secret_key, algorithm=settings.jwt_algorithm)
    else:
        principal = AuthenticatedUser(user_id=uuid4(), email="other@example.test", display_name="Other", role="member")
        monkeypatch.setitem(app.dependency_overrides, require_authenticated_user, lambda: principal)
    assert accept(client, project, proposal, **changes).status_code == 422
    assert db_session.query(Report).count() == db_session.query(IdempotencyRecord).count() == 0


@pytest.mark.parametrize("change", ["cited_text", "uncited_text", "deleted", "moved", "project_deleted"])
def test_all_effective_inputs_are_rechecked_at_save(reviewed_report, db_session, change):
    from datetime import datetime

    client, _, project, doc, chunks = reviewed_report
    proposal = draft(client, project).json()
    if change in {"cited_text", "uncited_text"}:
        chunks[0 if change == "cited_text" else 1].content = "Changed since human review"
    elif change == "deleted":
        doc.deleted_at = datetime.utcnow()
    elif change == "project_deleted":
        project.deleted_at = datetime.utcnow()
    else:
        other = Project(name="Moved")
        db_session.add(other)
        db_session.flush()
        doc.project_id = other.id
    db_session.commit()
    assert accept(client, project, proposal).status_code in {404, 409}
    assert db_session.query(Report).count() == 0


def test_source_changes_before_or_during_generation_require_review_again(reviewed_report, db_session):
    client, model, project, _, chunks = reviewed_report
    sources = source_list(client, project)
    chunks[0].content = "Edited after the source list"
    db_session.commit()
    assert draft(client, project, sources).status_code == 409
    model.complete.assert_not_called()
    sources = source_list(client, project)
    reply = model.complete.return_value
    def edit_during_call(*args, **kwargs):
        chunks[1].content = "Edited while provider was running"
        db_session.commit()
        return reply
    model.complete.side_effect = edit_during_call
    assert draft(client, project, sources).status_code == 409
    assert db_session.query(UsageRecord).count() == 1
    assert db_session.query(Report).count() == 0


def test_caps_are_visible_and_over_budget_selection_never_silently_truncates(reviewed_report, db_session):
    client, model, project, doc, _ = reviewed_report
    db_session.add_all([DocumentChunk(document_id=doc.id, chunk_index=i + 3, content=value)
                       for i, value in enumerate(["a" * 4000] * 101 + [" \n\t", "b" * 4001])])
    db_session.commit()
    sources = source_list(client, project)
    assert sources["coverage"]["eligible_chunks"] == 104
    assert sources["coverage"]["listed_chunks"] == 100
    assert sources["coverage"]["excluded_chunks"] == 2
    assert sources["coverage"]["limited"] is True
    assert all(len(s["text"]) == s["characters"] <= 4000 for s in sources["members"])
    for selected in ([], sources["members"][:13], sources["members"][3:10], [sources["members"][0]] * 2):
        assert draft(client, project, sources, chunk_ids=[s["chunk_id"] for s in selected]).status_code == 422
    assert draft(client, project, sources, chunk_ids=[sources["members"][0]["chunk_id"]], reviewed_sources=False).status_code == 422
    model.complete.assert_not_called()


def test_collection_filters_visibly_preserves_reviewed_order_and_rechecks_membership(reviewed_report, db_session, monkeypatch):
    client, model, project, _, chunks = reviewed_report
    monkeypatch.setattr(settings, "rbac_enabled", True)
    other = Project(name="Other readable project")
    db_session.add(other)
    db_session.flush()
    foreign = Document(name="Other feedback", project_id=other.id)
    db_session.add(foreign)
    db_session.flush()
    outside = DocumentChunk(document_id=foreign.id, chunk_index=0, content="Outside selected project")
    collection = Collection(name="Mixed project selection")
    db_session.add_all([outside, collection])
    db_session.flush()
    db_session.add_all([CollectionItem(collection_id=collection.id, chunk_id=c.id, review_position=i) for i, c in enumerate([chunks[2], outside, chunks[0]])])
    db_session.commit()
    sources = source_list(client, project, collection_id=str(collection.id))
    assert sources["coverage"]["other_project_chunks"] == 1
    assert [s["chunk_id"] for s in sources["members"]] == [str(chunks[2].id), str(chunks[0].id)]
    model.complete.return_value.content = json.dumps({"content": "Reviewed context [1] [2]."})
    proposal = draft(client, project, sources).json()
    assert "Outside selected project" not in str(model.complete.call_args)
    db_session.query(CollectionItem).filter(CollectionItem.collection_id == collection.id, CollectionItem.chunk_id == chunks[0].id).delete()
    db_session.commit()
    assert accept(client, project, proposal).status_code == 409
    assert db_session.query(Report).count() == 0


def test_receipt_and_sources_rollback_together_and_retry_never_resurrects_deletion(reviewed_report, db_session, monkeypatch):
    from sqlalchemy.orm import Session

    client, model, project, _, _ = reviewed_report
    proposal = draft(client, project).json()
    original = Session.commit
    def fail_report_commit(self):
        if any(isinstance(row, ReportSource) for row in self.new):
            raise RuntimeError("Isolated storage failure")
        return original(self)
    monkeypatch.setattr(Session, "commit", fail_report_commit)
    with pytest.raises(RuntimeError, match="Isolated storage"):
        accept(client, project, proposal)
    assert db_session.query(Report).count() == db_session.query(ReportSource).count() == db_session.query(IdempotencyRecord).count() == 0
    monkeypatch.setattr(Session, "commit", original)
    saved = accept(client, project, proposal).json()
    assert client.put(f"/api/v1/reports/{saved['report_id']}", json={"title": "Later human title"}).status_code == 200
    assert accept(client, project, proposal).json()["title"] == "Later human title"
    assert client.delete(f"/api/v1/reports/{saved['report_id']}").status_code == 200
    assert accept(client, project, proposal).status_code == 409
    assert db_session.query(Report).count() == 0
    assert db_session.query(IdempotencyRecord).count() == 1
    assert model.complete.call_count == 1


def test_member_ownership_exports_and_revoked_permissions(reviewed_report, db_session, monkeypatch):
    from app.models.user import User

    client, model, project, doc, _ = reviewed_report
    user = db_session.query(User).first()
    user.role = "member"
    project.owner_id = doc.owner_id = user.id
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", True)
    preview = draft(client, project).json()
    saved = accept(client, project, preview).json()
    detail = client.get(saved["href"].replace("/reports/", "/api/v1/reports/")).json()
    for format in ("md", "json", "txt"):
        exported = client.get(f"/api/v1/reports/{saved['report_id']}/export", params={"format": format})
        assert exported.status_code == 200
        if format == "json":
            assert exported.json()["content"] == preview["content"]
            assert exported.json()["citations"] == preview["citations"]
        else:
            assert preview["content"] in exported.text
            assert all(c["href"] in exported.text for c in detail["citations"])
    project.owner_id = doc.owner_id = None
    db_session.commit()
    assert accept(client, project, preview).status_code == 403
    assert db_session.query(Report).count() == 1
    assert model.complete.call_count == 1


def test_empty_or_unprocessed_context_and_service_principals_never_reach_provider(reviewed_report, db_session, monkeypatch):
    from app.core.security import AuthenticatedUser, require_authenticated_user

    client, model, _, _, _ = reviewed_report
    empty = Project(name="Only unprocessed text")
    db_session.add(empty)
    db_session.flush()
    db_session.add(Document(name="Pending ingestion", project_id=empty.id, content="There is text here, but no saved excerpts."))
    db_session.commit()
    sources = source_list(client, empty)
    assert sources["members"] == [] and sources["coverage"]["readable_chunks"] == 0
    assert draft(client, empty, sources).status_code == 422
    principal = AuthenticatedUser(user_id=uuid4(), email="service@example.test", display_name="Service", role="service")
    monkeypatch.setitem(app.dependency_overrides, require_authenticated_user, lambda: principal)
    assert client.get("/api/v1/librarian/reports/sources", params={"project_id": str(empty.id)}).status_code == 403
    assert draft(client, empty, sources, chunk_ids=[str(uuid4())]).status_code == 403
    model.complete.assert_not_called()


def test_collection_permission_is_refreshed_after_provider_returns(reviewed_report, db_session, monkeypatch):
    from app.models.user import User

    client, model, project, doc, chunks = reviewed_report
    user = db_session.query(User).first()
    other = User(email="collection-owner@example.test", display_name="Other", password_hash=str(uuid4()), role="member")
    db_session.add(other)
    db_session.flush()
    project.owner_id = doc.owner_id = user.id
    collection = Collection(name="Other owner collection", owner_id=other.id)
    db_session.add(collection)
    db_session.flush()
    db_session.add_all([CollectionItem(collection_id=collection.id, chunk_id=c.id, review_position=i) for i, c in enumerate(chunks)])
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", True)
    sources = source_list(client, project, collection_id=str(collection.id))
    reply = model.complete.return_value
    def revoke_during_call(*args, **kwargs):
        user.role = "member"
        db_session.commit()
        return reply
    model.complete.side_effect = revoke_during_call
    assert draft(client, project, sources).status_code == 403
    assert db_session.query(UsageRecord).count() == 1
    assert db_session.query(Report).count() == 0
