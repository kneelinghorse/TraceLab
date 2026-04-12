"""Tests for auto-report creation service (B16.8).

Comprehensive tests covering:
- Protocol to markdown formatting
- Report creation from protocol
- Source linking from document chunks
- Mission result_report_id update
- Error handling for edge cases
- Integration with webhook handler

Note: Database tests require a running PostgreSQL database due to PostgreSQL-specific
columns in the schema (content_tsv in document_chunks). Run with:
    DATABASE_URL=postgresql://... pytest tests/test_auto_report.py -v

Unit tests (TestFormatProtocolToMarkdown, TestAutoReportService::test_service_singleton)
can run without PostgreSQL.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.services.auto_report import (
    AutoReportError,
    AutoReportService,
    create_report_from_protocol,
    format_protocol_to_markdown,
    get_auto_report_service,
    get_document_chunks,
)


class TestFormatProtocolToMarkdown:
    """Tests for protocol to markdown conversion."""

    def test_format_basic_synthesis(self):
        """Format protocol with basic synthesis string."""
        protocol = {"synthesis": "This is a summary of findings."}
        result = format_protocol_to_markdown(protocol, "Test Mission")

        assert "# Research: Test Mission" in result
        assert "## Summary" in result
        assert "This is a summary of findings." in result

    def test_format_synthesis_with_key_findings(self):
        """Format protocol with structured synthesis."""
        protocol = {
            "synthesis": {
                "summary": "Overview of research.",
                "key_findings": [
                    "First important finding",
                    {"title": "Second Finding", "description": "Details here"},
                ],
            }
        }
        result = format_protocol_to_markdown(protocol, "Research Mission")

        assert "# Research: Research Mission" in result
        assert "## Summary" in result
        assert "Overview of research." in result
        assert "### Key Findings" in result
        assert "- First important finding" in result
        assert "- **Second Finding**: Details here" in result

    def test_format_findings_list(self):
        """Format protocol with findings array."""
        protocol = {
            "findings": [
                "Simple finding",
                {
                    "title": "Complex Finding",
                    "description": "With details",
                    "confidence": 0.95,
                },
            ]
        }
        result = format_protocol_to_markdown(protocol, "Findings Mission")

        assert "## Findings" in result
        assert "1. Simple finding" in result
        assert "### Complex Finding" in result
        assert "*Confidence: 95%*" in result
        assert "With details" in result

    def test_format_sources_list(self):
        """Format protocol with sources array."""
        protocol = {
            "sources": [
                "https://example.com/doc1",
                {
                    "url": "https://example.com/doc2",
                    "title": "Example Doc",
                    "relevance": 0.87,
                },
            ]
        }
        result = format_protocol_to_markdown(protocol, "Sourced Mission")

        assert "## Sources" in result
        assert "- https://example.com/doc1" in result
        assert "- [Example Doc](https://example.com/doc2)" in result
        assert "*(relevance: 87%)*" in result

    def test_format_quality_checkpoints(self):
        """Format protocol with quality checkpoints."""
        protocol = {
            "quality_checkpoints": [
                "Verified sources",
                {"name": "Cross-checked facts", "status": "passed"},
                {"name": "Pending review", "status": "pending"},
            ]
        }
        result = format_protocol_to_markdown(protocol, "Quality Mission")

        assert "## Quality Checkpoints" in result
        assert "- [x] Verified sources" in result
        assert "- [x] Cross-checked facts" in result
        assert "- [ ] Pending review" in result

    def test_format_empty_protocol_fallback(self):
        """Format protocol with no standard structure shows raw JSON."""
        protocol = {
            "custom_field": "custom_value",
            "nested": {"data": 123},
        }
        result = format_protocol_to_markdown(protocol, "Custom Mission")

        assert "## Protocol Data" in result
        assert "```json" in result
        assert '"custom_field": "custom_value"' in result

    def test_format_complete_protocol(self):
        """Format a complete protocol with all sections."""
        protocol = {
            "synthesis": {
                "summary": "Comprehensive research completed.",
                "key_findings": ["Finding 1", "Finding 2"],
            },
            "findings": [
                {"title": "Main Finding", "description": "Details", "confidence": 0.9}
            ],
            "sources": [
                {
                    "url": "https://source.com",
                    "title": "Primary Source",
                    "relevance": 0.95,
                }
            ],
            "quality_checkpoints": [{"name": "Sources verified", "status": "passed"}],
        }
        result = format_protocol_to_markdown(protocol, "Complete Mission")

        assert "# Research: Complete Mission" in result
        assert "## Summary" in result
        assert "## Findings" in result
        assert "## Sources" in result
        assert "## Quality Checkpoints" in result
        assert "*Generated automatically from DeepSearch results" in result


class TestGetDocumentChunks:
    """Tests for document chunk retrieval."""

    def test_get_chunks_returns_ordered_list(self, db_session):
        """Chunks are returned in order by chunk_index."""
        # Create project and document
        project = Project(name="Chunk Test Project")
        db_session.add(project)
        db_session.flush()

        doc = Document(
            project_id=project.id,
            name="test.md",
            file_type="markdown",
            content="Test content",
            file_size=100,
            mime_type="text/markdown",
        )
        db_session.add(doc)
        db_session.flush()

        # Create chunks out of order
        for i in [2, 0, 1]:
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                content=f"Chunk {i} content",
            )
            db_session.add(chunk)
        db_session.commit()

        chunks = get_document_chunks(db_session, doc.id, limit=10)

        assert len(chunks) == 3
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    def test_get_chunks_respects_limit(self, db_session):
        """Chunk retrieval respects limit parameter."""
        project = Project(name="Limit Test Project")
        db_session.add(project)
        db_session.flush()

        doc = Document(
            project_id=project.id,
            name="test.md",
            file_type="markdown",
            content="Test content",
            file_size=100,
            mime_type="text/markdown",
        )
        db_session.add(doc)
        db_session.flush()

        # Create 5 chunks
        for i in range(5):
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                content=f"Chunk {i}",
            )
            db_session.add(chunk)
        db_session.commit()

        chunks = get_document_chunks(db_session, doc.id, limit=3)

        assert len(chunks) == 3

    def test_get_chunks_empty_document(self, db_session):
        """Returns empty list for document with no chunks."""
        project = Project(name="Empty Chunks Project")
        db_session.add(project)
        db_session.flush()

        doc = Document(
            project_id=project.id,
            name="empty.md",
            file_type="markdown",
            content="No chunks",
            file_size=50,
            mime_type="text/markdown",
        )
        db_session.add(doc)
        db_session.commit()

        chunks = get_document_chunks(db_session, doc.id)

        assert chunks == []


class TestCreateReportFromProtocol:
    """Tests for report creation from protocol."""

    def _create_test_mission(
        self,
        db_session,
        mission_id: str = None,
        project_id: uuid.UUID = None,
    ) -> Mission:
        """Create a test mission with optional project."""
        if mission_id is None:
            mission_id = f"AR-{uuid.uuid4().hex[:8]}"
        if project_id is None:
            project = Project(name="Auto Report Test Project")
            db_session.add(project)
            db_session.flush()
            project_id = project.id

        mission = Mission(
            project_id=project_id,
            mission_id=mission_id,
            title="Auto Report Test Mission",
            objective="Test auto-report creation",
            success_criteria=["Criterion 1"],
            status="completed",
        )
        db_session.add(mission)
        db_session.commit()
        db_session.refresh(mission)
        return mission

    def test_create_report_basic(self, db_session):
        """Create a basic report from protocol."""
        mission = self._create_test_mission(db_session)
        protocol = {
            "synthesis": "Research findings summary.",
        }

        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.id is not None
        assert report.title == "Research: Auto Report Test Mission"
        assert report.report_type == "markdown"
        assert report.status == "draft"
        assert "Research findings summary." in report.content
        assert str(report.project_id) == str(mission.project_id)

    def test_create_report_updates_mission(self, db_session):
        """Report creation updates mission.result_report_id."""
        mission = self._create_test_mission(db_session)
        protocol = {"synthesis": "Test."}

        report = create_report_from_protocol(db_session, mission, protocol)

        db_session.refresh(mission)
        assert mission.result_report_id == report.id

    def test_create_report_links_document_chunks(self, db_session):
        """Report sources are linked from ingested document chunks."""
        project = Project(name="Chunks Link Test Project")
        db_session.add(project)
        db_session.flush()

        # Create document with chunks
        doc = Document(
            project_id=project.id,
            name="result.md",
            file_type="markdown",
            content="Document content",
            file_size=100,
            mime_type="text/markdown",
        )
        db_session.add(doc)
        db_session.flush()

        chunk_ids = []
        for i in range(3):
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                content=f"Chunk {i}",
            )
            db_session.add(chunk)
            db_session.flush()
            chunk_ids.append(str(chunk.id))
        db_session.commit()

        # Create mission with document reference
        mission = Mission(
            project_id=project.id,
            mission_id="CHUNKS-001",
            title="Chunks Test Mission",
            objective="Test chunk linking",
            success_criteria=["Criterion"],
            status="completed",
            result_document_ids=[str(doc.id)],
        )
        db_session.add(mission)
        db_session.commit()

        protocol = {"synthesis": "Linked sources."}

        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.chunk_count == 3
        sources = (
            db_session.query(ReportSource)
            .filter(ReportSource.report_id == report.id)
            .all()
        )
        assert len(sources) == 3
        assert all(s.source_type == "chunk" for s in sources)

    def test_create_report_no_protocol_raises(self, db_session):
        """Raises error when protocol is empty."""
        mission = self._create_test_mission(db_session)

        with pytest.raises(AutoReportError, match="No protocol data"):
            create_report_from_protocol(db_session, mission, {})

    def test_create_report_no_project_raises(self, db_session):
        """Raises error when mission has no project_id."""
        mission = Mission(
            mission_id="NO-PROJECT-001",
            title="No Project Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="completed",
            project_id=None,
        )
        db_session.add(mission)
        db_session.commit()

        with pytest.raises(AutoReportError, match="has no project_id"):
            create_report_from_protocol(db_session, mission, {"synthesis": "Test"})

    def test_create_report_content_hash(self, db_session):
        """Report has content hash for dedup."""
        mission = self._create_test_mission(db_session)
        protocol = {"synthesis": "Unique content."}

        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.content_hash is not None
        assert len(report.content_hash) == 64  # SHA256 hex

    def test_create_report_stores_metadata(self, db_session):
        """Report prompt includes auto-generated info."""
        mission = self._create_test_mission(db_session, mission_id="META-001")
        protocol = {"synthesis": "Test."}

        report = create_report_from_protocol(db_session, mission, protocol)

        assert "META-001" in report.prompt
        assert "Auto-generated" in report.prompt


class TestAutoReportService:
    """Tests for AutoReportService class."""

    def test_service_singleton(self):
        """get_auto_report_service returns singleton."""
        service1 = get_auto_report_service()
        service2 = get_auto_report_service()
        assert service1 is service2

    def test_service_create_report(self, db_session):
        """Service create_report_from_protocol delegates correctly."""
        project = Project(name="Service Test Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="SVC-001",
            title="Service Test Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="completed",
        )
        db_session.add(mission)
        db_session.commit()

        service = AutoReportService()
        report = service.create_report_from_protocol(
            db_session,
            mission,
            {"synthesis": "Service test."},
        )

        assert report.id is not None
        assert report.title == "Research: Service Test Mission"


class TestAutoReportIntegration:
    """Integration tests with webhook handler."""

    def test_webhook_handler_calls_auto_report(self, db_session):
        """Webhook handler invokes auto-report on success with protocol."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
        )
        from app.services.webhook_handler import WebhookHandler

        # Create project and mission
        project = Project(name="Webhook Integration Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="WH-AR-001",
            title="Webhook Auto Report Test",
            objective="Test webhook integration",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        # Mock auto-ingest to avoid document processing
        mock_auto_ingest = MagicMock()
        mock_document = MagicMock()
        mock_document.id = uuid.uuid4()
        mock_auto_ingest.auto_ingest_result.return_value = mock_document

        handler = WebhookHandler(auto_ingest_service=mock_auto_ingest)

        payload = DeepSearchWebhookPayload(
            job_id="ds-auto-report-test",
            mission_id="WH-AR-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown="# Results",
            result_protocol={"synthesis": "Webhook integration test."},
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert status_msg == "completed"
        db_session.refresh(updated_mission)
        assert updated_mission.result_report_id is not None

        # Verify report was created
        report = (
            db_session.query(Report)
            .filter(Report.id == updated_mission.result_report_id)
            .one()
        )
        assert "Webhook integration test." in report.content

    def test_webhook_handler_skips_without_protocol(self, db_session):
        """Webhook handler skips auto-report when no protocol."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
        )
        from app.services.webhook_handler import WebhookHandler

        project = Project(name="No Protocol Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="WH-NO-PROTO",
            title="No Protocol Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        handler = WebhookHandler()

        payload = DeepSearchWebhookPayload(
            job_id="ds-no-protocol",
            mission_id="WH-NO-PROTO",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown=None,
            result_protocol=None,  # No protocol
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert status_msg == "completed"
        db_session.refresh(updated_mission)
        assert updated_mission.result_report_id is None

    def test_webhook_handler_continues_on_report_error(self, db_session):
        """Webhook handler logs but doesn't fail on auto-report error."""
        from app.schemas.webhook import (
            DeepSearchWebhookPayload,
            DeepSearchWebhookStatus,
        )
        from app.services.webhook_handler import WebhookHandler

        project = Project(name="Error Test Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="WH-ERR-001",
            title="Error Test Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="in_progress",
        )
        db_session.add(mission)
        db_session.commit()

        # Mock auto-report to raise error
        mock_auto_report = MagicMock()
        mock_auto_report.create_report_from_protocol.side_effect = AutoReportError(
            "Test error"
        )

        handler = WebhookHandler(auto_report_service=mock_auto_report)

        payload = DeepSearchWebhookPayload(
            job_id="ds-error-test",
            mission_id="WH-ERR-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_protocol={"synthesis": "Test"},
        )

        # Should not raise - logs warning instead
        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert status_msg == "completed"
        assert updated_mission.status == "completed"


class TestEdgeCases:
    """Edge case tests for auto-report."""

    def test_invalid_document_id_in_mission(self, db_session):
        """Handles invalid document IDs gracefully."""
        project = Project(name="Invalid Doc ID Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="INVALID-DOC-001",
            title="Invalid Doc ID Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="completed",
            result_document_ids=["not-a-uuid", "also-invalid"],
        )
        db_session.add(mission)
        db_session.commit()

        protocol = {"synthesis": "Test with invalid doc IDs."}

        # Should not raise - logs warning instead
        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.id is not None
        assert report.chunk_count == 0  # No valid chunks linked

    def test_document_with_no_chunks(self, db_session):
        """Handles documents without chunks."""
        project = Project(name="No Chunks Doc Project")
        db_session.add(project)
        db_session.flush()

        doc = Document(
            project_id=project.id,
            name="no_chunks.md",
            file_type="markdown",
            content="Empty",
            file_size=5,
            mime_type="text/markdown",
        )
        db_session.add(doc)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="NO-CHUNKS-001",
            title="No Chunks Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="completed",
            result_document_ids=[str(doc.id)],
        )
        db_session.add(mission)
        db_session.commit()

        protocol = {"synthesis": "Test."}

        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.id is not None
        assert report.chunk_count == 0

    def test_protocol_with_nested_structure(self, db_session):
        """Handles deeply nested protocol structures."""
        project = Project(name="Nested Protocol Project")
        db_session.add(project)
        db_session.flush()

        mission = Mission(
            project_id=project.id,
            mission_id="NESTED-001",
            title="Nested Protocol Mission",
            objective="Test",
            success_criteria=["Criterion"],
            status="completed",
        )
        db_session.add(mission)
        db_session.commit()

        protocol = {
            "synthesis": {
                "summary": "Nested summary",
                "key_findings": [
                    {
                        "title": "F1",
                        "description": "Desc",
                        "metadata": {"nested": {"deep": True}},
                    }
                ],
            },
            "metadata": {
                "version": "1.0",
                "nested": {"deeply": {"nested": {"value": 42}}},
            },
        }

        report = create_report_from_protocol(db_session, mission, protocol)

        assert report.id is not None
        assert "Nested summary" in report.content
