"""Tests for soft delete functionality on projects and documents."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.project import Project
from app.services.document_query_service import DocumentQueryService
from app.services.project_query_service import ProjectQueryService
from app.services.soft_delete_service import DocumentSoftDeleteService

client = TestClient(app)


class TestSoftDeleteMixin:
    """Tests for the SoftDeleteMixin functionality."""

    def test_project_has_soft_delete_fields(self, db_session):
        """Project model should have deleted_at and deleted_by fields."""
        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()

        assert hasattr(project, "deleted_at")
        assert hasattr(project, "deleted_by")
        assert project.deleted_at is None
        assert project.deleted_by is None

    def test_document_has_soft_delete_fields(self, db_session, project):
        """Document model should have deleted_at and deleted_by fields."""
        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()

        assert hasattr(doc, "deleted_at")
        assert hasattr(doc, "deleted_by")
        assert doc.deleted_at is None
        assert doc.deleted_by is None

    def test_soft_delete_method(self, db_session):
        """soft_delete() should set deleted_at and deleted_by."""
        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()

        project.soft_delete(deleted_by="test_user")
        db_session.commit()

        assert project.deleted_at is not None
        assert project.deleted_by == "test_user"
        assert project.is_deleted is True

    def test_restore_method(self, db_session):
        """restore() should clear deleted_at and deleted_by."""
        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()

        project.soft_delete(deleted_by="test_user")
        db_session.commit()
        assert project.is_deleted is True

        project.restore()
        db_session.commit()

        assert project.deleted_at is None
        assert project.deleted_by is None
        assert project.is_deleted is False

    def test_is_deleted_property(self, db_session):
        """is_deleted property should correctly reflect deletion state."""
        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()

        assert project.is_deleted is False

        project.soft_delete()
        db_session.commit()

        assert project.is_deleted is True


class TestProjectSoftDelete:
    """Tests for project soft delete functionality."""

    def test_list_projects_excludes_deleted_by_default(self, db_session):
        """list_projects should exclude soft-deleted projects by default."""
        service = ProjectQueryService()

        # Create projects
        active = Project(name="Active Project")
        deleted = Project(name="Deleted Project")
        db_session.add_all([active, deleted])
        db_session.commit()

        # Soft delete one
        deleted.soft_delete()
        db_session.commit()

        # List without include_deleted
        projects, meta = service.list_projects(db_session, page=1, page_size=20)
        names = [p.name for p in projects]

        assert "Active Project" in names
        assert "Deleted Project" not in names
        assert meta.total == 1

    def test_list_projects_includes_deleted_when_requested(self, db_session):
        """list_projects with include_deleted=True should return all projects."""
        service = ProjectQueryService()

        active = Project(name="Active Project")
        deleted = Project(name="Deleted Project")
        db_session.add_all([active, deleted])
        db_session.commit()

        deleted.soft_delete()
        db_session.commit()

        projects, meta = service.list_projects(
            db_session, page=1, page_size=20, include_deleted=True
        )
        names = [p.name for p in projects]

        assert "Active Project" in names
        assert "Deleted Project" in names
        assert meta.total == 2

    def test_get_project_excludes_deleted_by_default(self, db_session):
        """get_project should return None for soft-deleted projects."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        project.soft_delete()
        db_session.commit()

        result = service.get_project(db_session, project_id)
        assert result is None

    def test_get_project_includes_deleted_when_requested(self, db_session):
        """get_project with include_deleted=True should return deleted projects."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        project.soft_delete()
        db_session.commit()

        result = service.get_project(db_session, project_id, include_deleted=True)
        assert result is not None
        assert result.name == "Test Project"

    def test_soft_delete_project_service(self, db_session):
        """soft_delete_project should mark project as deleted."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        result = service.soft_delete_project(db_session, project_id, deleted_by="admin")

        assert result is True
        db_session.refresh(project)
        assert project.is_deleted is True
        assert project.deleted_by == "admin"

    def test_soft_delete_project_returns_none_for_not_found(self, db_session):
        """soft_delete_project should return None for non-existent project."""
        service = ProjectQueryService()

        result = service.soft_delete_project(db_session, uuid4())
        assert result is None

    def test_soft_delete_project_returns_false_if_already_deleted(self, db_session):
        """soft_delete_project should return False if already deleted."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        service.soft_delete_project(db_session, project_id)
        result = service.soft_delete_project(db_session, project_id)

        assert result is False

    def test_restore_project_service(self, db_session):
        """restore_project should restore a soft-deleted project."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        service.soft_delete_project(db_session, project_id)
        result = service.restore_project(db_session, project_id)

        assert result is True
        db_session.refresh(project)
        assert project.is_deleted is False

    def test_restore_project_returns_none_for_not_found(self, db_session):
        """restore_project should return None for non-existent project."""
        service = ProjectQueryService()

        result = service.restore_project(db_session, uuid4())
        assert result is None

    def test_restore_project_returns_false_if_not_deleted(self, db_session):
        """restore_project should return False if project is not deleted."""
        service = ProjectQueryService()

        project = Project(name="Test Project")
        db_session.add(project)
        db_session.commit()
        project_id = project.id

        result = service.restore_project(db_session, project_id)
        assert result is False


class TestDocumentSoftDelete:
    """Tests for document soft delete functionality."""

    def test_list_documents_excludes_deleted_by_default(self, db_session, project):
        """list_documents should exclude soft-deleted documents by default."""
        service = DocumentQueryService()

        active = Document(name="active.txt", project_id=project.id)
        deleted = Document(name="deleted.txt", project_id=project.id)
        db_session.add_all([active, deleted])
        db_session.commit()

        deleted.soft_delete()
        db_session.commit()

        docs, meta = service.list_documents(db_session, page=1, page_size=20)
        names = [d.name for d in docs]

        assert "active.txt" in names
        assert "deleted.txt" not in names
        assert meta.total == 1

    def test_list_documents_includes_deleted_when_requested(self, db_session, project):
        """list_documents with include_deleted=True should return all documents."""
        service = DocumentQueryService()

        active = Document(name="active.txt", project_id=project.id)
        deleted = Document(name="deleted.txt", project_id=project.id)
        db_session.add_all([active, deleted])
        db_session.commit()

        deleted.soft_delete()
        db_session.commit()

        docs, meta = service.list_documents(
            db_session, page=1, page_size=20, include_deleted=True
        )
        names = [d.name for d in docs]

        assert "active.txt" in names
        assert "deleted.txt" in names
        assert meta.total == 2

    def test_get_document_excludes_deleted_by_default(self, db_session, project):
        """get_document should return None for soft-deleted documents."""
        service = DocumentQueryService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        doc.soft_delete()
        db_session.commit()

        result = service.get_document(db_session, doc_id)
        assert result is None

    def test_get_document_includes_deleted_when_requested(self, db_session, project):
        """get_document with include_deleted=True should return deleted documents."""
        service = DocumentQueryService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        doc.soft_delete()
        db_session.commit()

        result = service.get_document(db_session, doc_id, include_deleted=True)
        assert result is not None
        assert result.name == "test.txt"

    def test_soft_delete_document_service(self, db_session, project):
        """soft_delete_document should mark document as deleted."""
        service = DocumentSoftDeleteService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        result = service.soft_delete_document(db_session, doc_id, deleted_by="admin")

        assert result is True
        db_session.refresh(doc)
        assert doc.is_deleted is True
        assert doc.deleted_by == "admin"

    def test_soft_delete_document_returns_none_for_not_found(self, db_session):
        """soft_delete_document should return None for non-existent document."""
        service = DocumentSoftDeleteService()

        result = service.soft_delete_document(db_session, uuid4())
        assert result is None

    def test_soft_delete_document_returns_false_if_already_deleted(
        self, db_session, project
    ):
        """soft_delete_document should return False if already deleted."""
        service = DocumentSoftDeleteService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        service.soft_delete_document(db_session, doc_id)
        result = service.soft_delete_document(db_session, doc_id)

        assert result is False

    def test_restore_document_service(self, db_session, project):
        """restore_document should restore a soft-deleted document."""
        service = DocumentSoftDeleteService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        service.soft_delete_document(db_session, doc_id)
        result = service.restore_document(db_session, doc_id)

        assert result is True
        db_session.refresh(doc)
        assert doc.is_deleted is False

    def test_restore_document_returns_none_for_not_found(self, db_session):
        """restore_document should return None for non-existent document."""
        service = DocumentSoftDeleteService()

        result = service.restore_document(db_session, uuid4())
        assert result is None

    def test_restore_document_returns_false_if_not_deleted(self, db_session, project):
        """restore_document should return False if document is not deleted."""
        service = DocumentSoftDeleteService()

        doc = Document(name="test.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        result = service.restore_document(db_session, doc_id)
        assert result is False


class TestProjectStatsWithSoftDelete:
    """Tests for project stats filtering soft-deleted documents."""

    def test_stats_exclude_deleted_documents(self, db_session):
        """Project stats should not count soft-deleted documents."""
        service = ProjectQueryService()

        project = Project(name="Stats Test")
        db_session.add(project)
        db_session.commit()

        # Add documents
        doc1 = Document(name="active.txt", project_id=project.id)
        doc2 = Document(name="deleted.txt", project_id=project.id)
        db_session.add_all([doc1, doc2])
        db_session.commit()

        # Soft delete one
        doc2.soft_delete()
        db_session.commit()

        stats = service.get_project_stats(db_session, project.id)

        assert stats.document_count == 1


class TestAPIEndpointsWithSoftDelete:
    """Tests for API endpoints with soft delete support."""

    def test_delete_project_endpoint_soft_deletes(self, db_session, auth_headers):
        """DELETE /projects/{id} should soft delete, not hard delete."""
        project = Project(name="API Delete Test")
        db_session.add(project)
        db_session.commit()
        project_id = str(project.id)

        response = client.delete(
            f"/api/v1/projects/{project_id}?confirm=true", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Verify it's soft deleted (still in DB but marked)
        db_session.expire_all()
        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert project is not None
        assert project.is_deleted is True

    def test_delete_project_without_confirm_fails(self, db_session, auth_headers):
        """DELETE /projects/{id} without confirm should fail."""
        project = Project(name="API No Confirm Test")
        db_session.add(project)
        db_session.commit()
        project_id = str(project.id)

        response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)

        assert response.status_code == 400

    def test_restore_project_endpoint(self, db_session, auth_headers):
        """POST /projects/{id}/restore should restore soft-deleted project."""
        project = Project(name="API Restore Test")
        db_session.add(project)
        db_session.commit()
        project_id = str(project.id)

        # Soft delete first
        project.soft_delete()
        db_session.commit()

        response = client.post(
            f"/api/v1/projects/{project_id}/restore", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "restored"

        # Verify restored
        db_session.expire_all()
        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert project.is_deleted is False

    def test_restore_non_deleted_project_fails(self, db_session, auth_headers):
        """POST /projects/{id}/restore on non-deleted project should fail."""
        project = Project(name="API Restore Fail Test")
        db_session.add(project)
        db_session.commit()
        project_id = str(project.id)

        response = client.post(
            f"/api/v1/projects/{project_id}/restore", headers=auth_headers
        )

        assert response.status_code == 400
        assert "not deleted" in response.json()["detail"]

    def test_list_projects_with_include_deleted(self, db_session, auth_headers):
        """GET /projects?include_deleted=true should return deleted projects."""
        active = Project(name="Active API Test")
        deleted = Project(name="Deleted API Test")
        db_session.add_all([active, deleted])
        db_session.commit()

        deleted.soft_delete()
        db_session.commit()

        # Without include_deleted
        response = client.get("/api/v1/projects", headers=auth_headers)
        assert response.status_code == 200
        names = [p["name"] for p in response.json()["data"]]
        assert "Active API Test" in names
        assert "Deleted API Test" not in names

        # With include_deleted
        response = client.get(
            "/api/v1/projects?include_deleted=true", headers=auth_headers
        )
        assert response.status_code == 200
        names = [p["name"] for p in response.json()["data"]]
        assert "Active API Test" in names
        assert "Deleted API Test" in names

    def test_delete_document_endpoint_soft_deletes(
        self, db_session, project, auth_headers
    ):
        """DELETE /documents/{id} should soft delete, not hard delete."""
        doc = Document(name="api_delete.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = str(doc.id)

        response = client.delete(
            f"/api/v1/documents/{doc_id}?confirm=true", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Verify soft deleted
        db_session.expire_all()
        doc = db_session.query(Document).filter(Document.id == doc_id).first()
        assert doc is not None
        assert doc.is_deleted is True

    def test_restore_document_endpoint(self, db_session, project, auth_headers):
        """POST /documents/{id}/restore should restore soft-deleted document."""
        doc = Document(name="api_restore.txt", project_id=project.id)
        db_session.add(doc)
        db_session.commit()
        doc_id = str(doc.id)

        # Soft delete first
        doc.soft_delete()
        db_session.commit()

        response = client.post(
            f"/api/v1/documents/{doc_id}/restore", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "restored"

        # Verify restored
        db_session.expire_all()
        doc = db_session.query(Document).filter(Document.id == doc_id).first()
        assert doc.is_deleted is False

    def test_list_documents_with_include_deleted(
        self, db_session, project, auth_headers
    ):
        """GET /documents?include_deleted=true should return deleted documents."""
        active = Document(name="active_api.txt", project_id=project.id)
        deleted = Document(name="deleted_api.txt", project_id=project.id)
        db_session.add_all([active, deleted])
        db_session.commit()

        deleted.soft_delete()
        db_session.commit()

        # Without include_deleted
        response = client.get("/api/v1/documents", headers=auth_headers)
        assert response.status_code == 200
        names = [d["name"] for d in response.json()["data"]]
        assert "active_api.txt" in names
        assert "deleted_api.txt" not in names

        # With include_deleted
        response = client.get(
            "/api/v1/documents?include_deleted=true", headers=auth_headers
        )
        assert response.status_code == 200
        names = [d["name"] for d in response.json()["data"]]
        assert "active_api.txt" in names
        assert "deleted_api.txt" in names
