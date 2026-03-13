"""Tests for the document download API endpoint."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.project import Project


@pytest.fixture
def client():
    """Provide a FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


def _create_project(db_session, name: str) -> Project:
    project = Project(name=name)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_document(
    db_session,
    project_id,
    name,
    *,
    file_path=None,
    mime_type="text/plain",
    processed=False,
    chunked=False,
):
    document = Document(
        project_id=project_id,
        name=name,
        file_path=file_path,
        mime_type=mime_type,
        file_type="report",
        processed=processed,
        chunked=chunked,
        embedded=False,
        validation_status="pending",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def test_download_document_success(
    client: TestClient, db_session, auth_headers, tmp_path
):
    """Test successful document download."""
    # Create a test file
    test_file = tmp_path / "test_document.txt"
    test_content = b"This is test document content for download."
    test_file.write_bytes(test_content)

    project = _create_project(db_session, "Test Project")
    document = _create_document(
        db_session,
        project.id,
        "test_document.txt",
        file_path=str(test_file),
        mime_type="text/plain",
    )

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.content == test_content
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "test_document.txt" in response.headers.get("content-disposition", "")


def test_download_document_not_found(client: TestClient, db_session, auth_headers):
    """Test 404 for non-existent document."""
    fake_id = uuid.uuid4()
    response = client.get(f"/api/v1/documents/{fake_id}/download", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_download_document_no_file_path(client: TestClient, db_session, auth_headers):
    """Test 400 when document has no associated file."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(
        db_session,
        project.id,
        "no_file_document.txt",
        file_path=None,
    )

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=auth_headers
    )
    assert response.status_code == 400
    assert "no associated file" in response.json()["detail"]


def test_download_document_file_missing_on_disk(
    client: TestClient, db_session, auth_headers
):
    """Test 404 when file path exists but file is missing from disk."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(
        db_session,
        project.id,
        "missing_file.txt",
        file_path="/nonexistent/path/to/file.txt",
    )

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=auth_headers
    )
    assert response.status_code == 404
    assert "not found on disk" in response.json()["detail"]


def test_download_document_binary_file(
    client: TestClient, db_session, auth_headers, tmp_path
):
    """Test downloading a binary file (PDF-like)."""
    # Create a test binary file
    test_file = tmp_path / "test_document.pdf"
    test_content = b"%PDF-1.4\nTest binary content\x00\x01\x02"
    test_file.write_bytes(test_content)

    project = _create_project(db_session, "Test Project")
    document = _create_document(
        db_session,
        project.id,
        "test_document.pdf",
        file_path=str(test_file),
        mime_type="application/pdf",
    )

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.content == test_content
    assert response.headers["content-type"] == "application/pdf"


def test_download_document_fallback_mime_type(
    client: TestClient, db_session, auth_headers, tmp_path
):
    """Test download with missing mime_type falls back to application/octet-stream."""
    test_file = tmp_path / "unknown_file.xyz"
    test_content = b"Unknown file type content"
    test_file.write_bytes(test_content)

    project = _create_project(db_session, "Test Project")
    document = _create_document(
        db_session,
        project.id,
        "unknown_file.xyz",
        file_path=str(test_file),
        mime_type=None,
    )

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.content == test_content
    assert response.headers["content-type"] == "application/octet-stream"
