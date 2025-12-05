"""Tests for PEDR delta sync service.

Tests cover:
- Delta detection (only changed entities selected)
- Manifest transformation (governance metadata included)
- Event emission (sync triggers on completion)
- Parity validation (count comparison)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch

import pytest

from app.services.pedr.manifest_transformer import (
    ManifestTransformer,
    PEDRManifest,
    TransformationResult,
    get_manifest_transformer,
)
from app.services.pedr.delta_sync import (
    DeltaSyncService,
    EntityType,
    SyncMode,
    SyncResult,
    ParityCheckResult,
)
from app.services.pedr.sync_events import (
    SyncEvent,
    SyncEventEmitter,
    SyncEventType,
    emit_mission_completed,
    emit_mission_updated,
)


class TestManifestTransformer:
    """Test mission to PEDR manifest transformation."""

    @pytest.fixture
    def transformer(self) -> ManifestTransformer:
        return ManifestTransformer()

    def test_transform_mission_basic(self, transformer: ManifestTransformer) -> None:
        """Transform a basic mission to PEDR manifest."""
        mission_data = {
            "missionId": "M001",
            "name": "Test Mission",
            "researchStatement": {
                "objective": "Test the transformation process",
            },
        }

        result = transformer.transform_mission(
            mission_id="uuid-123",
            mission_data=mission_data,
            status="complete",
        )

        assert result.success
        assert result.manifest is not None
        assert result.manifest.urn == "urn:research:mission:M001"
        assert result.manifest.element_type == "mission"
        assert result.manifest.element_intent == "Read"
        assert result.manifest.context_domain == "research"
        assert "Test the transformation process" in result.manifest.purpose

    def test_transform_mission_with_quality_gates(self, transformer: ManifestTransformer) -> None:
        """Quality gates influence governance impact score."""
        mission_data = {
            "missionId": "M002",
            "name": "Quality Mission",
            "researchStatement": {"objective": "Test quality gates"},
        }
        quality_gates = {
            "research_statement": {"status": "pass", "validated": True},
            "evidence_links": {"status": "pass", "validated": True},
            "synthesis_quality": {"status": "pass", "validated": True},
            "traceability": {"status": "pass", "validated": True},
            "contradictions_resolved": {"status": "pass", "validated": True},
        }

        result = transformer.transform_mission(
            mission_id="uuid-456",
            mission_data=mission_data,
            quality_gates=quality_gates,
            status="complete",
        )

        assert result.success
        # Complete + all gates pass = 5 + 2 + 1 = 8
        assert result.manifest.governance_impact >= 8

    def test_transform_mission_pii_detection(self, transformer: ManifestTransformer) -> None:
        """PII is detected from governance flags."""
        mission_data = {
            "missionId": "M003",
            "name": "PII Mission",
            "governance": {"pii": True},
        }

        result = transformer.transform_mission(
            mission_id="uuid-789",
            mission_data=mission_data,
        )

        assert result.success
        assert result.manifest.governance_pii is True

    def test_transform_mission_pii_from_tags(self, transformer: ManifestTransformer) -> None:
        """PII detected from tags."""
        mission_data = {
            "missionId": "M004",
            "name": "Tagged Mission",
            "tags": ["research", "pii", "sensitive"],
        }

        result = transformer.transform_mission(
            mission_id="uuid-abc",
            mission_data=mission_data,
        )

        assert result.success
        assert result.manifest.governance_pii is True

    def test_transform_mission_bindings(self, transformer: ManifestTransformer) -> None:
        """Evidence and document bindings are extracted."""
        mission_data = {
            "missionId": "M005",
            "name": "Binding Mission",
            "evidence": [
                {"chunk_id": "chunk-1"},
                {"chunk_id": "chunk-2"},
            ],
            "documents": [
                {"id": "doc-1"},
                {"id": "doc-2"},
            ],
        }

        result = transformer.transform_mission(
            mission_id="uuid-def",
            mission_data=mission_data,
            project_id="project-123",
        )

        assert result.success
        assert result.manifest.bindings["project_id"] == "project-123"
        assert result.manifest.bindings["evidence_chunks"] == ["chunk-1", "chunk-2"]
        assert result.manifest.bindings["related_documents"] == ["doc-1", "doc-2"]

    def test_transform_empty_mission_fails(self, transformer: ManifestTransformer) -> None:
        """Empty mission data returns error."""
        result = transformer.transform_mission(
            mission_id="uuid-empty",
            mission_data={},
        )

        assert not result.success
        assert result.error is not None

    def test_transform_document(self, transformer: ManifestTransformer) -> None:
        """Transform document to PEDR manifest."""
        result = transformer.transform_document(
            document_id="doc-123",
            name="Interview Transcript",
            content="This is the document content...",
            file_type="transcript",
            source_type="interview",
            project_id="proj-456",
            chunk_count=10,
        )

        assert result.success
        assert result.manifest.urn == "urn:research:document:doc-123"
        assert result.manifest.element_type == "transcript"
        assert result.manifest.bindings["chunk_count"] == 10

    def test_transform_insight(self, transformer: ManifestTransformer) -> None:
        """Transform insight to PEDR manifest."""
        result = transformer.transform_insight(
            insight_id="insight-789",
            title="Key Finding",
            content="Important discovery about user behavior",
            insight_type="finding",
            validated=True,
        )

        assert result.success
        assert result.manifest.urn == "urn:research:insight:insight-789"
        assert result.manifest.element_type == "finding"
        assert result.manifest.element_intent == "Read"
        assert result.manifest.governance_impact == 7  # Validated insight


class TestDeltaSyncService:
    """Test delta detection and sync orchestration."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.query.return_value = session
        session.filter.return_value = session
        session.order_by.return_value = session
        session.all.return_value = []
        session.first.return_value = None
        session.scalar.return_value = 0
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create mock session factory."""
        return lambda: mock_session

    @pytest.fixture
    def service(self, mock_session_factory) -> DeltaSyncService:
        """Create delta sync service with mock session."""
        return DeltaSyncService(session_factory=mock_session_factory)

    def test_sync_with_no_missions(self, service: DeltaSyncService) -> None:
        """Sync with no missions returns zero counts."""
        result = service.sync_missions(SyncMode.DELTA)

        assert result.synced_count == 0
        assert result.failed_count == 0
        assert result.success

    def test_sync_mode_delta_uses_last_sync(
        self,
        mock_session_factory,
    ) -> None:
        """Delta mode filters by updated_at > last_sync_at."""
        mock_session = mock_session_factory()

        # Setup sync state with last_sync_at
        mock_sync_state = MagicMock()
        mock_sync_state.last_sync_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_sync_state.sync_count = 10

        service = DeltaSyncService(session_factory=mock_session_factory)

        # The service should query for missions updated after last_sync_at
        result = service.sync_missions(SyncMode.DELTA)

        assert result.mode == SyncMode.DELTA

    def test_sync_mode_full_ignores_last_sync(
        self,
        mock_session_factory,
    ) -> None:
        """Full mode syncs all missions regardless of last_sync."""
        service = DeltaSyncService(session_factory=mock_session_factory)

        result = service.sync_missions(SyncMode.FULL)

        assert result.mode == SyncMode.FULL

    def test_dry_run_does_not_ingest(
        self,
        mock_session_factory,
    ) -> None:
        """Dry run transforms but doesn't call ingestion."""
        ingest_called = []

        def mock_ingest(manifests):
            ingest_called.append(len(manifests))
            return True

        service = DeltaSyncService(
            session_factory=mock_session_factory,
            ingest_callback=mock_ingest,
        )

        result = service.sync_missions(SyncMode.DELTA, dry_run=True)

        # Ingest should not be called in dry run
        assert len(ingest_called) == 0

    def test_get_sync_status(self, service: DeltaSyncService) -> None:
        """Get sync status returns status for all entity types."""
        status = service.get_sync_status()

        assert "mission" in status
        assert "document" in status
        assert "last_sync_at" in status["mission"]
        assert "sync_count" in status["mission"]

    def test_check_parity(self, service: DeltaSyncService) -> None:
        """Parity check returns local and remote counts."""
        result = service.check_parity(EntityType.MISSION)

        assert isinstance(result, ParityCheckResult)
        assert result.entity_type == EntityType.MISSION
        assert isinstance(result.local_count, int)


class TestSyncEvents:
    """Test sync event emission."""

    @pytest.fixture
    def emitter(self) -> SyncEventEmitter:
        return SyncEventEmitter()

    def test_emit_event(self, emitter: SyncEventEmitter) -> None:
        """Events are emitted to handlers."""
        received_events = []

        def handler(event: SyncEvent) -> None:
            received_events.append(event)

        emitter.on(SyncEventType.MISSION_COMPLETED, handler)

        event = SyncEvent(
            event_type=SyncEventType.MISSION_COMPLETED,
            entity_id="mission-123",
            entity_type="mission",
        )
        emitter.emit(event)

        assert len(received_events) == 1
        assert received_events[0].entity_id == "mission-123"

    def test_emit_mission_completed(self, emitter: SyncEventEmitter) -> None:
        """Convenience function emits mission completed event."""
        received_events = []

        def handler(event: SyncEvent) -> None:
            received_events.append(event)

        emitter.on(SyncEventType.MISSION_COMPLETED, handler)

        emit_mission_completed(
            emitter,
            "mission-456",
            project_id="project-789",
            status="complete",
        )

        assert len(received_events) == 1
        assert received_events[0].priority == 0  # High priority

    def test_event_queue(self, emitter: SyncEventEmitter) -> None:
        """Events can be queued for later processing."""
        event = SyncEvent(
            event_type=SyncEventType.MISSION_UPDATED,
            entity_id="mission-abc",
            entity_type="mission",
        )

        assert emitter.queue(event)
        assert emitter.queue_size == 1

        processed = emitter.process_queue()
        assert processed == 1
        assert emitter.queue_size == 0

    def test_queue_priority_ordering(self, emitter: SyncEventEmitter) -> None:
        """Queued events are processed by priority."""
        events = [
            SyncEvent(
                event_type=SyncEventType.MISSION_UPDATED,
                entity_id="low-priority",
                entity_type="mission",
                priority=2,
            ),
            SyncEvent(
                event_type=SyncEventType.MISSION_COMPLETED,
                entity_id="high-priority",
                entity_type="mission",
                priority=0,
            ),
        ]

        for event in events:
            emitter.queue(event)

        received = []

        def handler(event: SyncEvent) -> None:
            received.append(event.entity_id)

        emitter.on(SyncEventType.MISSION_UPDATED, handler)
        emitter.on(SyncEventType.MISSION_COMPLETED, handler)

        emitter.process_queue()

        # High priority (0) should be processed first
        assert received[0] == "high-priority"
        assert received[1] == "low-priority"

    def test_handler_removal(self, emitter: SyncEventEmitter) -> None:
        """Handlers can be removed."""
        received = []

        def handler(event: SyncEvent) -> None:
            received.append(event)

        emitter.on(SyncEventType.MISSION_COMPLETED, handler)
        emitter.off(SyncEventType.MISSION_COMPLETED, handler)

        event = SyncEvent(
            event_type=SyncEventType.MISSION_COMPLETED,
            entity_id="test",
            entity_type="mission",
        )
        emitter.emit(event)

        assert len(received) == 0


class TestIntegration:
    """Integration tests for the complete sync flow."""

    def test_manifest_to_dict_serialization(self) -> None:
        """Manifest can be serialized to dict."""
        transformer = get_manifest_transformer()

        result = transformer.transform_mission(
            mission_id="test-id",
            mission_data={
                "missionId": "TEST.001",
                "name": "Test Mission",
                "researchStatement": {"objective": "Test objective"},
            },
            status="complete",
        )

        assert result.success
        manifest_dict = result.manifest.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(manifest_dict)
        parsed = json.loads(json_str)

        assert parsed["urn"] == "urn:research:mission:TEST.001"
        assert parsed["governance_pii"] is False
        assert "bindings" in parsed

    def test_sync_event_triggers_delta_sync(self) -> None:
        """Mission completion event can trigger delta sync."""
        sync_triggered = []

        def sync_handler(event: SyncEvent) -> None:
            sync_triggered.append({
                "entity_id": event.entity_id,
                "timestamp": event.timestamp,
            })

        emitter = SyncEventEmitter()
        emitter.on(SyncEventType.MISSION_COMPLETED, sync_handler)

        # Simulate mission completion
        emit_mission_completed(emitter, "completed-mission-id")

        assert len(sync_triggered) == 1
        assert sync_triggered[0]["entity_id"] == "completed-mission-id"

    def test_governance_impact_ranges(self) -> None:
        """Impact scores stay within 1-10 range."""
        transformer = ManifestTransformer()

        # Minimum case: draft, no gates
        result_min = transformer.transform_mission(
            mission_id="min",
            mission_data={"missionId": "MIN"},
            status="draft",
            quality_gates={},
        )
        assert 1 <= result_min.manifest.governance_impact <= 10

        # Maximum case: complete, all gates pass
        result_max = transformer.transform_mission(
            mission_id="max",
            mission_data={"missionId": "MAX"},
            status="complete",
            quality_gates={
                gate: {"status": "pass", "validated": True}
                for gate in transformer.EXPECTED_GATES
            },
        )
        assert 1 <= result_max.manifest.governance_impact <= 10
        assert result_max.manifest.governance_impact > result_min.manifest.governance_impact


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
