"""LIB-3: generation is not acceptance; later human edits always win."""

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
from app.models.document import Document
from app.models.project import Project
from app.models.usage_record import UsageRecord
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply


@pytest.fixture
def description_client(monkeypatch, auth_headers):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Description tests cannot contact outbound services")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    model = Mock(model_name="description-test")
    model.complete.return_value = ModelReply(
        content=json.dumps({"description": "A planned study of onboarding."}),
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    app.dependency_overrides[get_librarian_service] = lambda: LibrarianService(model_factory=lambda: model)
    client = TestClient(app)
    client.headers.update(auth_headers)
    yield client, model
    app.dependency_overrides.pop(get_librarian_service, None)


def draft(client, project):
    response = client.post("/api/v1/librarian/descriptions/draft", json={
        "project_id": str(project.id), "prompt": "Describe our planned onboarding study.",
    })
    assert response.status_code == 200, response.text
    return response.json()


def accept(client, project, proposal, **overrides):
    return client.post("/api/v1/librarian/descriptions/accept", json={
        "project_id": str(project.id), "proposal_token": proposal["proposal_token"],
        "description": proposal["description"], **overrides,
    })


def test_preview_accept_retry_restore_and_manual_edit(description_client, project, db_session):
    client, model = description_client
    previous = project.description
    proposal = draft(client, project)
    db_session.refresh(project)
    assert project.description == previous
    assert project.description_provenance is None
    assert proposal["basis"] == "planning_brief"
    assert db_session.query(UsageRecord).count() == 1
    saved = accept(client, project, proposal)
    assert saved.status_code == 200, saved.text
    state = saved.json()
    assert state["description"] == proposal["description"]
    assert state["provenance"]["accepted_by"]
    assert state["provenance"]["previous_value"] == previous
    assert state["can_restore"] is True
    assert accept(client, project, proposal).json() == state
    restore_payload = {"project_id": str(project.id), "proposal_id": state["provenance"]["proposal_id"]}
    restored = client.post("/api/v1/librarian/descriptions/restore", json=restore_payload)
    assert restored.status_code == 200, restored.text
    assert restored.json()["description"] == previous
    assert client.post("/api/v1/librarian/descriptions/restore", json=restore_payload).json() == restored.json()
    assert accept(client, project, proposal).status_code == 409
    assert model.complete.call_count == 1
    assert db_session.query(UsageRecord).count() == 1


def test_later_manual_edit_and_aba_prevent_stale_accept_or_undo(description_client, project):
    client, _ = description_client
    proposal = draft(client, project)
    for description in ("Human edit", project.description):
        assert client.put(f"/api/v1/projects/{project.id}", json={"description": description}).status_code == 200
    assert accept(client, project, proposal).status_code == 409
    proposal = draft(client, project)
    state = accept(client, project, proposal).json()
    client.put(f"/api/v1/projects/{project.id}", json={"description": "Later human text"})
    status = client.get(f"/api/v1/librarian/descriptions/{project.id}").json()
    assert status["can_restore"] is False
    assert status["provenance"]["current"] is False
    response = client.post("/api/v1/librarian/descriptions/restore", json={
        "project_id": str(project.id), "proposal_id": state["provenance"]["proposal_id"],
    })
    assert response.status_code == 409


def test_forged_token_wrong_project_and_unreviewed_fields(description_client, project, db_session):
    client, _ = description_client
    proposal = draft(client, project)
    assert accept(client, project, proposal, **{"proposal_token": "forged"}).status_code == 422
    assert accept(client, project, proposal, source_ids=[str(uuid4())]).status_code == 422
    other = Project(name="Other")
    db_session.add(other)
    db_session.commit()
    assert accept(client, other, proposal).status_code == 422


def test_corpus_citations_are_scoped_and_rechecked(description_client, project, db_session):
    client, model = description_client
    doc = Document(name="Interviews", project_id=project.id)
    other = Project(name="Other")
    db_session.add_all([doc, other])
    db_session.flush()
    unrelated = Document(name="Secret", project_id=other.id)
    db_session.add(unrelated)
    db_session.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="Onboarding interviews.")
    db_session.add_all([chunk, DocumentChunk(document_id=unrelated.id, chunk_index=0, content="OTHER PROJECT SECRET")])
    db_session.commit()
    model.complete.return_value.content = json.dumps({"description": "Onboarding research [1]."})
    proposal = draft(client, project)
    assert proposal["basis"] == "corpus"
    assert "OTHER PROJECT SECRET" not in str(model.complete.call_args)
    assert proposal["citations"][0]["chunk_id"] == str(chunk.id)
    assert accept(client, project, proposal, description="Fabricated [999].").status_code == 422
    chunk.content = "Edited after generation"
    db_session.commit()
    assert accept(client, project, proposal).status_code == 409
    db_session.refresh(project)
    assert project.description_provenance is None


def test_coverage_is_bounded_and_discloses_excluded_input(description_client, project, db_session):
    client, model = description_client
    doc = Document(name="Long project", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    contents = ["a" * 4000] * 20 + [" ", "b" * 4001]
    db_session.add_all([DocumentChunk(document_id=doc.id, chunk_index=i, content=value) for i, value in enumerate(contents)])
    db_session.commit()
    model.complete.return_value.content = '{"description":"A bounded overview [1]."}'
    proposal = draft(client, project)
    assert proposal["coverage"] == {"readable_chunks": 22, "eligible_chunks": 20, "used_chunks": 6,
                                    "excluded_chunks": 2, "limited": True, "chunk_limit": 12, "character_limit": 24000}
    supplied = json.loads(model.complete.call_args.args[0][-1]["content"])["sources"]
    assert sum(len(s["text"]) for s in supplied) == 24000
    assert model.complete.call_args.kwargs["max_tokens"] == 2500


@pytest.mark.parametrize("change", ["delete_document", "delete_project", "reparent", "revoke_document"])
def test_source_and_parent_liveness_checked_at_accept(description_client, project, db_session, monkeypatch, change):
    from datetime import datetime

    from app.models.user import User

    client, model = description_client
    owner = db_session.query(User).first()
    project.owner_id = owner.id
    doc = Document(name="Source", project_id=project.id, owner_id=owner.id)
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocumentChunk(document_id=doc.id, chunk_index=0, content="Onboarding facts"))
    db_session.commit()
    model.complete.return_value.content = '{"description":"Onboarding [1]."}'
    proposal = draft(client, project)
    if change == "delete_document":
        doc.deleted_at = datetime.utcnow()
    elif change == "delete_project":
        project.deleted_at = datetime.utcnow()
    elif change == "reparent":
        other = Project(name="Another readable project")
        db_session.add(other)
        db_session.flush()
        doc.project_id = other.id
    else:
        # Project ownership still grants document reads. Move it to a live but
        # inaccessible project while the caller remains able to update this one.
        monkeypatch.setattr(settings, "rbac_enabled", True)
        owner.role = "member"
        other = Project(name="Private")
        db_session.add(other)
        db_session.flush()
        doc.project_id = other.id
        doc.owner_id = None
    db_session.commit()
    assert accept(client, project, proposal).status_code in (404, 409)
    db_session.refresh(project)
    assert project.description_provenance is None


def test_human_project_authorization_precedes_model_and_signed_caller_is_required(description_client, project, db_session, monkeypatch):
    from app.core.security import AuthenticatedUser, require_authenticated_user
    from app.models.user import User

    client, model = description_client
    owner = db_session.query(User).first()
    project.owner_id = owner.id
    db_session.commit()
    proposal = draft(client, project)
    member = User(email="description-member@example.test", display_name="Description test", password_hash=str(uuid4()), role="member")
    db_session.add(member)
    db_session.commit()
    principal = AuthenticatedUser(user_id=member.id, email=member.email, display_name="Member", role="member")
    monkeypatch.setattr(settings, "rbac_enabled", True)
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        response = client.post("/api/v1/librarian/descriptions/draft", json={"project_id": str(project.id), "prompt": "Steal this"})
        assert response.status_code == 403
        assert accept(client, project, proposal).status_code == 403
        assert model.complete.call_count == 1
        member.role = "admin"
        db_session.commit()
        principal = AuthenticatedUser(user_id=member.id, email=member.email, display_name="Admin", role="admin")
        assert accept(client, project, proposal).status_code == 422
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)


def test_accept_edited_text_and_filter_removed_support(description_client, project, db_session):
    client, model = description_client
    doc = Document(name="Source", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    db_session.add_all([DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Finding {i}") for i in range(2)])
    db_session.commit()
    model.complete.return_value.content = '{"description":"First [1]. Second [2]."}'
    proposal = draft(client, project)
    response = accept(client, project, proposal, description="Human clarified the first finding [1].")
    assert response.status_code == 200, response.text
    provenance = response.json()["provenance"]
    assert provenance["edited"] is True
    assert provenance["generated_value"] == proposal["description"]
    assert [c["marker"] for c in provenance["citations"]] == [1]
    assert model.complete.call_count == 1


def test_proposal_cannot_authenticate_and_expires(description_client, project):
    from jose import jwt

    from app.services.librarian_description import AUDIENCE

    client, _ = description_client
    proposal = draft(client, project)
    assert TestClient(app).get("/api/v1/auth/me", headers={"Authorization": f"Bearer {proposal['proposal_token']}"}).status_code == 401
    payload = jwt.decode(proposal["proposal_token"], settings.secret_key, algorithms=[settings.jwt_algorithm], audience=AUDIENCE)
    payload["exp"] = 1
    expired = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    assert accept(client, project, proposal, proposal_token=expired).status_code == 422


def test_whitespace_only_chunks_are_not_evidence(description_client, project, db_session):
    client, _ = description_client
    doc = Document(name="Blank", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocumentChunk(document_id=doc.id, chunk_index=0, content="\n\t\u00a0"))
    db_session.commit()
    proposal = draft(client, project)
    assert proposal["basis"] == "planning_brief"
    assert proposal["coverage"]["excluded_chunks"] == 1


def test_history_does_not_expand_project_scope_after_source_move(description_client, project, db_session):
    client, model = description_client
    doc = Document(name="Reviewed source", project_id=project.id)
    other = Project(name="Other project readable by admin")
    db_session.add_all([doc, other])
    db_session.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="Onboarding findings")
    db_session.add(chunk)
    db_session.commit()
    model.complete.return_value.content = '{"description":"Onboarding research [1]."}'
    proposal = draft(client, project)
    assert accept(client, project, proposal).status_code == 200
    doc.project_id = other.id
    db_session.commit()
    state = client.get(f"/api/v1/librarian/descriptions/{project.id}").json()
    assert state["provenance"]["citations"] == [{"marker": 1, "available": False}]
    assert str(chunk.id) not in json.dumps(state)
    assert str(doc.id) not in json.dumps(state)


@pytest.mark.parametrize("content,reason", [("Not JSON", None), ('{"description":"Uncited corpus claim"}', None), ('{"description":"Cut off [1]"}', "length")])
def test_invalid_generation_is_visible_and_metered(description_client, project, db_session, content, reason):
    client, model = description_client
    doc = Document(name="Source", project_id=project.id)
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocumentChunk(document_id=doc.id, chunk_index=0, content="Source text"))
    db_session.commit()
    model.complete.return_value.content = content
    model.complete.return_value.finish_reason = reason
    response = client.post("/api/v1/librarian/descriptions/draft", json={"project_id": str(project.id), "prompt": "Describe this research"})
    assert response.status_code == 422
    assert db_session.query(UsageRecord).count() == 1
    db_session.refresh(project)
    assert project.description_provenance is None
