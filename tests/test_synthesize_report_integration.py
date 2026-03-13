"""Tests for the synthesize-to-report integration feature (B15.8).

Tests the save_as_report parameter on the /api/v1/synthesize endpoint,
which allows persisting synthesis results as reports in a single API call.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.models.report import Report


def _create_test_project(db_session) -> Project:
    """Create a test project."""
    project = Project(name="Synth-Report Test Project", description="For testing")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_test_document(
    db_session, project_id: uuid.UUID, name: str = "Test Doc"
) -> Document:
    """Create a test document."""
    doc = Document(
        project_id=project_id,
        name=name,
        file_type="report",
        source_type="report",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _create_test_chunk(
    db_session,
    document_id: uuid.UUID,
    index: int = 0,
    content: str = "Test chunk content",
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
    collection = Collection(name=name, description="Test collection")
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)
    return collection


def _add_chunk_to_collection(
    db_session, collection_id: str, chunk_id: str
) -> CollectionItem:
    """Add a chunk to a collection."""
    item = CollectionItem(
        collection_id=collection_id,
        chunk_id=chunk_id,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _mock_openai_response(content: str = "This is a synthesis [1] with citations [2]."):
    """Create a mock OpenAI response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 500
    mock_usage.completion_tokens = 100
    mock_usage.total_tokens = 600

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    return mock_response


class TestSynthesizeToReportIntegration:
    """Tests for POST /api/v1/synthesize with save_as_report=true."""

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_without_save_as_report_returns_null_report_id(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that normal synthesis returns null report_id."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(
            db_session, document.id, 0, "Test content for synthesis."
        )
        collection = _create_test_collection(db_session, "Normal Synthesis")
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        # Request without save_as_report
        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] is None
        assert "content" in data

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_with_save_as_report_creates_report(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that synthesis with save_as_report=true creates a report."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "Key findings report [1] with analysis [2]."
        )
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk1 = _create_test_chunk(db_session, document.id, 0, "First finding.")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Second finding.")
        collection = _create_test_collection(db_session, "Report Synthesis")
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk1.id))
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk2.id))

        report_title = "Q4 Research Summary"

        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(collection.id),
                "save_as_report": True,
                "report_title": report_title,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] is not None
        assert "content" in data

        # Verify report was actually created in DB
        report_id = uuid.UUID(data["report_id"])
        report = db_session.query(Report).filter(Report.id == str(report_id)).first()
        assert report is not None
        assert report.title == report_title
        assert report.content == data["content"]
        assert report.status == "draft"

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_save_as_report_with_project_id(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that report is associated with project when project_id provided."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Test content.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(collection.id),
                "save_as_report": True,
                "report_title": "Project Report",
                "project_id": str(project.id),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] is not None

        # Verify project association
        report = db_session.query(Report).filter(Report.id == data["report_id"]).first()
        assert str(report.project_id) == str(project.id)

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_save_as_report_records_sources(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that report sources are recorded when saving synthesis."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Source content.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(collection.id),
                "save_as_report": True,
                "report_title": "Sourced Report",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify sources were recorded
        report = db_session.query(Report).filter(Report.id == data["report_id"]).first()
        assert len(report.sources) >= 1
        source_types = [s.source_type for s in report.sources]
        assert "collection" in source_types

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_with_chunk_ids_saves_as_report(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test save_as_report works with chunk_ids instead of collection_id."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk1 = _create_test_chunk(db_session, document.id, 0, "Chunk one.")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Chunk two.")

        response = client.post(
            "/api/v1/synthesize",
            json={
                "chunk_ids": [str(chunk1.id), str(chunk2.id)],
                "save_as_report": True,
                "report_title": "Chunk-based Report",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] is not None

        # Verify chunk sources
        report = db_session.query(Report).filter(Report.id == data["report_id"]).first()
        chunk_sources = [s for s in report.sources if s.source_type == "chunk"]
        assert len(chunk_sources) == 2


class TestSynthesizeToReportValidation:
    """Tests for request validation of save_as_report params."""

    def test_save_as_report_requires_report_title(self, auth_headers):
        """Test that save_as_report=true without report_title fails validation."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(uuid.uuid4()),
                "save_as_report": True,
                # Missing report_title
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "report_title" in response.text.lower()

    def test_report_title_without_save_as_report_is_ignored(
        self, auth_headers, db_session
    ):
        """Test that report_title without save_as_report is allowed (no-op)."""
        # This should pass validation but not create a report

        from app.schemas.synthesis import SynthesizeRequest

        # Should not raise
        request = SynthesizeRequest(
            collection_id=uuid.uuid4(),
            report_title="Ignored Title",  # save_as_report defaults to False
        )
        assert request.save_as_report is False
        assert request.report_title == "Ignored Title"

    def test_save_as_report_false_with_report_title_is_valid(self):
        """Test explicit save_as_report=false with report_title is valid."""
        from app.schemas.synthesis import SynthesizeRequest

        request = SynthesizeRequest(
            collection_id=uuid.uuid4(),
            save_as_report=False,
            report_title="Won't Be Used",
        )
        assert request.save_as_report is False


class TestSynthesizeSchemaExtensions:
    """Tests for the new schema fields."""

    def test_request_schema_has_save_as_report_field(self):
        """Test SynthesizeRequest has save_as_report field with default."""
        from app.schemas.synthesis import SynthesizeRequest

        request = SynthesizeRequest(collection_id=uuid.uuid4())
        assert hasattr(request, "save_as_report")
        assert request.save_as_report is False  # Default

    def test_request_schema_has_report_title_field(self):
        """Test SynthesizeRequest has report_title field."""
        from app.schemas.synthesis import SynthesizeRequest

        request = SynthesizeRequest(
            collection_id=uuid.uuid4(),
            save_as_report=True,
            report_title="My Report",
        )
        assert request.report_title == "My Report"

    def test_request_schema_has_project_id_field(self):
        """Test SynthesizeRequest has project_id field."""
        from app.schemas.synthesis import SynthesizeRequest

        project_id = uuid.uuid4()
        request = SynthesizeRequest(
            collection_id=uuid.uuid4(),
            save_as_report=True,
            report_title="Project Report",
            project_id=project_id,
        )
        assert request.project_id == project_id

    def test_response_schema_has_report_id_field(self):
        """Test SynthesizeResponse has report_id field."""
        from app.schemas.synthesis import SynthesizeResponse

        # With report_id
        response = SynthesizeResponse(
            content="Test",
            citations=[],
            tokens_used=100,
            chunk_count=1,
            report_id=uuid.uuid4(),
        )
        assert response.report_id is not None

        # Without report_id (null)
        response_no_report = SynthesizeResponse(
            content="Test",
            citations=[],
            tokens_used=100,
            chunk_count=1,
        )
        assert response_no_report.report_id is None

    def test_report_title_max_length(self):
        """Test report_title respects max_length constraint."""
        from pydantic import ValidationError

        from app.schemas.synthesis import SynthesizeRequest

        with pytest.raises(ValidationError):
            SynthesizeRequest(
                collection_id=uuid.uuid4(),
                save_as_report=True,
                report_title="x" * 300,  # Exceeds 255 char limit
            )


class TestBackwardCompatibility:
    """Tests ensuring existing synthesis calls work unchanged."""

    @patch("app.services.synthesis.OpenAI")
    def test_existing_calls_unchanged(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that existing API calls without new params work identically."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Test.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        # Old-style request (no new params)
        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(collection.id),
                "prompt": "Summarize this.",
                "format": "summary",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # All original fields present
        assert "content" in data
        assert "citations" in data
        assert "tokens_used" in data
        assert "truncated" in data
        assert "chunk_count" in data
        assert "cache_hit" in data
        # New field defaults to null
        assert data["report_id"] is None

    @patch("app.services.synthesis.OpenAI")
    def test_no_reports_created_without_flag(
        self, mock_openai_class, auth_headers, db_session
    ):
        """Test that reports are NOT created unless explicitly requested."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Test.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        # Count reports before
        reports_before = db_session.query(Report).count()

        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Count reports after - should be unchanged
        reports_after = db_session.query(Report).count()
        assert reports_after == reports_before
