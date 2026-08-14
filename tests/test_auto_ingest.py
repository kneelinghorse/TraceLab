"""Tests for auto-ingest service (B16.7).

Comprehensive tests covering:
- Auto-ingestion of result_markdown as document
- Document metadata (mission_id, deepsearch_job_id, auto_generated)
- Chunking and embedding via ingestion pipeline
- Integration with webhook handler
- Error handling

Note: These tests require PostgreSQL with the schema created via Alembic migrations.
The SQLAlchemy CheckConstraints in Mission model are not compatible with the
conftest.py's drop/create_all approach. Run with:

    DATABASE_URL=postgresql://... alembic upgrade head
    DATABASE_URL=postgresql://... pytest tests/test_auto_ingest.py -v

For unit tests that don't need the database, see TestAutoIngestSingleton.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest


# Lazy imports to allow schema tests to run without DB
def _get_mission_model():
    from app.models.mission import Mission

    return Mission


def _get_document_model():
    from app.models.document import Document

    return Document


def _get_project_model():
    from app.models.project import Project

    return Project


from app.services.auto_ingest import (
    AutoIngestError,
    AutoIngestService,
    auto_ingest_result,
    get_auto_ingest_service,
)
from app.services.document_ingestion import DocumentIngestionService

# Note: Tests skip reset_database_and_reports fixture due to Mission model's
# SQLite-specific json_type() CheckConstraint that's incompatible with PostgreSQL.
# Tests use existing database schema (created via Alembic migrations).


@pytest.fixture
def mission(db_session, project):
    """Create a mission for auto-ingest testing."""
    Mission = _get_mission_model()
    instance = Mission(
        project_id=project.id,
        mission_id=f"AI-{uuid.uuid4().hex[:8]}",
        title="Auto-Ingest Test Mission",
        objective="Test auto-ingestion of DeepSearch results",
        success_criteria=["Test criterion 1", "Test criterion 2"],
        status="completed",
        deepsearch_job_id=f"ds-job-test-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(instance)
    db_session.commit()
    db_session.refresh(instance)
    return instance


@pytest.fixture
def mission_without_project(db_session):
    """Create a mission without project_id for error testing."""
    Mission = _get_mission_model()
    instance = Mission(
        project_id=None,
        mission_id=f"AI-{uuid.uuid4().hex[:8]}",
        title="Orphan Mission",
        objective="Test mission without project",
        success_criteria=["Criterion"],
        status="completed",
    )
    db_session.add(instance)
    db_session.commit()
    db_session.refresh(instance)
    return instance


@pytest.fixture
def sample_markdown():
    """Sample markdown content for testing."""
    return """# Research Results

## Summary
This is a test research result from DeepSearch.

## Key Findings
1. Finding one
2. Finding two
3. Finding three

## Conclusion
The research was successful.
"""


@pytest.fixture
def mock_ingestion_service():
    """Mock ingestion service that simulates successful processing."""
    service = MagicMock(spec=DocumentIngestionService)
    service.process_document.return_value = {
        "status": "completed",
        "stages": {
            "extracted": {"status": "success"},
            "chunked": {"status": "success", "chunk_count": 3},
            "embedded": {"status": "skipped", "reason": "Test environment"},
        },
    }
    return service


class TestAutoIngestService:
    """Unit tests for AutoIngestService."""

    def test_auto_ingest_creates_document(self, db_session, mission, sample_markdown):
        """Test that auto_ingest_result creates a document record."""
        service = AutoIngestService(
            ingestion_service=MagicMock(
                spec=DocumentIngestionService,
                process_document=MagicMock(return_value={"status": "completed"}),
            )
        )

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document is not None
        assert document.id is not None
        assert document.project_id == mission.project_id

    def test_auto_ingest_document_filename(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document filename follows {mission_id}_report.md pattern."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.name == f"{mission.mission_id}_report.md"

    def test_auto_ingest_source_type_deepsearch(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document source_type is set to 'deepsearch'."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.source_type == "deepsearch"

    def test_auto_ingest_document_metadata(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document metadata includes mission_id, job_id, auto_generated."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.document_metadata is not None
        assert document.document_metadata["mission_id"] == mission.mission_id
        assert (
            document.document_metadata["deepsearch_job_id"] == mission.deepsearch_job_id
        )
        assert document.document_metadata["auto_generated"] is True

    def test_auto_ingest_updates_mission_result_document_ids(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that mission.result_document_ids is updated with new doc ID."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        # Ensure mission starts with no result_document_ids
        assert mission.result_document_ids is None or mission.result_document_ids == []

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        # Refresh mission to get updated data
        db_session.refresh(mission)

        assert mission.result_document_ids is not None
        assert str(document.id) in mission.result_document_ids

    def test_auto_ingest_document_content_stored(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that markdown content is stored in document."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.content == sample_markdown

    def test_auto_ingest_document_file_type(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document file_type is 'report'."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.file_type == "report"

    def test_auto_ingest_document_mime_type(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document mime_type is text/markdown."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document.mime_type == "text/markdown"

    def test_auto_ingest_document_file_size(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Test that document file_size is calculated correctly."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        expected_size = len(sample_markdown.encode("utf-8"))
        assert document.file_size == expected_size

    def test_auto_ingest_triggers_ingestion_pipeline(
        self, db_session, mission, sample_markdown
    ):
        """Test that ingestion pipeline is called with correct parameters."""
        mock_service = MagicMock(spec=DocumentIngestionService)
        mock_service.process_document.return_value = {"status": "completed"}

        service = AutoIngestService(ingestion_service=mock_service)

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        # Verify ingestion was called
        mock_service.process_document.assert_called_once()

        # Check call arguments
        call_kwargs = mock_service.process_document.call_args.kwargs
        assert call_kwargs["db"] == db_session
        assert call_kwargs["document_id"] == document.id
        assert call_kwargs["file_content"] == sample_markdown.encode("utf-8")


class TestAutoIngestErrorHandling:
    """Tests for error handling in auto-ingest."""

    def test_auto_ingest_raises_on_empty_markdown(self, db_session, mission):
        """Test that empty result_markdown raises AutoIngestError."""
        service = AutoIngestService()

        with pytest.raises(AutoIngestError, match="No result_markdown"):
            service.auto_ingest_result(
                db=db_session,
                mission=mission,
                result_markdown="",
            )

    def test_auto_ingest_raises_on_none_markdown(self, db_session, mission):
        """Test that None result_markdown raises AutoIngestError."""
        service = AutoIngestService()

        with pytest.raises(AutoIngestError, match="No result_markdown"):
            service.auto_ingest_result(
                db=db_session,
                mission=mission,
                result_markdown=None,
            )

    def test_auto_ingest_raises_on_missing_project_id(
        self, db_session, mission_without_project, sample_markdown
    ):
        """Test that mission without project_id raises AutoIngestError."""
        service = AutoIngestService()

        with pytest.raises(AutoIngestError, match="has no project_id"):
            service.auto_ingest_result(
                db=db_session,
                mission=mission_without_project,
                result_markdown=sample_markdown,
            )

    def test_auto_ingest_raises_on_ingestion_failure(
        self, db_session, mission, sample_markdown
    ):
        """Test that ingestion pipeline failure raises AutoIngestError."""
        mock_service = MagicMock(spec=DocumentIngestionService)
        mock_service.process_document.return_value = {
            "status": "failed",
            "error": "Parsing failed",
        }

        service = AutoIngestService(ingestion_service=mock_service)

        with pytest.raises(AutoIngestError, match="Ingestion failed"):
            service.auto_ingest_result(
                db=db_session,
                mission=mission,
                result_markdown=sample_markdown,
            )

    def test_auto_ingest_wraps_unexpected_exceptions(
        self, db_session, mission, sample_markdown
    ):
        """Test that unexpected exceptions are wrapped in AutoIngestError."""
        mock_service = MagicMock(spec=DocumentIngestionService)
        mock_service.process_document.side_effect = RuntimeError("Unexpected error")

        service = AutoIngestService(ingestion_service=mock_service)

        with pytest.raises(AutoIngestError, match="Ingestion error"):
            service.auto_ingest_result(
                db=db_session,
                mission=mission,
                result_markdown=sample_markdown,
            )


class TestAutoIngestIntegration:
    """Integration tests for auto-ingest with real document processing."""

    @pytest.mark.skip(
        reason="Full pipeline test requires embedding service and Qdrant — chunks not created in SQLite test env"
    )
    def test_auto_ingest_full_pipeline(self, db_session, mission, sample_markdown):
        """Test auto-ingest with real ingestion service (no mocking).

        This test verifies the full integration but skips embedding since
        that requires OpenAI API key and Qdrant.
        """
        service = AutoIngestService()

        document = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        # Verify document was created and processed
        assert document is not None
        assert document.processed is True
        assert document.chunked is True
        # Embedded is False in test environment
        assert document.embedded is False

        # Verify chunks were created
        db_session.refresh(document)
        assert len(document.chunks) > 0

    def test_auto_ingest_replay_reuses_linked_document(
        self, db_session, mission, sample_markdown, mock_ingestion_service
    ):
        """Replaying the same mission result must not create another document."""
        service = AutoIngestService(ingestion_service=mock_ingestion_service)

        # First ingest
        doc1 = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        # Replaying the same completed mission returns its linked document.
        doc2 = service.auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        db_session.refresh(mission)

        assert doc2.id == doc1.id
        assert len(mission.result_document_ids) == 1
        assert str(doc1.id) in mission.result_document_ids


class TestAutoIngestSingleton:
    """Tests for module-level singleton and convenience function."""

    def test_get_auto_ingest_service_singleton(self):
        """Test that get_auto_ingest_service returns same instance."""
        # Reset singleton for test
        import app.services.auto_ingest as auto_ingest_module

        auto_ingest_module._service = None

        service1 = get_auto_ingest_service()
        service2 = get_auto_ingest_service()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_auto_ingest_result_convenience_function(
        self, db_session, mission, sample_markdown
    ):
        """Test the async convenience function."""
        # Reset singleton and inject mock
        import app.services.auto_ingest as auto_ingest_module

        mock_service = MagicMock(spec=DocumentIngestionService)
        mock_service.process_document.return_value = {"status": "completed"}
        auto_ingest_module._service = AutoIngestService(ingestion_service=mock_service)

        document = await auto_ingest_result(
            db=db_session,
            mission=mission,
            result_markdown=sample_markdown,
        )

        assert document is not None
        assert document.name == f"{mission.mission_id}_report.md"


class TestWebhookHandlerAutoIngestIntegration:
    """Tests for auto-ingest integration with webhook handler."""

    def test_webhook_success_triggers_auto_ingest(self, db_session, project):
        """Test that successful webhook triggers auto-ingest."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
            ExecutionMetadata,
        )
        from app.services.webhook_handler import WebhookHandler

        Mission = _get_mission_model()
        Document = _get_document_model()

        # Create mission with project
        mission = Mission(
            project_id=project.id,
            mission_id="WH-AUTO-001",
            title="Webhook Auto-Ingest Test",
            objective="Test auto-ingest via webhook",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        # Create mock services
        mock_ingestion = MagicMock(spec=DocumentIngestionService)

        def mark_search_ready(*, db, document_id, **_kwargs):
            document = db.query(Document).filter(Document.id == document_id).one()
            document.processed = True
            document.chunked = True
            document.embedded = True
            db.commit()
            return {"status": "completed"}

        mock_ingestion.process_document.side_effect = mark_search_ready
        mock_auto_ingest = AutoIngestService(ingestion_service=mock_ingestion)

        handler = WebhookHandler(auto_ingest_service=mock_auto_ingest)

        # Create webhook payload
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-wh-test",
            mission_id="WH-AUTO-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            execution_metadata=ExecutionMetadata(loops_executed=2),
            result_markdown="# Webhook Result\nContent from DeepSearch.",
        )

        # Process webhook
        updated_mission, status = handler.process_deepsearch_webhook(
            db_session, payload
        )

        # Verify mission was updated
        assert updated_mission.status == "completed"
        assert status == "completed"

        # Verify auto-ingest was triggered
        db_session.refresh(updated_mission)
        assert updated_mission.result_document_ids is not None
        assert len(updated_mission.result_document_ids) == 1

        # Verify document was created
        doc_id = uuid.UUID(updated_mission.result_document_ids[0])
        document = db_session.query(Document).filter(Document.id == doc_id).first()
        assert document is not None
        assert document.name == "WH-AUTO-001_report.md"
        assert document.source_type == "deepsearch"

    def test_webhook_success_no_result_markdown_skips_ingest(self, db_session, project):
        """Test that webhook without result_markdown skips auto-ingest."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
        )
        from app.services.webhook_handler import WebhookHandler

        Mission = _get_mission_model()

        mission = Mission(
            project_id=project.id,
            mission_id="WH-NO-MD-001",
            title="No Markdown Test",
            objective="Test webhook without markdown",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        handler = WebhookHandler()

        payload = DeepSearchWebhookPayload(
            job_id="ds-job-no-md",
            mission_id="WH-NO-MD-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown=None,  # No markdown
        )

        updated_mission, status = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert updated_mission.status == "completed"
        # No documents should be created
        assert (
            updated_mission.result_document_ids is None
            or updated_mission.result_document_ids == []
        )

    def test_webhook_auto_ingest_failure_fails_loud_but_keeps_completion(
        self, db_session, project
    ):
        """A failed promotion is retryable without reverting DeepSearch completion."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
        )
        from app.services.webhook_handler import WebhookHandler, WebhookProcessingError

        Mission = _get_mission_model()

        mission = Mission(
            project_id=project.id,
            mission_id="WH-FAIL-001",
            title="Ingest Failure Test",
            objective="Test auto-ingest failure handling",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        # Create mock that fails
        mock_ingestion = MagicMock(spec=DocumentIngestionService)
        mock_ingestion.process_document.side_effect = RuntimeError("Ingestion failed")
        mock_auto_ingest = AutoIngestService(ingestion_service=mock_ingestion)

        handler = WebhookHandler(auto_ingest_service=mock_auto_ingest)

        payload = DeepSearchWebhookPayload(
            job_id="ds-job-fail",
            mission_id="WH-FAIL-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown="# Results\nThis will fail ingestion.",
        )

        with pytest.raises(WebhookProcessingError, match="materialization is incomplete"):
            handler.process_deepsearch_webhook(db_session, payload)

        db_session.refresh(mission)
        assert mission.status == "completed"
        assert not mission.result_document_ids
