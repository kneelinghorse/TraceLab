"""Tests for the document chunks API endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import DocumentChunk
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


def _create_document(db_session, project_id, name, *, processed=True, chunked=True):
    document = Document(
        project_id=project_id,
        name=name,
        file_type="report",
        processed=processed,
        chunked=chunked,
        embedded=False,
        validation_status="processed" if processed else "pending",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _create_chunk(
    db_session, document_id, chunk_index: int, content: str, token_count: int = 50
):
    chunk = DocumentChunk(
        document_id=document_id,
        chunk_index=chunk_index,
        content=content,
        content_tsv=content,  # Simplified for test; actual would use PostgreSQL tsvector
        token_count=token_count,
        start_char=chunk_index * 100,
        end_char=(chunk_index + 1) * 100,
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def test_list_document_chunks_empty(client: TestClient, db_session, auth_headers):
    """Test listing chunks for a document with no chunks."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(db_session, project.id, "Empty Doc", chunked=False)

    response = client.get(
        f"/api/v1/documents/{document.id}/chunks", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 0
    assert payload["data"] == []


def test_list_document_chunks_with_content(
    client: TestClient, db_session, auth_headers
):
    """Test listing chunks for a document with chunks."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(db_session, project.id, "Chunked Doc")

    _create_chunk(db_session, document.id, 0, "First chunk content", 45)
    _create_chunk(db_session, document.id, 1, "Second chunk content", 52)
    _create_chunk(db_session, document.id, 2, "Third chunk content", 48)

    response = client.get(
        f"/api/v1/documents/{document.id}/chunks", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["pagination"]["total"] == 3
    assert payload["pagination"]["pages"] == 1
    assert len(payload["data"]) == 3

    # Verify ordering by chunk_index
    assert payload["data"][0]["chunk_index"] == 0
    assert payload["data"][1]["chunk_index"] == 1
    assert payload["data"][2]["chunk_index"] == 2

    # Verify content is included
    assert payload["data"][0]["content"] == "First chunk content"
    assert payload["data"][0]["token_count"] == 45


def test_list_document_chunks_pagination(client: TestClient, db_session, auth_headers):
    """Test pagination for document chunks."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(db_session, project.id, "Many Chunks Doc")

    # Create 5 chunks
    for i in range(5):
        _create_chunk(db_session, document.id, i, f"Chunk {i} content")

    # First page
    response = client.get(
        f"/api/v1/documents/{document.id}/chunks?page=1&page_size=2",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 5
    assert payload["pagination"]["pages"] == 3
    assert len(payload["data"]) == 2
    assert payload["data"][0]["chunk_index"] == 0
    assert payload["data"][1]["chunk_index"] == 1

    # Second page
    response = client.get(
        f"/api/v1/documents/{document.id}/chunks?page=2&page_size=2",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 2
    assert payload["data"][0]["chunk_index"] == 2
    assert payload["data"][1]["chunk_index"] == 3

    # Last page
    response = client.get(
        f"/api/v1/documents/{document.id}/chunks?page=3&page_size=2",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 1
    assert payload["data"][0]["chunk_index"] == 4


def test_list_document_chunks_not_found(client: TestClient, db_session, auth_headers):
    """Test 404 for non-existent document."""
    import uuid

    fake_id = uuid.uuid4()
    response = client.get(f"/api/v1/documents/{fake_id}/chunks", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_list_document_chunks_includes_metadata(
    client: TestClient, db_session, auth_headers
):
    """Test that chunk response includes all expected fields."""
    project = _create_project(db_session, "Test Project")
    document = _create_document(db_session, project.id, "Metadata Test Doc")
    chunk = _create_chunk(db_session, document.id, 0, "Test content", 60)

    response = client.get(
        f"/api/v1/documents/{document.id}/chunks", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()

    chunk_data = payload["data"][0]
    assert "id" in chunk_data
    assert "document_id" in chunk_data
    assert "chunk_index" in chunk_data
    assert "content" in chunk_data
    assert "token_count" in chunk_data
    assert "start_char" in chunk_data
    assert "end_char" in chunk_data
    assert "created_at" in chunk_data
    assert str(chunk.id) == chunk_data["id"]
