"""Tests for the reports API endpoints."""
from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.project import Project
from app.models.report import Report, ReportSource
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


def _create_test_chunk(
    db_session, document_id: uuid.UUID, index: int = 0, content: str = "Test chunk content"
) -> DocumentChunk:
    """Create a test document chunk."""
    from sqlalchemy import text

    chunk = DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        content=content,
        content_tsv=text("''"),
        token_count=len(content.split()),
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def _create_test_collection(db_session, name: str = "Test Collection") -> Collection:
    """Create a test collection."""
    collection = Collection(name=name, description="For testing")
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)
    return collection


def _add_chunk_to_collection(db_session, collection_id: uuid.UUID, chunk_id: uuid.UUID):
    """Add a chunk to a collection."""
    item = CollectionItem(
        collection_id=str(collection_id),
        chunk_id=str(chunk_id),
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _mock_synthesis_result():
    """Return a mock synthesis result."""
    return {
        "content": "This is a synthesized report about the test content. [1]",
        "citations": [
            {
                "chunk_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "excerpt": "Test excerpt",
            }
        ],
        "tokens_used": 150,
        "truncated": False,
        "chunk_count": 2,
    }


class MockSynthesisService:
    """Mock synthesis service for testing."""

    def __init__(self, result=None):
        self.result = result or _mock_synthesis_result()
        self.call_args = []

    def synthesize(self, **kwargs):
        self.call_args.append(kwargs)
        return self.result


class TestReportCreate:
    """Tests for POST /api/v1/reports."""

    def test_create_report_with_collection(self, auth_headers, db_session):
        """Create a report from a collection."""
        from app.services.report_service import ReportService, get_report_service

        client = TestClient(app)

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk1 = _create_test_chunk(db_session, document.id, 0, "First chunk content")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Second chunk content")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, collection.id, chunk1.id)
        _add_chunk_to_collection(db_session, collection.id, chunk2.id)

        mock_synthesis = MockSynthesisService()
        mock_report_service = ReportService(synthesis_service=mock_synthesis)

        app.dependency_overrides[get_report_service] = lambda: mock_report_service
        try:
            response = client.post(
                "/api/v1/reports",
                json={
                    "title": "Test Report",
                    "collection_id": str(collection.id),
                    "project_id": str(project.id),
                    "format": "summary",
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["title"] == "Test Report"
        assert data["status"] == "draft"
        assert "content" in data
        assert data["tokens_used"] > 0
        assert "citations" in data

    def test_create_report_with_chunk_ids(self, auth_headers, db_session):
        """Create a report from specific chunks."""
        from app.services.report_service import ReportService, get_report_service

        client = TestClient(app)

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk1 = _create_test_chunk(db_session, document.id, 0, "First chunk")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Second chunk")

        mock_synthesis = MockSynthesisService()
        mock_report_service = ReportService(synthesis_service=mock_synthesis)

        app.dependency_overrides[get_report_service] = lambda: mock_report_service
        try:
            response = client.post(
                "/api/v1/reports",
                json={
                    "title": "Chunk Report",
                    "chunk_ids": [str(chunk1.id), str(chunk2.id)],
                    "format": "bullets",
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["title"] == "Chunk Report"

    def test_create_report_with_custom_prompt(self, auth_headers, db_session):
        """Create a report with a custom prompt."""
        from app.services.report_service import ReportService, get_report_service

        client = TestClient(app)

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Content")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, collection.id, chunk.id)

        mock_synthesis = MockSynthesisService()
        mock_report_service = ReportService(synthesis_service=mock_synthesis)

        app.dependency_overrides[get_report_service] = lambda: mock_report_service
        try:
            response = client.post(
                "/api/v1/reports",
                json={
                    "title": "Custom Prompt Report",
                    "collection_id": str(collection.id),
                    "prompt": "Focus on the key findings",
                    "format": "report",
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        assert len(mock_synthesis.call_args) == 1
        call_kwargs = mock_synthesis.call_args[0]
        assert call_kwargs["prompt"] == "Focus on the key findings"

    def test_create_report_requires_source(self, auth_headers):
        """Creating report without collection_id or chunk_ids fails."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/reports",
            json={"title": "Invalid Report"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "collection_id or chunk_ids" in response.json()["detail"].lower()

    def test_create_report_requires_title(self, auth_headers, db_session):
        """Creating report without title fails validation."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Content")

        response = client.post(
            "/api/v1/reports",
            json={
                "chunk_ids": [str(chunk.id)],
            },
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error


class TestReportList:
    """Tests for GET /api/v1/reports."""

    def test_list_reports_empty(self, auth_headers):
        """List reports when none exist."""
        client = TestClient(app)

        response = client.get("/api/v1/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_reports_with_data(self, auth_headers, db_session):
        """List reports when they exist."""
        client = TestClient(app)

        # Create report directly in DB
        report = Report(
            title="Existing Report",
            content="Some content",
            report_type="summary",
            status="draft",
            tokens_used=100,
            chunk_count=5,
        )
        db_session.add(report)
        db_session.commit()

        response = client.get("/api/v1/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Existing Report"

    def test_list_reports_filter_by_project(self, auth_headers, db_session):
        """List reports filtered by project."""
        client = TestClient(app)

        project = _create_test_project(db_session)

        # Create two reports, one with project
        report1 = Report(
            title="With Project",
            content="Content 1",
            report_type="summary",
            project_id=str(project.id),
        )
        report2 = Report(
            title="Without Project",
            content="Content 2",
            report_type="summary",
        )
        db_session.add_all([report1, report2])
        db_session.commit()

        response = client.get(
            f"/api/v1/reports?project_id={project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "With Project"

    def test_list_reports_filter_by_status(self, auth_headers, db_session):
        """List reports filtered by status."""
        client = TestClient(app)

        report1 = Report(
            title="Draft Report",
            content="Content 1",
            report_type="summary",
            status="draft",
        )
        report2 = Report(
            title="Final Report",
            content="Content 2",
            report_type="summary",
            status="final",
        )
        db_session.add_all([report1, report2])
        db_session.commit()

        response = client.get(
            "/api/v1/reports?status=final",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Final Report"

    def test_list_reports_pagination(self, auth_headers, db_session):
        """Test report list pagination."""
        client = TestClient(app)

        # Create 5 reports
        for i in range(5):
            report = Report(
                title=f"Report {i}",
                content=f"Content {i}",
                report_type="summary",
            )
            db_session.add(report)
        db_session.commit()

        # Get page 1 with 2 items
        response = client.get(
            "/api/v1/reports?page=1&page_size=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestReportGet:
    """Tests for GET /api/v1/reports/{id}."""

    def test_get_report(self, auth_headers, db_session):
        """Get a single report by ID."""
        client = TestClient(app)

        report = Report(
            title="Detail Report",
            content="Full content here",
            report_type="report",
            status="draft",
            tokens_used=200,
            chunk_count=3,
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        response = client.get(
            f"/api/v1/reports/{report.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(report.id)
        assert data["title"] == "Detail Report"
        assert data["content"] == "Full content here"
        assert data["report_type"] == "report"
        assert "sources" in data
        assert "updated_at" in data

    def test_get_report_with_sources(self, auth_headers, db_session):
        """Get report includes its sources."""
        client = TestClient(app)

        chunk_id = uuid.uuid4()
        collection_id = uuid.uuid4()

        report = Report(
            title="Report With Sources",
            content="Content",
            report_type="summary",
        )
        db_session.add(report)
        db_session.flush()

        source1 = ReportSource(
            report_id=report.id,
            source_type="collection",
            source_id=str(collection_id),
        )
        source2 = ReportSource(
            report_id=report.id,
            source_type="chunk",
            source_id=str(chunk_id),
        )
        db_session.add_all([source1, source2])
        db_session.commit()

        response = client.get(
            f"/api/v1/reports/{report.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 2

    def test_get_report_not_found(self, auth_headers):
        """Get non-existent report returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.get(
            f"/api/v1/reports/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestReportUpdate:
    """Tests for PUT /api/v1/reports/{id}."""

    def test_update_report_title(self, auth_headers, db_session):
        """Update report title."""
        client = TestClient(app)

        report = Report(
            title="Old Title",
            content="Content",
            report_type="summary",
        )
        db_session.add(report)
        db_session.commit()

        response = client.put(
            f"/api/v1/reports/{report.id}",
            json={"title": "New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"

    def test_update_report_status(self, auth_headers, db_session):
        """Update report status to final."""
        client = TestClient(app)

        report = Report(
            title="Draft Report",
            content="Content",
            report_type="summary",
            status="draft",
        )
        db_session.add(report)
        db_session.commit()

        response = client.put(
            f"/api/v1/reports/{report.id}",
            json={"status": "final"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "final"

    def test_update_report_both_fields(self, auth_headers, db_session):
        """Update both title and status."""
        client = TestClient(app)

        report = Report(
            title="Original",
            content="Content",
            report_type="summary",
            status="draft",
        )
        db_session.add(report)
        db_session.commit()

        response = client.put(
            f"/api/v1/reports/{report.id}",
            json={"title": "Updated", "status": "final"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated"
        assert data["status"] == "final"

    def test_update_report_not_found(self, auth_headers):
        """Update non-existent report returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.put(
            f"/api/v1/reports/{fake_id}",
            json={"title": "New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestReportDelete:
    """Tests for DELETE /api/v1/reports/{id}."""

    def test_delete_report(self, auth_headers, db_session):
        """Delete a report."""
        client = TestClient(app)

        report = Report(
            title="To Delete",
            content="Content",
            report_type="summary",
        )
        db_session.add(report)
        db_session.commit()
        report_id = str(report.id)

        response = client.delete(
            f"/api/v1/reports/{report_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify deleted
        verify_resp = client.get(
            f"/api/v1/reports/{report_id}",
            headers=auth_headers,
        )
        assert verify_resp.status_code == 404

    def test_delete_report_cascades_sources(self, auth_headers, db_session):
        """Deleting report also deletes its sources."""
        client = TestClient(app)

        report = Report(
            title="With Sources",
            content="Content",
            report_type="summary",
        )
        db_session.add(report)
        db_session.flush()

        source = ReportSource(
            report_id=report.id,
            source_type="chunk",
            source_id=str(uuid.uuid4()),
        )
        db_session.add(source)
        db_session.commit()
        report_id = str(report.id)

        response = client.delete(
            f"/api/v1/reports/{report_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify sources also deleted
        session = SessionLocal()
        try:
            remaining = session.query(ReportSource).filter(
                ReportSource.report_id == report_id
            ).all()
            assert len(remaining) == 0
        finally:
            session.close()

    def test_delete_report_not_found(self, auth_headers):
        """Delete non-existent report returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.delete(
            f"/api/v1/reports/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestReportFormats:
    """Tests for different output formats."""

    @pytest.mark.parametrize("format_type", ["summary", "report", "bullets", "markdown"])
    def test_create_report_all_formats(self, auth_headers, db_session, format_type):
        """Test creating reports with all format types."""
        from app.services.report_service import ReportService, get_report_service

        client = TestClient(app)

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Content")
        collection = _create_test_collection(db_session, f"Collection-{format_type}")
        _add_chunk_to_collection(db_session, collection.id, chunk.id)

        mock_synthesis = MockSynthesisService()
        mock_report_service = ReportService(synthesis_service=mock_synthesis)

        app.dependency_overrides[get_report_service] = lambda: mock_report_service
        try:
            response = client.post(
                "/api/v1/reports",
                json={
                    "title": f"Test {format_type}",
                    "collection_id": str(collection.id),
                    "format": format_type,
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201, f"Failed for format: {format_type}"
        assert len(mock_synthesis.call_args) == 1
        assert mock_synthesis.call_args[0]["output_format"] == format_type


class TestReportAuthentication:
    """Tests for authentication requirements."""

    def test_list_reports_requires_auth(self):
        """List reports requires authentication."""
        client = TestClient(app)
        response = client.get("/api/v1/reports")
        assert response.status_code == 401

    def test_create_report_requires_auth(self):
        """Create report requires authentication."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/reports",
            json={"title": "Test", "collection_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401

    def test_get_report_requires_auth(self):
        """Get report requires authentication."""
        client = TestClient(app)
        response = client.get(f"/api/v1/reports/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_update_report_requires_auth(self):
        """Update report requires authentication."""
        client = TestClient(app)
        response = client.put(
            f"/api/v1/reports/{uuid.uuid4()}",
            json={"title": "Test"},
        )
        assert response.status_code == 401

    def test_delete_report_requires_auth(self):
        """Delete report requires authentication."""
        client = TestClient(app)
        response = client.delete(f"/api/v1/reports/{uuid.uuid4()}")
        assert response.status_code == 401
