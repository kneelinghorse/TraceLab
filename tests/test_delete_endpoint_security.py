"""Tests for DELETE endpoint authentication and confirmation requirements (B17.3).

These tests verify that:
1. DELETE endpoints require authentication (returns 401 without auth)
2. DELETE endpoints require confirm=true query parameter (returns 400 without confirm)
3. DELETE operations succeed with both auth AND confirm=true
"""
from __future__ import annotations

from typing import List
from uuid import uuid4

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


def _create_project(db_session, name: str = "Test Project") -> Project:
    """Helper to create a project for testing."""
    project = Project(name=name)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_document(db_session, project_id, name: str = "Test Document") -> Document:
    """Helper to create a document for testing."""
    document = Document(
        project_id=project_id,
        name=name,
        file_type="report",
        processed=False,
        chunked=False,
        embedded=False,
        validation_status="pending",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


class TestProjectDeleteSecurity:
    """Tests for DELETE /api/v1/projects/{id} security."""

    def test_delete_project_requires_auth(self, client: TestClient, db_session):
        """DELETE /projects/{id} returns 401 without authentication."""
        project = _create_project(db_session)

        # Request without auth headers
        response = client.delete(f"/api/v1/projects/{project.id}?confirm=true")

        assert response.status_code == 401
        assert "Authorization" in response.json()["detail"] or "token" in response.json()["detail"].lower()

    def test_delete_project_requires_confirmation(self, client: TestClient, db_session, auth_headers):
        """DELETE /projects/{id} returns 400 without confirm=true."""
        project = _create_project(db_session)

        # Request with auth but no confirm parameter
        response = client.delete(f"/api/v1/projects/{project.id}", headers=auth_headers)

        assert response.status_code == 400
        assert "confirm=true" in response.json()["detail"]
        assert "WARNING" in response.json()["detail"]

    def test_delete_project_requires_confirm_true(self, client: TestClient, db_session, auth_headers):
        """DELETE /projects/{id} returns 400 when confirm=false."""
        project = _create_project(db_session)

        response = client.delete(f"/api/v1/projects/{project.id}?confirm=false", headers=auth_headers)

        assert response.status_code == 400
        assert "confirm=true" in response.json()["detail"]

    def test_delete_project_succeeds_with_auth_and_confirm(self, client: TestClient, db_session, auth_headers):
        """DELETE /projects/{id} succeeds with auth and confirm=true."""
        project = _create_project(db_session)
        project_id = project.id

        response = client.delete(f"/api/v1/projects/{project_id}?confirm=true", headers=auth_headers)

        assert response.status_code == 204

        # Verify project is actually deleted
        get_response = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_delete_nonexistent_project_returns_404(self, client: TestClient, auth_headers):
        """DELETE /projects/{id} returns 404 for nonexistent project (after auth/confirm check)."""
        fake_id = uuid4()

        response = client.delete(f"/api/v1/projects/{fake_id}?confirm=true", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDocumentDeleteSecurity:
    """Tests for DELETE /api/v1/documents/{id} security."""

    def test_delete_document_requires_auth(self, client: TestClient, db_session):
        """DELETE /documents/{id} returns 401 without authentication."""
        project = _create_project(db_session)
        document = _create_document(db_session, project.id)

        # Request without auth headers
        response = client.delete(f"/api/v1/documents/{document.id}?confirm=true")

        assert response.status_code == 401
        assert "Authorization" in response.json()["detail"] or "token" in response.json()["detail"].lower()

    def test_delete_document_requires_confirmation(self, client: TestClient, db_session, auth_headers):
        """DELETE /documents/{id} returns 400 without confirm=true."""
        project = _create_project(db_session)
        document = _create_document(db_session, project.id)

        # Request with auth but no confirm parameter
        response = client.delete(f"/api/v1/documents/{document.id}", headers=auth_headers)

        assert response.status_code == 400
        assert "confirm=true" in response.json()["detail"]
        assert "WARNING" in response.json()["detail"]

    def test_delete_document_requires_confirm_true(self, client: TestClient, db_session, auth_headers):
        """DELETE /documents/{id} returns 400 when confirm=false."""
        project = _create_project(db_session)
        document = _create_document(db_session, project.id)

        response = client.delete(f"/api/v1/documents/{document.id}?confirm=false", headers=auth_headers)

        assert response.status_code == 400
        assert "confirm=true" in response.json()["detail"]

    def test_delete_document_succeeds_with_auth_and_confirm(self, client: TestClient, db_session, auth_headers):
        """DELETE /documents/{id} succeeds with auth and confirm=true."""
        project = _create_project(db_session)
        document = _create_document(db_session, project.id)
        document_id = document.id

        response = client.delete(f"/api/v1/documents/{document_id}?confirm=true", headers=auth_headers)

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

        # Verify document is actually deleted
        get_response = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_delete_nonexistent_document_returns_404(self, client: TestClient, auth_headers):
        """DELETE /documents/{id} returns 404 for nonexistent document (after auth/confirm check)."""
        fake_id = uuid4()

        response = client.delete(f"/api/v1/documents/{fake_id}?confirm=true", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteEndpointErrorMessages:
    """Tests for clear, actionable error messages on DELETE endpoints."""

    def test_project_delete_error_explains_cascade(self, client: TestClient, db_session, auth_headers):
        """Project delete error message explains cascade consequences."""
        project = _create_project(db_session)

        response = client.delete(f"/api/v1/projects/{project.id}", headers=auth_headers)

        detail = response.json()["detail"]
        # Should mention what will be deleted
        assert any(word in detail.lower() for word in ["documents", "chunks", "insights", "missions"])

    def test_document_delete_error_explains_cascade(self, client: TestClient, db_session, auth_headers):
        """Document delete error message explains cascade consequences."""
        project = _create_project(db_session)
        document = _create_document(db_session, project.id)

        response = client.delete(f"/api/v1/documents/{document.id}", headers=auth_headers)

        detail = response.json()["detail"]
        # Should mention what will be deleted
        assert any(word in detail.lower() for word in ["chunks", "embeddings"])

    def test_auth_error_message_is_clear(self, client: TestClient, db_session):
        """Auth error message clearly indicates what's needed."""
        project = _create_project(db_session)

        response = client.delete(f"/api/v1/projects/{project.id}?confirm=true")

        assert response.status_code == 401
        # Should indicate authorization is needed
        detail = response.json()["detail"]
        assert "bearer" in detail.lower() or "api-key" in detail.lower() or "authorization" in detail.lower()
