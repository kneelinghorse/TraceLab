"""DOCV-1: GET /documents/{id}/content and the slim, link-bearing document read."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ROLE_MEMBER, create_access_token
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.user import User
from app.models.workspace import Workspace

API = "/api/v1/documents"
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _user(db, role: str = ROLE_MEMBER) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test", display_name="Reader", password_hash=_HASH, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _project(db, owner: User | None = None, workspace: Workspace | None = None) -> Project:
    project = Project(
        name="Content project",
        owner_id=owner.id if owner else None,
        workspace_id=workspace.id if workspace else None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _document(db, project: Project, **fields) -> Document:
    document = Document(project_id=project.id, name="notes.txt", mime_type="text/plain", **fields)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _mission(db, project: Project, owner: User | None = None) -> Mission:
    mission = Mission(
        project_id=project.id,
        mission_id=f"DOCV-{uuid.uuid4().hex[:8]}",
        title="Source mission",
        objective="Produce a report",
        success_criteria=["A report exists"],
        owner_id=owner.id if owner else None,
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def _report(db, project: Project, owner: User | None = None, title: str = "Source report") -> Report:
    report = Report(project_id=project.id, title=title, content="# Findings", owner_id=owner.id if owner else None)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_content_requires_authentication(client, db_session):
    document = _document(db_session, _project(db_session), content="private")
    assert client.get(f"{API}/{document.id}/content").status_code == 401


def test_content_returns_404_for_unknown_and_deleted_documents(client, db_session, auth_headers):
    assert client.get(f"{API}/{uuid.uuid4()}/content", headers=auth_headers).status_code == 404
    document = _document(db_session, _project(db_session), content="gone")
    document.deleted_at = datetime.utcnow()
    db_session.commit()
    assert client.get(f"{API}/{document.id}/content", headers=auth_headers).status_code == 404


def test_content_is_forbidden_outside_the_callers_projects(client, db_session, rbac_on):
    outsider = _user(db_session)
    space = Workspace(name="Someone else's space")
    db_session.add(space)
    db_session.commit()
    project = _project(db_session, owner=None, workspace=space)
    document = _document(db_session, project, content="not yours")
    assert client.get(f"{API}/{document.id}/content", headers=_bearer(outsider)).status_code == 403
    assert client.get(f"{API}/{document.id}", headers=_bearer(outsider)).status_code == 403


def test_content_returns_the_full_text_without_raw_bytes(client, db_session, auth_headers):
    project = _project(db_session)
    text = "Line one.\n\nLine two is longer than any preview would show. " * 40
    document = _document(db_session, project, content=text, raw_content=b"\x00binary")
    response = client.get(f"{API}/{document.id}/content", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {
        "id": str(document.id),
        "name": "notes.txt",
        "mime_type": "text/plain",
        "source_origin": "upload",
        "content": text,
        "links": [],
    }


def test_content_serves_markdown_documents_with_their_mime_type(client, db_session, auth_headers):
    project = _project(db_session)
    document = Document(
        project_id=project.id,
        name="synthesis.md",
        mime_type="text/markdown",
        source_origin="synthesized",
        content="# Heading\n\n- bullet",
    )
    db_session.add(document)
    db_session.commit()
    payload = client.get(f"{API}/{document.id}/content", headers=auth_headers).json()
    assert payload["mime_type"] == "text/markdown"
    assert payload["source_origin"] == "synthesized"
    assert payload["content"] == "# Heading\n\n- bullet"


def test_content_is_null_when_nothing_was_extracted(client, db_session, auth_headers):
    document = _document(db_session, _project(db_session), content=None)
    payload = client.get(f"{API}/{document.id}/content", headers=auth_headers).json()
    assert payload["content"] is None


def test_links_include_only_readable_report_and_mission(client, db_session, rbac_on):
    member = _user(db_session)
    project = _project(db_session, owner=member)
    mission = _mission(db_session, project, owner=member)
    report = _report(db_session, project, owner=member)
    hidden = _report(db_session, project, owner=None, title="Hidden report")
    linked = _document(db_session, project, source_report_id=report.id, source_mission_id=mission.id, content="x")
    hidden_doc = _document(db_session, project, source_report_id=hidden.id, content="y")

    payload = client.get(f"{API}/{linked.id}/content", headers=_bearer(member)).json()
    assert payload["links"] == [
        {"kind": "report", "id": str(report.id), "title": "Source report", "href": f"/reports/{report.id}"},
        {"kind": "mission", "id": str(mission.id), "title": "Source mission", "href": f"/missions/{mission.id}"},
    ]
    detail = client.get(f"{API}/{linked.id}", headers=_bearer(member)).json()
    assert detail["links"] == payload["links"]
    assert detail["source_report_id"] == str(report.id)
    assert detail["source_mission_id"] == str(mission.id)

    payload = client.get(f"{API}/{hidden_doc.id}/content", headers=_bearer(member)).json()
    assert payload["links"] == []
    assert "Hidden report" not in payload.get("content", "")


def test_report_link_falls_back_to_the_missions_result_report(client, db_session, rbac_on):
    member = _user(db_session)
    project = _project(db_session, owner=member)
    mission = _mission(db_session, project, owner=member)
    report = _report(db_session, project, owner=member, title="Mission result")
    mission.result_report_id = report.id
    db_session.commit()
    document = _document(db_session, project, source_mission_id=mission.id, content="z")
    payload = client.get(f"{API}/{document.id}/content", headers=_bearer(member)).json()
    assert [link["kind"] for link in payload["links"]] == ["report", "mission"]
    assert payload["links"][0]["title"] == "Mission result"

    unreadable = _mission(db_session, project, owner=None)
    unreadable.result_report_id = report.id
    db_session.commit()
    orphan = _document(db_session, project, source_mission_id=unreadable.id, content="q")
    payload = client.get(f"{API}/{orphan.id}/content", headers=_bearer(member)).json()
    assert payload["links"] == []


def test_document_read_no_longer_ships_content_or_raw_bytes(client, db_session, auth_headers):
    project = _project(db_session)
    document = _document(db_session, project, content="full text", raw_content=b"bytes")
    db_session.add(DocumentChunk(document_id=document.id, chunk_index=0, content="full text", token_count=2))
    db_session.commit()
    payload = client.get(f"{API}/{document.id}", headers=auth_headers).json()
    assert "content" not in payload
    assert "raw_content" not in payload
    assert payload["preview"] == "full text"
    assert payload["source_origin"] == "upload"
    assert payload["links"] == []
    schema = app.openapi()["components"]["schemas"]["DocumentRead"]["properties"]
    assert "content" not in schema and "raw_content" not in schema
    assert "content" in app.openapi()["components"]["schemas"]["DocumentCreate"]["properties"]
