"""ORG-1: reviewed membership, scope and retry determine the saved artifact."""

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
from app.models.usage_record import UsageRecord
from app.services.collection import CollectionService
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply


@pytest.fixture
def organisation(monkeypatch, auth_headers, db_session, project):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Organisation tests cannot contact outbound services")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    doc = Document(name="Interview", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    chunks = [DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Finding {i}: people need clearer source navigation.") for i in range(3)]
    db_session.add_all(chunks)
    db_session.commit()
    model = Mock(model_name="organisation-test")
    model.complete.return_value = ModelReply(content=json.dumps({"groups": [
        {"name": "Navigation", "description": "Feedback about finding sources", "rationale": "Source navigation is unclear [3] [1] [2].", "members": [3, 1, 2]},
        {"name": "Other view", "description": "An optional reading", "rationale": "A source-navigation example [2].", "members": [2]},
    ]}), usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20})
    app.dependency_overrides[get_librarian_service] = lambda: LibrarianService(model_factory=lambda: model)
    client = TestClient(app)
    client.headers.update(auth_headers)
    yield client, model, project, doc, chunks
    app.dependency_overrides.pop(get_librarian_service, None)


def draft(client, project):
    response = client.post("/api/v1/librarian/collections/draft", json={"project_id": str(project.id), "prompt": "Group feedback by pain point"})
    assert response.status_code == 200, response.text
    return response.json()


def accept(client, project, group, **changes):
    return client.post("/api/v1/librarian/collections/accept", json={
        "project_id": str(project.id), "proposal_token": group["proposal_token"], "name": group["name"],
        "description": group["description"], "member_ids": [m["chunk_id"] for m in group["members"]], **changes,
    })


def test_preview_then_one_edited_group_saves_only_reviewed_members(organisation, db_session):
    client, model, project, _, chunks = organisation
    proposal = draft(client, project)
    assert db_session.query(Collection).count() == db_session.query(CollectionItem).count() == 0
    assert db_session.query(UsageRecord).count() == 1
    group = proposal["groups"][0]
    selected = [str(chunks[2].id), str(chunks[1].id)]
    saved = accept(client, project, group, name="Reviewed navigation", description="Human description", member_ids=selected)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result["state"] == "saved"
    assert result["completed_member_ids"] == selected
    assert result["missing_member_ids"] == []
    repeated = accept(client, project, group, name="Reviewed navigation", description="Human description", member_ids=selected)
    assert repeated.json() == result
    db_session.expire_all()
    row = db_session.query(Collection).one()
    assert row.name == "Reviewed navigation" and row.description == "Human description"
    assert row.owner_id is not None
    assert row.generation_provenance["accepted_member_ids"] == selected
    assert row.generation_provenance["accepted_by"] == str(row.owner_id)
    detail = client.get(f"/api/v1/collections/{row.id}").json()
    assert [item["chunk_id"] for item in detail["items"]] == selected
    assert detail["item_count"] == 2
    provenance = client.get(f"/api/v1/librarian/collections/{row.id}").json()
    assert provenance["provenance"]["model"] == "organisation-test"
    assert model.complete.call_count == db_session.query(UsageRecord).count() == 1


def test_partial_failure_retry_reuses_collection_and_preserves_order(organisation, db_session, monkeypatch):
    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    original = CollectionService.add_chunk
    calls = []
    def fail_second(self, *args, **kwargs):
        calls.append(str(kwargs["chunk_id"]))
        if len(calls) == 2:
            raise RuntimeError("isolated attachment failure")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CollectionService, "add_chunk", fail_second)
    partial = accept(client, project, group)
    assert partial.status_code == 200, partial.text
    assert partial.json()["state"] == "partial"
    assert len(partial.json()["completed_member_ids"]) == 1
    assert len(partial.json()["missing_member_ids"]) == 2
    assert db_session.query(Collection).count() == 1
    monkeypatch.setattr(CollectionService, "add_chunk", original)
    saved = accept(client, project, group).json()
    assert saved["collection_id"] == partial.json()["collection_id"]
    assert saved["state"] == "saved"
    assert saved["completed_member_ids"] == [m["chunk_id"] for m in group["members"]]
    assert db_session.query(Collection).count() == 1
    assert db_session.query(CollectionItem).count() == 3


@pytest.mark.parametrize("change", ["token", "foreign_member", "empty", "limit", "reorder", "extra"])
def test_unreviewed_acceptance_is_rejected_without_creation(organisation, db_session, change):
    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    changes = {
        "token": {"proposal_token": "forged"}, "foreign_member": {"member_ids": [str(uuid4())]},
        "empty": {"member_ids": []}, "limit": {"member_ids": [str(uuid4()) for _ in range(101)]},
        "reorder": {"member_ids": list(reversed([m["chunk_id"] for m in group["members"]]))},
        "extra": {"owner_id": str(uuid4())},
    }[change]
    response = accept(client, project, group, **changes)
    assert response.status_code == 422, response.text
    assert db_session.query(Collection).count() == 0


@pytest.mark.parametrize("change", ["text", "deleted", "reparented"])
def test_stale_member_prevents_even_collection_creation(organisation, db_session, change):
    from datetime import datetime

    client, _, project, doc, chunks = organisation
    group = draft(client, project)["groups"][0]
    if change == "text":
        chunks[0].content = "The source was edited after review"
    elif change == "deleted":
        doc.deleted_at = datetime.utcnow()
    else:
        other = Project(name="Other project")
        db_session.add(other)
        db_session.flush()
        doc.project_id = other.id
    db_session.commit()
    response = accept(client, project, group)
    assert response.status_code == 409, response.text
    assert db_session.query(Collection).count() == 0


def test_completed_retry_cannot_restore_removed_members_or_deleted_collection(organisation, db_session):
    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    saved = accept(client, project, group).json()
    identity = saved["collection_id"]
    removed = group["members"][0]["chunk_id"]
    assert client.delete(f"/api/v1/collections/{identity}/chunks/{removed}").status_code == 204
    repeated = accept(client, project, group).json()
    assert repeated["state"] == "changed"
    assert repeated["missing_member_ids"] == [removed]
    assert db_session.query(CollectionItem).count() == 2
    assert client.delete(f"/api/v1/collections/{identity}").status_code == 204
    assert accept(client, project, group).status_code == 409
    assert db_session.query(Collection).count() == 0
    assert db_session.query(IdempotencyRecord).count() == 1


def test_pending_payload_is_immutable_on_retry(organisation, db_session, monkeypatch):
    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    monkeypatch.setattr(CollectionService, "add_chunk", Mock(side_effect=RuntimeError("unavailable")))
    partial = accept(client, project, group).json()
    assert partial["state"] == "partial"
    assert accept(client, project, group, name="Different intent").status_code == 409
    assert db_session.query(Collection).count() == 1


def test_source_changed_between_validation_and_attachment_stays_partial(organisation, db_session, monkeypatch):
    from app.core.database import SessionLocal

    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    original = CollectionService.add_chunk
    def changed_before_add(self, *args, **kwargs):
        with SessionLocal() as other:
            row = other.get(DocumentChunk, kwargs["chunk_id"])
            row.content = "Edited during attachment"
            other.commit()
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CollectionService, "add_chunk", changed_before_add)
    result = accept(client, project, group).json()
    assert result["state"] == "partial"
    assert result["completed_member_ids"] == []
    assert db_session.query(CollectionItem).count() == 0
    assert db_session.query(Collection).one().generation_provenance["completed_at"] is None


def test_read_order_matches_collection_export_and_report_inputs(organisation, db_session):
    from sqlalchemy import true

    from app.services.document_policy import resolve_readable_chunks
    from app.services.synthesis import SynthesisService

    client, _, project, _, chunks = organisation
    group = draft(client, project)["groups"][0]
    identity = accept(client, project, group).json()["collection_id"]
    expected = [str(chunks[i].id) for i in (2, 0, 1)]
    rows = resolve_readable_chunks(db_session, document_filter=true(), collection_id=identity)
    assert [str(row[0]) for row in rows] == expected
    synthesis = SynthesisService.__new__(SynthesisService)
    from app.core.database import SessionLocal
    synthesis.session_factory = SessionLocal
    rows, _ = synthesis._fetch_collection_chunks(identity, accessible_project_ids=[project.id])
    assert [row["chunk_id"] for row in rows] == expected
    export = client.get(f"/api/v1/collections/{identity}/export").text
    assert export.index("Finding 2") < export.index("Finding 0") < export.index("Finding 1")


@pytest.mark.parametrize("failure", ["empty", "unknown", "duplicate", "uncited", "malformed", "truncated", "action"])
def test_bad_generation_still_counts_usage_but_never_writes_collections(organisation, db_session, failure):
    client, model, project, _, _ = organisation
    body = json.loads(model.complete.return_value.content)
    if failure == "empty":
        body["groups"] = []
    elif failure == "unknown":
        body["groups"][0]["members"] = [999]
    elif failure == "duplicate":
        body["groups"][0]["members"] = [1, 1]
    elif failure == "uncited":
        body["groups"][0]["rationale"] = "Unsupported corpus claim"
    elif failure == "action":
        body["groups"][0]["delete_document"] = str(uuid4())
    model.complete.return_value.content = "not json" if failure == "malformed" else json.dumps(body)
    if failure == "truncated":
        model.complete.return_value.finish_reason = "length"
    response = client.post("/api/v1/librarian/collections/draft", json={"project_id": str(project.id), "prompt": "Group feedback"})
    assert response.status_code == 422
    assert db_session.query(UsageRecord).count() == 1
    assert db_session.query(Collection).count() == db_session.query(IdempotencyRecord).count() == 0


def test_input_limits_and_unchunked_documents_are_disclosed(organisation, db_session):
    client, model, project, doc, _ = organisation
    db_session.add(Document(name="Unprocessed", project_id=project.id, content="Text without saved chunks"))
    db_session.add_all([DocumentChunk(document_id=doc.id, chunk_index=i + 3, content=value)
                        for i, value in enumerate(["a" * 4000] * 25 + [" ", "b" * 4001])])
    db_session.commit()
    result = draft(client, project)
    supplied = json.loads(model.complete.call_args.args[0][-1]["content"])["excerpts"]
    assert len(supplied) <= 20 and sum(len(s["text"]) for s in supplied) <= 24000
    assert model.complete.call_args.kwargs["max_tokens"] == 4000
    assert result["coverage"]["limited"] is True
    assert result["coverage"]["readable_documents"] == 2
    assert result["coverage"]["documents_with_eligible_chunks"] == 1
    assert result["coverage"]["excluded_chunks"] == 2


def test_empty_project_refuses_before_initializing_model(organisation, db_session):
    client, model, _, _, _ = organisation
    empty = Project(name="Empty")
    db_session.add(empty)
    db_session.commit()
    response = client.post("/api/v1/librarian/collections/draft", json={"project_id": str(empty.id), "prompt": "Organise"})
    assert response.status_code == 422
    model.complete.assert_not_called()


def test_privileged_caller_is_still_scoped_before_provider_and_acceptance(organisation, db_session, monkeypatch):
    client, model, project, _, _ = organisation
    monkeypatch.setattr(settings, "rbac_enabled", True)
    foreign = Project(name="Foreign")
    db_session.add(foreign)
    db_session.flush()
    doc = Document(name="Private", project_id=foreign.id)
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocumentChunk(document_id=doc.id, chunk_index=0, content="FOREIGN SECRET"))
    db_session.commit()
    result = draft(client, project)
    assert "FOREIGN SECRET" not in str(model.complete.call_args)
    assert accept(client, foreign, result["groups"][0]).status_code == 422


def test_wrong_user_and_service_cannot_accept_another_principals_group(organisation, db_session, monkeypatch):
    from app.core.security import AuthenticatedUser, require_authenticated_user

    client, model, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    for role, expected in (("member", 422), ("service", 403)):
        principal = AuthenticatedUser(user_id=uuid4(), email="fixture@example.test", display_name="Fixture", role=role)
        monkeypatch.setitem(app.dependency_overrides, require_authenticated_user, lambda principal=principal: principal)
        assert accept(client, project, group).status_code == expected
    assert db_session.query(Collection).count() == 0
    assert model.complete.call_count == 1


def test_revoked_access_rejects_acceptance_before_creation(organisation, db_session, monkeypatch):
    from app.models.user import User

    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    user = db_session.query(User).first()
    user.role = "member"
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", True)
    assert accept(client, project, group).status_code == 403
    assert db_session.query(Collection).count() == 0


def test_member_owns_saved_collection_and_revoked_sources_disappear(organisation, db_session, monkeypatch):
    from app.models.user import User

    client, _, project, doc, _ = organisation
    user = db_session.query(User).first()
    user.role = "member"
    project.owner_id = doc.owner_id = user.id
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", True)
    group = draft(client, project)["groups"][0]
    response = accept(client, project, group)
    assert response.status_code == 200, response.text
    identity = response.json()["collection_id"]
    assert client.get(f"/api/v1/collections/{identity}").json()["item_count"] == 3
    origin = client.get(f"/api/v1/librarian/collections/{identity}").json()["provenance"]
    assert origin["accepted_by"] == str(user.id)
    assert all(source["available"] for source in origin["members"])
    # Ownership of the new artifact must not preserve access to a revoked project.
    project.owner_id = doc.owner_id = None
    db_session.commit()
    assert client.get(f"/api/v1/collections/{identity}").json()["item_count"] == 0
    origin = client.get(f"/api/v1/librarian/collections/{identity}").json()["provenance"]
    assert origin["origin"] == "librarian"
    assert "members" not in origin and "prompt" not in origin and "project_id" not in origin


def test_reparented_sources_are_unavailable_even_to_privileged_origin_reader(organisation, db_session):
    client, _, project, doc, _ = organisation
    group = draft(client, project)["groups"][0]
    identity = accept(client, project, group).json()["collection_id"]
    other = Project(name="Different research")
    db_session.add(other)
    db_session.flush()
    doc.project_id = other.id
    db_session.commit()
    origin = client.get(f"/api/v1/librarian/collections/{identity}").json()["provenance"]
    assert origin["members"] == [{"marker": member["marker"], "available": False} for member in group["members"]]


def test_changed_source_after_last_attachment_prevents_completed_receipt(organisation, db_session, monkeypatch):
    from app.core.database import SessionLocal

    client, _, project, _, _ = organisation
    group = draft(client, project)["groups"][0]
    original = CollectionService.add_chunk
    calls = 0
    def change_after_last(self, *args, **kwargs):
        nonlocal calls
        result = original(self, *args, **kwargs)
        calls += 1
        if calls == len(group["members"]):
            with SessionLocal() as other:
                row = other.get(DocumentChunk, kwargs["chunk_id"])
                row.content = "Changed after attachment but before final validation"
                other.commit()
        return result
    monkeypatch.setattr(CollectionService, "add_chunk", change_after_last)
    response = accept(client, project, group)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "partial" and result["missing_member_ids"] == []
    assert "Sources changed" in result["error"]
    assert db_session.query(Collection).one().generation_provenance["completed_at"] is None
