"""Tests for the CMOS → TraceLab mission event bridge.

Covers:
- Event emission for all CMOS transition types (start, complete, block, unblock)
- Status mapping to correct MissionEventType
- Graceful degradation on failure
- SSE format correctness
- HTTP endpoint (POST /events/cmos)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.mission_events import (
    MissionEvent,
    MissionEventBus,
    MissionEventType,
    emit_cmos_mission_event,
    get_mission_event_bus,
)


@pytest.fixture(autouse=True)
def fresh_event_bus():
    """Reset the singleton event bus for each test."""
    import app.core.mission_events as mod

    original = mod._event_bus
    mod._event_bus = MissionEventBus()
    yield mod._event_bus
    mod._event_bus = original


class TestCmosEventTypes:
    """CMOS-specific event types exist in the enum."""

    def test_cmos_started_type(self):
        assert MissionEventType.CMOS_MISSION_STARTED.value == "cmos.mission.started"

    def test_cmos_completed_type(self):
        assert MissionEventType.CMOS_MISSION_COMPLETED.value == "cmos.mission.completed"

    def test_cmos_blocked_type(self):
        assert MissionEventType.CMOS_MISSION_BLOCKED.value == "cmos.mission.blocked"

    def test_cmos_unblocked_type(self):
        assert MissionEventType.CMOS_MISSION_UNBLOCKED.value == "cmos.mission.unblocked"

    def test_cmos_status_changed_type(self):
        assert MissionEventType.CMOS_MISSION_STATUS_CHANGED.value == "cmos.mission.status_changed"


class TestEmitCmosMissionEvent:
    """Tests for the emit_cmos_mission_event bridge function."""

    def test_emit_start_transition(self, fresh_event_bus):
        result = emit_cmos_mission_event(
            mission_id="T35.2",
            name="Mission Event Bridge",
            new_status="In Progress",
            previous_status="Queued",
        )

        assert result is True
        events = fresh_event_bus.get_recent_events()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "cmos.mission.started"
        assert event.mission_id == "T35.2"
        assert event.mission_title == "Mission Event Bridge"
        assert event.status == "in progress"
        assert event.previous_status == "queued"
        assert event.details["source"] == "cmos"

    def test_emit_complete_transition(self, fresh_event_bus):
        result = emit_cmos_mission_event(
            mission_id="T35.1",
            name="Graph L6 Quality Validation",
            new_status="Completed",
            previous_status="In Progress",
            notes="All tests passing",
        )

        assert result is True
        event = fresh_event_bus.get_recent_events()[0]
        assert event.event_type == "cmos.mission.completed"
        assert event.details["notes"] == "All tests passing"

    def test_emit_block_transition(self, fresh_event_bus):
        result = emit_cmos_mission_event(
            mission_id="T35.5",
            name="PG Sync Dedup Validation",
            new_status="Blocked",
            previous_status="In Progress",
            reason="Waiting for cmos-mcp fix",
        )

        assert result is True
        event = fresh_event_bus.get_recent_events()[0]
        assert event.event_type == "cmos.mission.blocked"
        assert event.details["reason"] == "Waiting for cmos-mcp fix"

    def test_emit_unblock_transition(self, fresh_event_bus):
        result = emit_cmos_mission_event(
            mission_id="T35.5",
            name="PG Sync Dedup Validation",
            new_status="Unblocked",
            previous_status="Blocked",
        )

        assert result is True
        event = fresh_event_bus.get_recent_events()[0]
        assert event.event_type == "cmos.mission.unblocked"

    def test_emit_unknown_status_falls_back(self, fresh_event_bus):
        result = emit_cmos_mission_event(
            mission_id="T35.3",
            name="Decision-Insight Linking",
            new_status="Current",
            previous_status="Queued",
        )

        assert result is True
        event = fresh_event_bus.get_recent_events()[0]
        assert event.event_type == "cmos.mission.status_changed"

    def test_emit_includes_sprint_id(self, fresh_event_bus):
        emit_cmos_mission_event(
            mission_id="T35.4",
            name="Telemetry Standardization",
            new_status="In Progress",
            sprint_id="sprint-35",
        )

        event = fresh_event_bus.get_recent_events()[0]
        assert event.details["sprint_id"] == "sprint-35"

    def test_emit_status_normalization(self, fresh_event_bus):
        """Status strings are normalized to lowercase."""
        emit_cmos_mission_event(
            mission_id="T35.1",
            name="Test",
            new_status="  IN PROGRESS  ",
            previous_status="  QUEUED  ",
        )

        event = fresh_event_bus.get_recent_events()[0]
        assert event.status == "in progress"
        assert event.previous_status == "queued"

    def test_emit_none_previous_status(self, fresh_event_bus):
        emit_cmos_mission_event(
            mission_id="T35.1",
            name="Test",
            new_status="In Progress",
            previous_status=None,
        )

        event = fresh_event_bus.get_recent_events()[0]
        assert event.previous_status is None


class TestCmosBridgeGracefulDegradation:
    """Bridge must never crash TraceLab, even if event bus fails."""

    def test_returns_false_on_bus_failure(self):
        with patch(
            "app.core.mission_events.get_mission_event_bus",
            side_effect=RuntimeError("bus unavailable"),
        ):
            result = emit_cmos_mission_event(
                mission_id="T35.2",
                name="Test",
                new_status="In Progress",
            )

        assert result is False

    def test_returns_false_on_emit_failure(self):
        mock_bus = MagicMock()
        mock_bus.emit.side_effect = RuntimeError("emit failed")

        with patch(
            "app.core.mission_events.get_mission_event_bus",
            return_value=mock_bus,
        ):
            result = emit_cmos_mission_event(
                mission_id="T35.2",
                name="Test",
                new_status="Completed",
            )

        assert result is False

    def test_logs_warning_on_failure(self):
        with patch(
            "app.core.mission_events.get_mission_event_bus",
            side_effect=RuntimeError("bus unavailable"),
        ):
            with patch("app.core.mission_events.logger") as mock_logger:
                emit_cmos_mission_event(
                    mission_id="T35.2",
                    name="Test",
                    new_status="In Progress",
                )

                mock_logger.warning.assert_called_once()
                assert "CMOS bridge" in str(mock_logger.warning.call_args)


class TestCmosBridgeSSEFormat:
    """CMOS bridge events format correctly as SSE."""

    def test_sse_output_format(self, fresh_event_bus):
        emit_cmos_mission_event(
            mission_id="T35.2",
            name="Mission Event Bridge",
            new_status="Completed",
        )

        event = fresh_event_bus.get_recent_events()[0]
        sse = event.to_sse()

        assert sse.startswith("event: cmos.mission.completed\n")
        assert '"mission_id": "T35.2"' in sse
        assert '"source": "cmos"' in sse
        assert sse.endswith("\n\n")

    def test_event_bus_fans_out_cmos_events(self, fresh_event_bus):
        """CMOS events go through same fan-out as TraceLab events."""
        emit_cmos_mission_event(
            mission_id="T35.2",
            name="Test",
            new_status="In Progress",
        )

        assert len(fresh_event_bus.get_recent_events()) == 1


class TestCmosEndpoint:
    """Tests for the POST /events/cmos HTTP endpoint."""

    def test_endpoint_request_model(self):
        from app.api.v1.mission_events import CmosMissionEventRequest

        req = CmosMissionEventRequest(
            mission_id="T35.2",
            name="Mission Event Bridge",
            new_status="In Progress",
            previous_status="Queued",
            notes="Starting bridge work",
            sprint_id="sprint-35",
        )
        assert req.mission_id == "T35.2"
        assert req.name == "Mission Event Bridge"
        assert req.new_status == "In Progress"
        assert req.sprint_id == "sprint-35"

    def test_endpoint_request_model_minimal(self):
        from app.api.v1.mission_events import CmosMissionEventRequest

        req = CmosMissionEventRequest(
            mission_id="T35.2",
            name="Test",
            new_status="Completed",
        )
        assert req.previous_status is None
        assert req.notes is None
        assert req.reason is None
        assert req.sprint_id is None
