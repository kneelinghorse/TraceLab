"""Tests for DeepSearchClient with mocked responses."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.schemas.deepsearch import DeepSearchJobStatus
from app.services.deepsearch_client import (
    DeepSearchAPIError,
    DeepSearchClient,
    DeepSearchConfigurationError,
    DeepSearchConnectionError,
    DeepSearchTimeoutError,
    execute_mission,
    get_job_status,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings with valid DeepSearch configuration."""
    with patch("app.services.deepsearch_client.settings") as mock:
        mock.deepsearch_api_url = "https://deepsearch.example.com"
        mock.deepsearch_api_key = "test-api-key-12345"
        mock.deepsearch_timeout = 10.0
        mock.deepsearch_retries = 3
        mock.deepsearch_backoff_multiplier = 2.0
        mock.deepsearch_initial_backoff = 0.1  # Fast for tests
        yield mock


@pytest.fixture
def client(mock_settings) -> DeepSearchClient:
    """Create a DeepSearchClient with test configuration."""
    return DeepSearchClient()


@pytest.fixture
def execute_response_data() -> dict[str, Any]:
    """Sample execute response from DeepSearch."""
    return {
        "job_id": "job-abc-123",
        "mission_id": "mission-001",
        "status": "pending",
        "estimated_duration_seconds": 120,
        "created_at": "2025-12-07T01:00:00Z",
    }


@pytest.fixture
def status_response_pending() -> dict[str, Any]:
    """Sample pending status response."""
    return {
        "job_id": "job-abc-123",
        "mission_id": "mission-001",
        "status": "pending",
        "progress_percent": None,
        "current_phase": None,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "error_code": None,
    }


@pytest.fixture
def status_response_running() -> dict[str, Any]:
    """Sample running status response."""
    return {
        "job_id": "job-abc-123",
        "mission_id": "mission-001",
        "status": "running",
        "progress_percent": 50,
        "current_phase": "research",
        "started_at": "2025-12-07T01:01:00Z",
        "completed_at": None,
        "result": None,
        "error": None,
        "error_code": None,
    }


@pytest.fixture
def status_response_completed() -> dict[str, Any]:
    """Sample completed status response."""
    return {
        "job_id": "job-abc-123",
        "mission_id": "mission-001",
        "status": "completed",
        "progress_percent": 100,
        "current_phase": "finished",
        "started_at": "2025-12-07T01:01:00Z",
        "completed_at": "2025-12-07T01:05:00Z",
        "result": {"findings": ["result1", "result2"]},
        "error": None,
        "error_code": None,
    }


@pytest.fixture
def status_response_failed() -> dict[str, Any]:
    """Sample failed status response."""
    return {
        "job_id": "job-abc-123",
        "mission_id": "mission-001",
        "status": "failed",
        "progress_percent": 30,
        "current_phase": "research",
        "started_at": "2025-12-07T01:01:00Z",
        "completed_at": "2025-12-07T01:03:00Z",
        "result": None,
        "error": "Research phase failed due to API limit",
        "error_code": "RESEARCH_LIMIT_EXCEEDED",
    }


# =============================================================================
# Configuration Tests
# =============================================================================


class TestDeepSearchClientConfiguration:
    """Tests for client configuration and initialization."""

    def test_client_initialization_with_settings(self, mock_settings):
        """Client initializes correctly from settings."""
        client = DeepSearchClient()
        assert client.api_url == "https://deepsearch.example.com"
        assert client.api_key == "test-api-key-12345"
        assert client.timeout == 10.0
        assert client.max_retries == 3

    def test_client_initialization_with_params(self, mock_settings):
        """Client params override settings."""
        client = DeepSearchClient(
            api_url="https://custom.example.com",
            api_key="custom-key",
            timeout=30.0,
            max_retries=5,
        )
        assert client.api_url == "https://custom.example.com"
        assert client.api_key == "custom-key"
        assert client.timeout == 30.0
        assert client.max_retries == 5

    def test_client_strips_trailing_slash(self, mock_settings):
        """API URL has trailing slash stripped."""
        client = DeepSearchClient(api_url="https://example.com/api/")
        assert client.api_url == "https://example.com/api"

    def test_missing_api_url_raises_error(self, mock_settings):
        """Missing API URL raises configuration error."""
        mock_settings.deepsearch_api_url = None
        with pytest.raises(DeepSearchConfigurationError) as exc_info:
            DeepSearchClient()
        assert "API URL not configured" in str(exc_info.value)

    def test_missing_api_key_raises_error(self, mock_settings):
        """Missing API key raises configuration error."""
        mock_settings.deepsearch_api_key = None
        with pytest.raises(DeepSearchConfigurationError) as exc_info:
            DeepSearchClient()
        assert "API key not configured" in str(exc_info.value)


# =============================================================================
# Execute Mission Tests
# =============================================================================


class TestExecuteMission:
    """Tests for execute_mission method."""

    @pytest.mark.asyncio
    async def test_execute_mission_success(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Successful mission execution."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        response = await client.execute_mission(
            mission_id="mission-001",
            title="Test Mission",
            objective="Test objective",
            success_criteria=["Criterion 1", "Criterion 2"],
            callback_url="https://tracelab.example.com/webhook",
        )

        assert response.job_id == "job-abc-123"
        assert response.mission_id == "mission-001"
        assert response.status == DeepSearchJobStatus.PENDING
        assert response.estimated_duration_seconds == 120

    @pytest.mark.asyncio
    async def test_execute_mission_with_optional_params(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Execute mission with all optional parameters."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        response = await client.execute_mission(
            mission_id="mission-001",
            title="Test Mission",
            objective="Test objective",
            success_criteria=["Criterion 1"],
            callback_url="https://tracelab.example.com/webhook",
            context={"project": "TraceLab"},
            deliverables=["Report", "Analysis"],
            research_phases={"phase1": {"focus": "data gathering"}},
            metadata={"priority": "high"},
        )

        assert response.job_id == "job-abc-123"

        # Verify request body contained optional params
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["context"] == {"project": "TraceLab"}
        assert body["deliverables"] == ["Report", "Analysis"]
        assert "research_phases" in body
        assert body["metadata"] == {"priority": "high"}

    @pytest.mark.asyncio
    async def test_execute_mission_api_error(self, client, httpx_mock: HTTPXMock):
        """API error response handled correctly."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json={
                "error": "Invalid mission format",
                "error_code": "VALIDATION_ERROR",
                "details": {"field": "objective"},
            },
            status_code=400,
        )

        with pytest.raises(DeepSearchAPIError) as exc_info:
            await client.execute_mission(
                mission_id="mission-001",
                title="Test",
                objective="",
                success_criteria=["Test"],
                callback_url="https://example.com/webhook",
            )

        assert exc_info.value.error_code == "VALIDATION_ERROR"
        assert exc_info.value.status_code == 400
        assert "Invalid mission format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_mission_updates_stats(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Stats are updated on execute calls."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        assert client.stats.execute_requests == 0
        assert client.stats.execute_successes == 0

        await client.execute_mission(
            mission_id="mission-001",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        assert client.stats.execute_requests == 1
        assert client.stats.execute_successes == 1
        assert client.stats.execute_failures == 0


# =============================================================================
# Get Status Tests
# =============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_get_status_pending(
        self, client, httpx_mock: HTTPXMock, status_response_pending
    ):
        """Get pending job status."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_pending,
        )

        status = await client.get_status("job-abc-123")

        assert status.job_id == "job-abc-123"
        assert status.status == DeepSearchJobStatus.PENDING
        assert status.progress_percent is None

    @pytest.mark.asyncio
    async def test_get_status_running(
        self, client, httpx_mock: HTTPXMock, status_response_running
    ):
        """Get running job status with progress."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_running,
        )

        status = await client.get_status("job-abc-123")

        assert status.status == DeepSearchJobStatus.RUNNING
        assert status.progress_percent == 50
        assert status.current_phase == "research"

    @pytest.mark.asyncio
    async def test_get_status_completed(
        self, client, httpx_mock: HTTPXMock, status_response_completed
    ):
        """Get completed job status with result."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        status = await client.get_status("job-abc-123")

        assert status.status == DeepSearchJobStatus.COMPLETED
        assert status.progress_percent == 100
        assert status.result == {"findings": ["result1", "result2"]}

    @pytest.mark.asyncio
    async def test_get_status_failed(
        self, client, httpx_mock: HTTPXMock, status_response_failed
    ):
        """Get failed job status with error."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_failed,
        )

        status = await client.get_status("job-abc-123")

        assert status.status == DeepSearchJobStatus.FAILED
        assert status.error == "Research phase failed due to API limit"
        assert status.error_code == "RESEARCH_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client, httpx_mock: HTTPXMock):
        """Job not found returns API error."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/nonexistent-job/status",
            json={"error": "Job not found", "error_code": "NOT_FOUND"},
            status_code=404,
        )

        with pytest.raises(DeepSearchAPIError) as exc_info:
            await client.get_status("nonexistent-job")

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_code == "NOT_FOUND"


# =============================================================================
# Retry Logic Tests
# =============================================================================


class TestRetryLogic:
    """Tests for retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Retries on connection error then succeeds."""
        # First two attempts fail, third succeeds
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        response = await client.execute_mission(
            mission_id="mission-001",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        assert response.job_id == "job-abc-123"
        assert client.stats.total_retries == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Retries on timeout then succeeds."""
        httpx_mock.add_exception(httpx.ReadTimeout("Read timeout"))
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        response = await client.execute_mission(
            mission_id="mission-001",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        assert response.job_id == "job-abc-123"
        assert client.stats.total_retries == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_connection(
        self, client, httpx_mock: HTTPXMock
    ):
        """All retries exhausted raises connection error."""
        # All 3 attempts fail
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        with pytest.raises(DeepSearchConnectionError) as exc_info:
            await client.execute_mission(
                mission_id="mission-001",
                title="Test",
                objective="Test",
                success_criteria=["Test"],
                callback_url="https://example.com/webhook",
            )

        assert "Connection error" in str(exc_info.value)
        assert client.stats.execute_failures == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_timeout(self, client, httpx_mock: HTTPXMock):
        """All retries exhausted on timeout raises timeout error."""
        httpx_mock.add_exception(httpx.ReadTimeout("Timeout"))
        httpx_mock.add_exception(httpx.ReadTimeout("Timeout"))
        httpx_mock.add_exception(httpx.ReadTimeout("Timeout"))

        with pytest.raises(DeepSearchTimeoutError):
            await client.execute_mission(
                mission_id="mission-001",
                title="Test",
                objective="Test",
                success_criteria=["Test"],
                callback_url="https://example.com/webhook",
            )

    @pytest.mark.asyncio
    async def test_no_retry_on_api_error(self, client, httpx_mock: HTTPXMock):
        """API errors are not retried."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json={"error": "Bad request", "error_code": "BAD_REQUEST"},
            status_code=400,
        )

        with pytest.raises(DeepSearchAPIError):
            await client.execute_mission(
                mission_id="mission-001",
                title="Test",
                objective="Test",
                success_criteria=["Test"],
                callback_url="https://example.com/webhook",
            )

        # Only 1 request made (no retries)
        assert len(httpx_mock.get_requests()) == 1
        assert client.stats.total_retries == 0


# =============================================================================
# Wait for Completion Tests
# =============================================================================


class TestWaitForCompletion:
    """Tests for wait_for_completion polling method."""

    @pytest.mark.asyncio
    async def test_wait_for_completion_immediate(
        self, client, httpx_mock: HTTPXMock, status_response_completed
    ):
        """Job already completed returns immediately."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        status = await client.wait_for_completion("job-abc-123", poll_interval=0.1)

        assert status.status == DeepSearchJobStatus.COMPLETED
        assert len(httpx_mock.get_requests()) == 1

    @pytest.mark.asyncio
    async def test_wait_for_completion_polls(
        self,
        client,
        httpx_mock: HTTPXMock,
        status_response_pending,
        status_response_running,
        status_response_completed,
    ):
        """Polls until job completes."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_pending,
        )
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_running,
        )
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        status = await client.wait_for_completion("job-abc-123", poll_interval=0.05)

        assert status.status == DeepSearchJobStatus.COMPLETED
        assert len(httpx_mock.get_requests()) == 3

    @pytest.mark.asyncio
    async def test_wait_for_completion_returns_on_failure(
        self, client, httpx_mock: HTTPXMock, status_response_failed
    ):
        """Returns when job fails (terminal state)."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_failed,
        )

        status = await client.wait_for_completion("job-abc-123", poll_interval=0.1)

        assert status.status == DeepSearchJobStatus.FAILED
        assert status.error is not None

    @pytest.mark.asyncio
    @pytest.mark.httpx_mock(
        can_send_already_matched_responses=True,
        assert_all_responses_were_requested=False,
    )
    async def test_wait_for_completion_timeout(
        self, client, httpx_mock: HTTPXMock, status_response_running
    ):
        """Raises timeout if max_wait exceeded."""
        # Always return running status (multiple times for polling)
        for _ in range(10):
            httpx_mock.add_response(
                method="GET",
                url="https://deepsearch.example.com/missions/job-abc-123/status",
                json=status_response_running,
            )

        with pytest.raises(DeepSearchTimeoutError) as exc_info:
            await client.wait_for_completion(
                "job-abc-123", poll_interval=0.05, max_wait=0.1
            )

        assert "did not complete" in str(exc_info.value)


# =============================================================================
# Statistics Tests
# =============================================================================


class TestClientStats:
    """Tests for client statistics."""

    @pytest.mark.asyncio
    async def test_stats_tracking(
        self,
        client,
        httpx_mock: HTTPXMock,
        execute_response_data,
        status_response_completed,
    ):
        """Stats correctly track all operations."""
        # Setup responses
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        # Execute calls
        await client.execute_mission(
            mission_id="m1",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )
        await client.get_status("job-abc-123")

        # Verify stats
        stats = client.get_stats()
        assert stats["execute_requests"] == 1
        assert stats["execute_successes"] == 1
        assert stats["execute_success_rate"] == 1.0
        assert stats["status_requests"] == 1
        assert stats["status_successes"] == 1
        assert stats["status_success_rate"] == 1.0


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_execute_mission_function(
        self, mock_settings, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Convenience execute_mission function works."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        response = await execute_mission(
            mission_id="mission-001",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        assert response.job_id == "job-abc-123"

    @pytest.mark.asyncio
    async def test_get_job_status_function(
        self, mock_settings, httpx_mock: HTTPXMock, status_response_completed
    ):
        """Convenience get_job_status function works."""
        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        status = await get_job_status("job-abc-123")

        assert status.status == DeepSearchJobStatus.COMPLETED


# =============================================================================
# Request Header Tests
# =============================================================================


class TestRequestHeaders:
    """Tests for request headers."""

    @pytest.mark.asyncio
    async def test_authorization_header(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Authorization header is set correctly."""
        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        await client.execute_mission(
            mission_id="mission-001",
            title="Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        request = httpx_mock.get_request()
        assert request.headers["Authorization"] == "Bearer test-api-key-12345"
        assert request.headers["Content-Type"] == "application/json"
        assert "TraceLab" in request.headers["User-Agent"]


# =============================================================================
# Event Emission Tests
# =============================================================================


class TestDeepSearchEventEmission:
    """Verify DeepSearchClient emits mission events at key milestones."""

    @pytest.fixture(autouse=True)
    def _reset_event_bus(self):
        import app.core.mission_events as mod

        mod._event_bus = None
        yield
        mod._event_bus = None

    @pytest.mark.asyncio
    async def test_execute_emits_started_event(
        self, client, httpx_mock: HTTPXMock, execute_response_data
    ):
        """Successful execute_mission emits in_progress status change."""
        from app.core.mission_events import MissionEventType, get_mission_event_bus

        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json=execute_response_data,
        )

        await client.execute_mission(
            mission_id="EVT-001",
            title="Event Test",
            objective="Test",
            success_criteria=["Test"],
            callback_url="https://example.com/webhook",
        )

        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == MissionEventType.MISSION_STARTED.value
        assert events[0].mission_id == "EVT-001"
        assert events[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_execute_emits_failed_on_error(self, client, httpx_mock: HTTPXMock):
        """Failed execute_mission emits failed status change."""
        from app.core.mission_events import MissionEventType, get_mission_event_bus

        httpx_mock.add_response(
            method="POST",
            url="https://deepsearch.example.com/missions/execute",
            json={"error": "Server error", "error_code": "INTERNAL"},
            status_code=500,
        )

        with pytest.raises(DeepSearchAPIError):
            await client.execute_mission(
                mission_id="EVT-002",
                title="Fail Test",
                objective="Test",
                success_criteria=["Test"],
                callback_url="https://example.com/webhook",
            )

        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == MissionEventType.MISSION_FAILED.value
        assert events[0].mission_id == "EVT-002"

    @pytest.mark.asyncio
    async def test_wait_for_completion_emits_completed(
        self, client, httpx_mock: HTTPXMock, status_response_completed
    ):
        """wait_for_completion emits completed status change."""
        from app.core.mission_events import MissionEventType, get_mission_event_bus

        httpx_mock.add_response(
            method="GET",
            url="https://deepsearch.example.com/missions/job-abc-123/status",
            json=status_response_completed,
        )

        await client.wait_for_completion("job-abc-123", poll_interval=0.01)

        bus = get_mission_event_bus()
        events = bus.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == MissionEventType.MISSION_COMPLETED.value
