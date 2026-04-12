"""Coverage for the project/document read APIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.project import Project


@pytest.fixture
def client():
    """Provide an authenticated FastAPI test client."""

    with TestClient(app) as test_client:
        yield test_client


def _create_projects(db_session, names: list[str]) -> list[Project]:
    projects: list[Project] = []
    for name in names:
        project = Project(name=name)
        db_session.add(project)
        projects.append(project)
    db_session.commit()
    for project in projects:
        db_session.refresh(project)
    return projects


def _create_document(db_session, project_id, name, *, processed=False):
    document = Document(
        project_id=project_id,
        name=name,
        file_type="report",
        processed=processed,
        chunked=processed,
        embedded=processed,
        validation_status="processed" if processed else "pending",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def test_projects_list_and_detail(client: TestClient, db_session, auth_headers):
    projects = _create_projects(
        db_session, ["Deep Dive", "Field Study", "Quant Sprint"]
    )

    first_page = client.get("/api/v1/projects?page=1&page_size=2", headers=auth_headers)
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["pagination"]["total"] == 3
    assert len(payload["data"]) == 2

    search = client.get("/api/v1/projects?search=Field", headers=auth_headers)
    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["pagination"]["total"] == 1
    assert search_payload["data"][0]["name"] == "Field Study"

    detail = client.get(f"/api/v1/projects/{projects[0].id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == str(projects[0].id)


def test_documents_list_filters(client: TestClient, db_session, auth_headers):
    project_a, project_b = _create_projects(db_session, ["Atlas", "Beacon"])

    _create_document(db_session, project_a.id, "Discovery Interview", processed=True)
    _create_document(db_session, project_a.id, "Discovery Notes", processed=False)
    _create_document(db_session, project_b.id, "Competitive Matrix", processed=True)

    project_filtered = client.get(
        f"/api/v1/documents?project_id={project_a.id}", headers=auth_headers
    )
    assert project_filtered.status_code == 200
    project_payload = project_filtered.json()
    assert project_payload["pagination"]["total"] == 2
    assert all(
        entry["project_id"] == str(project_a.id) for entry in project_payload["data"]
    )

    processed_only = client.get(
        "/api/v1/documents?processed=true", headers=auth_headers
    )
    assert processed_only.status_code == 200
    processed_payload = processed_only.json()
    assert processed_payload["pagination"]["total"] == 2
    assert all(entry["processed"] for entry in processed_payload["data"])

    search = client.get("/api/v1/documents?search=Matrix", headers=auth_headers)
    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["pagination"]["total"] == 1
    assert search_payload["data"][0]["name"] == "Competitive Matrix"
