"""Tests for the report promotion feature (B17.2).

Tests the ability to promote a mission's report to a searchable document,
running it through the chunking/embedding pipeline.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report


def _create_test_project(db_session) -> Project:
    """Create a test project."""
    project = Project(name="Test Project", description="For testing")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_test_report(db_session, project_id=None, title="Test Report") -> Report:
    """Create a test report."""
    report = Report(
        project_id=project_id,
        title=title,
        report_type="summary",
        content="# Test Report\n\nThis is test content.",
        status="draft",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


def _create_test_mission(
    db_session,
    mission_id: str = "TEST-001",
    title: str = "Test Mission",
    status: str = "draft",
    project_id=None,
    result_report_id=None,
) -> Mission:
    """Create a test mission."""
    mission = Mission(
        mission_id=mission_id,
        title=title,
        objective="Test objective",
        success_criteria=["Criterion 1", "Criterion 2"],
        status=status,
        project_id=project_id,
        result_report_id=result_report_id,
        context={"key": "value"},
        deliverables=["Deliverable 1"],
        tags=["test", "api"],
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


class TestReportPromotionSchema:
    """Tests for ReportPromotionResponse schema."""

    def test_schema_fields_exist(self):
        """Verify schema has required fields."""
        from app.schemas.mission import ReportPromotionResponse

        # Test creating an instance
        response = ReportPromotionResponse(
            document_id=uuid.uuid4(),
            document_name="Test Document",
            status="completed",
            message="Report promoted successfully",
            chunk_count=5,
        )
        assert response.document_id is not None
        assert response.document_name == "Test Document"
        assert response.status == "completed"
        assert response.chunk_count == 5


class TestReportPromotionService:
    """Tests for ReportPromotionService."""

    def test_service_module_exists(self):
        """Verify service module is importable."""
        from app.services.report_promotion import (
            ReportPromotionService,
            ReportPromotionError,
            ReportAlreadyPromotedError,
            get_report_promotion_service,
            promote_mission_report,
        )

        service = get_report_promotion_service()
        assert service is not None
        assert isinstance(service, ReportPromotionService)

    def test_promote_report_no_content_fails(self, db_session):
        """Promoting report with no content fails."""
        from app.services.report_promotion import (
            ReportPromotionService,
            ReportPromotionError,
        )

        project = _create_test_project(db_session)
        report = Report(
            project_id=project.id,
            title="Empty Report",
            report_type="summary",
            content="",  # Empty content
            status="draft",
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        mission = _create_test_mission(
            db_session,
            mission_id="PROMO-001",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        service = ReportPromotionService()
        with pytest.raises(ReportPromotionError, match="no content"):
            service.promote_report(db_session, mission, report)

    def test_promote_report_no_project_fails(self, db_session):
        """Promoting report from mission without project fails."""
        from app.services.report_promotion import (
            ReportPromotionService,
            ReportPromotionError,
        )

        report = _create_test_report(db_session)

        mission = _create_test_mission(
            db_session,
            mission_id="PROMO-002",
            status="completed",
            project_id=None,  # No project
            result_report_id=report.id,
        )

        service = ReportPromotionService()
        with pytest.raises(ReportPromotionError, match="no project_id"):
            service.promote_report(db_session, mission, report)

    def test_promote_report_already_promoted_fails(self, db_session):
        """Promoting already-promoted report fails with 409."""
        from app.services.report_promotion import (
            ReportPromotionService,
            ReportAlreadyPromotedError,
        )

        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)

        # Create an existing document with this report as source
        existing_doc = Document(
            project_id=project.id,
            name="Existing Document",
            source_report_id=report.id,
            content="Existing content",
        )
        db_session.add(existing_doc)
        db_session.commit()

        mission = _create_test_mission(
            db_session,
            mission_id="PROMO-003",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        service = ReportPromotionService()
        with pytest.raises(ReportAlreadyPromotedError, match="already been promoted"):
            service.promote_report(db_session, mission, report)

    @patch("app.services.report_promotion.DocumentIngestionService")
    def test_promote_report_success(self, mock_ingestion_class, db_session):
        """Successfully promote a report to a document."""
        from app.services.report_promotion import ReportPromotionService

        # Mock the ingestion service
        mock_ingestion = MagicMock()
        mock_ingestion.process_document.return_value = {"status": "success"}
        mock_ingestion_class.return_value = mock_ingestion

        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)

        mission = _create_test_mission(
            db_session,
            mission_id="PROMO-004",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        service = ReportPromotionService()
        document = service.promote_report(db_session, mission, report)

        assert document is not None
        assert document.project_id == project.id
        assert document.source_report_id == report.id
        assert document.source_mission_id == mission.id
        assert document.source_origin == "synthesized"
        assert document.file_type == "report"
        assert "Test Report" in document.name or "Test Mission" in document.name


class TestPromoteReportEndpoint:
    """Tests for POST /api/v1/missions/{id}/promote-report endpoint."""

    def test_promote_report_requires_auth(self):
        """Promote report endpoint requires authentication."""
        client = TestClient(app)
        response = client.post(f"/api/v1/missions/{uuid.uuid4()}/promote-report")
        assert response.status_code == 401

    def test_promote_report_mission_not_found(self, auth_headers):
        """Promote report returns 404 for non-existent mission."""
        client = TestClient(app)
        fake_id = uuid.uuid4()

        response = client.post(
            f"/api/v1/missions/{fake_id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_promote_report_mission_not_completed(self, auth_headers, db_session):
        """Promote report fails if mission is not completed."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)
        mission = _create_test_mission(
            db_session,
            mission_id="PROMOTE-001",
            status="draft",  # Not completed
            project_id=project.id,
            result_report_id=report.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "must be completed" in response.json()["detail"]

    def test_promote_report_mission_no_report(self, auth_headers, db_session):
        """Promote report fails if mission has no report."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="PROMOTE-002",
            status="completed",
            project_id=project.id,
            result_report_id=None,  # No report
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "no result report" in response.json()["detail"]

    def test_promote_report_already_promoted(self, auth_headers, db_session):
        """Promote report returns 409 if already promoted."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)

        # Create existing promoted document
        existing_doc = Document(
            project_id=project.id,
            name="Already Promoted",
            source_report_id=report.id,
            content="Existing",
        )
        db_session.add(existing_doc)
        db_session.commit()

        mission = _create_test_mission(
            db_session,
            mission_id="PROMOTE-003",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert "already been promoted" in response.json()["detail"]

    @patch("app.services.report_promotion.DocumentIngestionService")
    def test_promote_report_success(self, mock_ingestion_class, auth_headers, db_session):
        """Successfully promote a report via API."""
        client = TestClient(app)

        # Mock the ingestion service
        mock_ingestion = MagicMock()
        mock_ingestion.process_document.return_value = {"status": "success"}
        mock_ingestion_class.return_value = mock_ingestion

        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)
        mission = _create_test_mission(
            db_session,
            mission_id="PROMOTE-004",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "document_id" in data
        assert "document_name" in data
        assert "status" in data
        assert "message" in data
        assert data["status"] in ("processing", "completed")

    @patch("app.services.report_promotion.DocumentIngestionService")
    def test_promote_report_creates_document_with_provenance(
        self, mock_ingestion_class, auth_headers, db_session
    ):
        """Promoted document has correct provenance fields."""
        client = TestClient(app)

        # Mock the ingestion service
        mock_ingestion = MagicMock()
        mock_ingestion.process_document.return_value = {"status": "success"}
        mock_ingestion_class.return_value = mock_ingestion

        project = _create_test_project(db_session)
        report = _create_test_report(
            db_session, project_id=project.id, title="Provenance Test Report"
        )
        mission = _create_test_mission(
            db_session,
            mission_id="PROMOTE-005",
            title="Provenance Test Mission",
            status="completed",
            project_id=project.id,
            result_report_id=report.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/promote-report",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify document was created with correct provenance
        doc = db_session.query(Document).filter(
            Document.id == data["document_id"]
        ).first()
        assert doc is not None
        assert doc.source_report_id == report.id
        assert doc.source_mission_id == mission.id
        assert doc.source_origin == "synthesized"
        assert doc.project_id == project.id


class TestDocumentProvenanceFields:
    """Tests for the new document provenance fields."""

    def test_document_model_has_provenance_fields(self):
        """Document model has source_report_id, source_mission_id, source_origin."""
        from app.models.document import Document

        # Check column names exist
        assert hasattr(Document, "source_report_id")
        assert hasattr(Document, "source_mission_id")
        assert hasattr(Document, "source_origin")

    def test_document_can_be_created_with_provenance(self, db_session):
        """Document can be created with provenance fields."""
        project = _create_test_project(db_session)
        report = _create_test_report(db_session, project_id=project.id)

        mission = _create_test_mission(
            db_session,
            mission_id="DOC-001",
            status="completed",
            project_id=project.id,
        )

        doc = Document(
            project_id=project.id,
            name="Document with Provenance",
            content="Test content",
            source_report_id=report.id,
            source_mission_id=mission.id,
            source_origin="synthesized",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        assert doc.source_report_id == report.id
        assert doc.source_mission_id == mission.id
        assert doc.source_origin == "synthesized"

    def test_document_source_origin_defaults_to_upload(self, db_session):
        """Document source_origin defaults to 'upload'."""
        project = _create_test_project(db_session)

        doc = Document(
            project_id=project.id,
            name="Regular Upload",
            content="Test content",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        assert doc.source_origin == "upload"

    def test_query_documents_by_source_origin(self, db_session):
        """Can query documents by source_origin."""
        project = _create_test_project(db_session)

        # Create documents with different origins
        doc1 = Document(
            project_id=project.id,
            name="Upload Doc",
            content="Test",
            source_origin="upload",
        )
        doc2 = Document(
            project_id=project.id,
            name="Synthesized Doc",
            content="Test",
            source_origin="synthesized",
        )
        doc3 = Document(
            project_id=project.id,
            name="Imported Doc",
            content="Test",
            source_origin="imported",
        )
        db_session.add_all([doc1, doc2, doc3])
        db_session.commit()

        # Query by origin
        synthesized = db_session.query(Document).filter(
            Document.source_origin == "synthesized"
        ).all()
        assert len(synthesized) == 1
        assert synthesized[0].name == "Synthesized Doc"

        uploaded = db_session.query(Document).filter(
            Document.source_origin == "upload"
        ).all()
        assert len(uploaded) == 1
