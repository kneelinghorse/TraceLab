"""Tests for the collections API endpoints."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.project import Project
from app.core.database import SessionLocal


def _create_test_project(db_session) -> Project:
    """Create a test project."""
    project = Project(name="Test Project", description="For testing")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_test_document(db_session, project_id: uuid.UUID) -> Document:
    """Create a test document."""
    doc = Document(
        project_id=project_id,
        name="Test Document",
        file_type="report",
        source_type="report",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _create_test_chunk(db_session, document_id: uuid.UUID, index: int = 0, content: str = "Test chunk content") -> DocumentChunk:
    """Create a test document chunk."""
    from sqlalchemy import text

    chunk = DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        content=content,
        content_tsv=text("''"),  # Empty tsvector for testing
        token_count=len(content.split()),
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def test_collection_crud_flow(auth_headers):
    """Create, list, get, update, and delete collections through the API."""
    client = TestClient(app)

    # Create a collection
    create_resp = client.post(
        "/api/v1/collections",
        json={
            "name": "Research Notes",
            "description": "Collection of important research snippets",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Research Notes"
    assert created["description"] == "Collection of important research snippets"
    assert created["item_count"] == 0
    collection_id = created["id"]

    # List collections
    list_resp = client.get("/api/v1/collections", headers=auth_headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert payload["data"][0]["id"] == collection_id

    # Get collection detail
    get_resp = client.get(f"/api/v1/collections/{collection_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["name"] == "Research Notes"
    assert detail["items"] == []

    # Update collection
    update_resp = client.put(
        f"/api/v1/collections/{collection_id}",
        json={"name": "Updated Research Notes", "description": "New description"},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Updated Research Notes"
    assert updated["description"] == "New description"

    # Delete collection
    delete_resp = client.delete(f"/api/v1/collections/{collection_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify deleted
    after_delete = client.get("/api/v1/collections", headers=auth_headers).json()
    assert after_delete["total"] == 0


def test_collection_not_found(auth_headers):
    """Test 404 responses for non-existent collections."""
    client = TestClient(app)
    fake_id = str(uuid.uuid4())

    get_resp = client.get(f"/api/v1/collections/{fake_id}", headers=auth_headers)
    assert get_resp.status_code == 404

    update_resp = client.put(
        f"/api/v1/collections/{fake_id}",
        json={"name": "New Name"},
        headers=auth_headers,
    )
    assert update_resp.status_code == 404

    delete_resp = client.delete(f"/api/v1/collections/{fake_id}", headers=auth_headers)
    assert delete_resp.status_code == 404


def test_collection_add_remove_chunks(auth_headers, db_session):
    """Test adding and removing chunks from a collection."""
    client = TestClient(app)

    # Create test data
    project = _create_test_project(db_session)
    document = _create_test_document(db_session, project.id)
    chunk1 = _create_test_chunk(db_session, document.id, 0, "First chunk content for testing")
    chunk2 = _create_test_chunk(db_session, document.id, 1, "Second chunk content for testing")

    # Create collection
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "Analysis Collection"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    collection_id = create_resp.json()["id"]

    # Add first chunk
    add_resp1 = client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": str(chunk1.id), "notes": "Important finding"},
        headers=auth_headers,
    )
    assert add_resp1.status_code == 201, add_resp1.text
    item1 = add_resp1.json()
    assert item1["chunk_id"] == str(chunk1.id)
    assert item1["notes"] == "Important finding"
    assert item1["chunk_content"] is not None

    # Add second chunk
    add_resp2 = client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": str(chunk2.id)},
        headers=auth_headers,
    )
    assert add_resp2.status_code == 201

    # Verify collection has 2 items
    detail_resp = client.get(f"/api/v1/collections/{collection_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["item_count"] == 2
    assert len(detail["items"]) == 2

    # Remove first chunk
    remove_resp = client.delete(
        f"/api/v1/collections/{collection_id}/chunks/{chunk1.id}",
        headers=auth_headers,
    )
    assert remove_resp.status_code == 204

    # Verify collection has 1 item
    detail_after = client.get(f"/api/v1/collections/{collection_id}", headers=auth_headers)
    assert detail_after.json()["item_count"] == 1


def test_collection_duplicate_chunk_rejected(auth_headers, db_session):
    """Test that adding the same chunk twice returns 400."""
    client = TestClient(app)

    # Create test data
    project = _create_test_project(db_session)
    document = _create_test_document(db_session, project.id)
    chunk = _create_test_chunk(db_session, document.id, 0, "Unique chunk")

    # Create collection
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "Dedup Test"},
        headers=auth_headers,
    )
    collection_id = create_resp.json()["id"]

    # Add chunk first time
    add_resp1 = client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": str(chunk.id)},
        headers=auth_headers,
    )
    assert add_resp1.status_code == 201

    # Try to add same chunk again
    add_resp2 = client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": str(chunk.id)},
        headers=auth_headers,
    )
    assert add_resp2.status_code == 400
    assert "already" in add_resp2.json()["detail"].lower()


def test_collection_invalid_chunk_rejected(auth_headers):
    """Test that adding a non-existent chunk returns 400."""
    client = TestClient(app)

    # Create collection
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "Invalid Chunk Test"},
        headers=auth_headers,
    )
    collection_id = create_resp.json()["id"]

    # Try to add non-existent chunk
    fake_chunk_id = str(uuid.uuid4())
    add_resp = client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": fake_chunk_id},
        headers=auth_headers,
    )
    assert add_resp.status_code == 400
    assert "not found" in add_resp.json()["detail"].lower()


def test_collection_remove_nonexistent_chunk(auth_headers, db_session):
    """Test that removing a chunk not in the collection returns 404."""
    client = TestClient(app)

    # Create test data
    project = _create_test_project(db_session)
    document = _create_test_document(db_session, project.id)
    chunk = _create_test_chunk(db_session, document.id, 0, "Orphan chunk")

    # Create collection
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "Remove Test"},
        headers=auth_headers,
    )
    collection_id = create_resp.json()["id"]

    # Try to remove chunk that was never added
    remove_resp = client.delete(
        f"/api/v1/collections/{collection_id}/chunks/{chunk.id}",
        headers=auth_headers,
    )
    assert remove_resp.status_code == 404


def test_collection_name_required(auth_headers):
    """Test that collection name is required."""
    client = TestClient(app)

    # Try to create with empty name
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "", "description": "No name"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 422  # Validation error


def test_collection_cascade_delete_items(auth_headers, db_session):
    """Test that deleting a collection also deletes its items."""
    client = TestClient(app)

    # Create test data
    project = _create_test_project(db_session)
    document = _create_test_document(db_session, project.id)
    chunk = _create_test_chunk(db_session, document.id, 0, "Will be cascaded")

    # Create collection and add chunk
    create_resp = client.post(
        "/api/v1/collections",
        json={"name": "Cascade Test"},
        headers=auth_headers,
    )
    collection_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/collections/{collection_id}/chunks",
        json={"chunk_id": str(chunk.id)},
        headers=auth_headers,
    )

    # Delete collection
    delete_resp = client.delete(f"/api/v1/collections/{collection_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify chunk still exists (only collection item should be deleted)
    from app.models.chunk import DocumentChunk
    session = SessionLocal()
    try:
        remaining_chunk = session.query(DocumentChunk).filter(DocumentChunk.id == chunk.id).one_or_none()
        assert remaining_chunk is not None, "Chunk should still exist after collection deletion"
    finally:
        session.close()
