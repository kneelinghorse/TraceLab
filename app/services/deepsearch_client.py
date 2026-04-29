"""HTTP client for DeepSearch API integration.

Provides typed methods for submitting missions and checking execution status.
Includes retry logic with exponential backoff and comprehensive error handling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.mission_events import (
    emit_mission_status_change,
)
from app.schemas.deepsearch import (
    DeepSearchErrorResponse,
    DeepSearchExecuteRequest,
    DeepSearchExecuteResponse,
    DeepSearchJobStatus,
    DeepSearchStatusResponse,
)

logger = logging.getLogger(__name__)


class DeepSearchClientError(Exception):
    """Base exception for DeepSearch client errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class DeepSearchConfigurationError(DeepSearchClientError):
    """Raised when DeepSearch client is not properly configured."""

    pass


class DeepSearchConnectionError(DeepSearchClientError):
    """Raised when connection to DeepSearch fails."""

    pass


class DeepSearchTimeoutError(DeepSearchClientError):
    """Raised when request to DeepSearch times out."""

    pass


class DeepSearchAPIError(DeepSearchClientError):
    """Raised when DeepSearch returns an error response."""

    pass


@dataclass(slots=True)
class DeepSearchClientStats:
    """Statistics for DeepSearch client operations."""

    execute_requests: int = 0
    execute_successes: int = 0
    execute_failures: int = 0
    status_requests: int = 0
    status_successes: int = 0
    status_failures: int = 0
    total_retries: int = 0

    @property
    def execute_success_rate(self) -> float:
        if self.execute_requests == 0:
            return 0.0
        return round(self.execute_successes / self.execute_requests, 3)

    @property
    def status_success_rate(self) -> float:
        if self.status_requests == 0:
            return 0.0
        return round(self.status_successes / self.status_requests, 3)


class DeepSearchClient:
    """Async HTTP client for DeepSearch mission execution API.

    Provides methods to:
    - Submit missions for execution via POST /missions/execute
    - Check job status via GET /missions/{job_id}/status

    Features:
    - Automatic retry with exponential backoff
    - Configurable timeouts
    - Typed request/response schemas
    - Comprehensive error handling
    """

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        backoff_multiplier: float | None = None,
        initial_backoff: float | None = None,
    ) -> None:
        """Initialize DeepSearch client.

        Args:
            api_url: DeepSearch API base URL. Falls back to settings.
            api_key: DeepSearch API key. Falls back to settings.
            timeout: Request timeout in seconds. Falls back to settings.
            max_retries: Maximum retry attempts. Falls back to settings.
            backoff_multiplier: Exponential backoff multiplier. Falls back to settings.
            initial_backoff: Initial backoff delay in seconds. Falls back to settings.

        Raises:
            DeepSearchConfigurationError: If required configuration is missing.
        """
        self.api_url = (api_url or settings.deepsearch_api_url or "").rstrip("/")
        self.api_key = api_key or settings.deepsearch_api_key
        self.timeout = timeout or settings.deepsearch_timeout
        self.max_retries = max_retries or settings.deepsearch_retries
        self.backoff_multiplier = (
            backoff_multiplier or settings.deepsearch_backoff_multiplier
        )
        self.initial_backoff = initial_backoff or settings.deepsearch_initial_backoff
        self.stats = DeepSearchClientStats()

        if not self.api_url:
            raise DeepSearchConfigurationError(
                "DeepSearch API URL not configured. "
                "Set DEEPSEARCH_API_URL environment variable or pass api_url parameter."
            )

        if not self.api_key:
            raise DeepSearchConfigurationError(
                "DeepSearch API key not configured. "
                "Set DEEPSEARCH_API_KEY environment variable or pass api_key parameter."
            )

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "TraceLab-DeepSearch-Client/1.0",
            "Accept": "application/json",
        }

    async def execute_mission(
        self,
        mission_id: str,
        title: str,
        objective: str,
        success_criteria: list[str],
        callback_url: str,
        *,
        context: dict[str, Any] | None = None,
        deliverables: list[str] | None = None,
        research_phases: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeepSearchExecuteResponse:
        """Submit a mission for execution on DeepSearch.

        Args:
            mission_id: Unique mission identifier.
            title: Mission title.
            objective: Primary mission objective.
            success_criteria: List of measurable success criteria.
            callback_url: Webhook URL for status updates.
            context: Additional context for mission execution.
            deliverables: Expected deliverables.
            research_phases: Research phase configuration.
            metadata: Additional metadata.

        Returns:
            DeepSearchExecuteResponse with job_id for tracking.

        Raises:
            DeepSearchConfigurationError: If client not properly configured.
            DeepSearchConnectionError: If connection fails.
            DeepSearchTimeoutError: If request times out.
            DeepSearchAPIError: If API returns an error.
        """
        self.stats.execute_requests += 1

        request = DeepSearchExecuteRequest(
            mission_id=mission_id,
            title=title,
            objective=objective,
            success_criteria=success_criteria,
            callback_url=callback_url,
            context=context,
            deliverables=deliverables,
            research_phases=research_phases,
            metadata=metadata,
        )

        try:
            response_data = await self._request_with_retry(
                method="POST",
                endpoint="/missions/execute",
                json_data=request.model_dump(mode="json", exclude_none=True),
            )
            self.stats.execute_successes += 1
            result = DeepSearchExecuteResponse.model_validate(response_data)

            # Emit mission started event
            emit_mission_status_change(
                mission_id=mission_id,
                title=title,
                new_status="in_progress",
                previous_status="queued",
            )
            return result

        except (DeepSearchConnectionError, DeepSearchTimeoutError, DeepSearchAPIError):
            self.stats.execute_failures += 1
            emit_mission_status_change(
                mission_id=mission_id,
                title=title,
                new_status="failed",
                previous_status="queued",
            )
            raise

    async def get_status(self, job_id: str) -> DeepSearchStatusResponse:
        """Get the current status of a DeepSearch job.

        Args:
            job_id: Job identifier from execute_mission response.

        Returns:
            DeepSearchStatusResponse with current job status.

        Raises:
            DeepSearchConnectionError: If connection fails.
            DeepSearchTimeoutError: If request times out.
            DeepSearchAPIError: If API returns an error (e.g., job not found).
        """
        self.stats.status_requests += 1

        try:
            response_data = await self._request_with_retry(
                method="GET",
                endpoint=f"/missions/{job_id}/status",
            )
            self.stats.status_successes += 1
            return DeepSearchStatusResponse.model_validate(response_data)

        except (DeepSearchConnectionError, DeepSearchTimeoutError, DeepSearchAPIError):
            self.stats.status_failures += 1
            raise

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with exponential backoff retry.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path.
            json_data: JSON request body (for POST/PUT).

        Returns:
            Parsed JSON response.

        Raises:
            DeepSearchConnectionError: If all connection attempts fail.
            DeepSearchTimeoutError: If all attempts timeout.
            DeepSearchAPIError: If API returns an error response.
        """
        url = f"{self.api_url}{endpoint}"
        backoff = self.initial_backoff
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=self._get_headers())
                    elif method.upper() == "POST":
                        response = await client.post(
                            url, headers=self._get_headers(), json=json_data
                        )
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                # Handle successful response
                if response.is_success:
                    return response.json()

                # Handle error response
                try:
                    error_data = response.json()
                    error_response = DeepSearchErrorResponse.model_validate(error_data)
                    raise DeepSearchAPIError(
                        error_response.error,
                        error_code=error_response.error_code,
                        status_code=response.status_code,
                        details=error_response.details,
                    )
                except (ValueError, KeyError):
                    raise DeepSearchAPIError(
                        f"DeepSearch API error: HTTP {response.status_code}",
                        status_code=response.status_code,
                        details={"response_text": response.text[:500]},
                    )

            except httpx.TimeoutException as e:
                last_error = DeepSearchTimeoutError(
                    f"Request timeout after {self.timeout}s: {e}"
                )
                logger.warning(
                    "DeepSearch request timeout (attempt %d/%d): %s %s",
                    attempt,
                    self.max_retries,
                    method,
                    endpoint,
                )

            except httpx.RequestError as e:
                last_error = DeepSearchConnectionError(
                    f"Connection error: {e}",
                    details={"url": url, "method": method},
                )
                logger.warning(
                    "DeepSearch connection error (attempt %d/%d): %s %s - %s",
                    attempt,
                    self.max_retries,
                    method,
                    endpoint,
                    str(e),
                )

            except DeepSearchAPIError:
                # Don't retry on API errors (4xx, 5xx with error body)
                raise

            # Retry with backoff
            if attempt < self.max_retries:
                self.stats.total_retries += 1
                logger.info(
                    "Retrying DeepSearch request in %.1fs (attempt %d/%d)",
                    backoff,
                    attempt + 1,
                    self.max_retries,
                )
                await asyncio.sleep(backoff)
                backoff *= self.backoff_multiplier

        # All retries exhausted
        if last_error:
            raise last_error

        raise DeepSearchConnectionError("All retry attempts exhausted")

    async def wait_for_completion(
        self,
        job_id: str,
        *,
        poll_interval: float = 5.0,
        max_wait: float = 300.0,
    ) -> DeepSearchStatusResponse:
        """Poll for job completion with timeout.

        Args:
            job_id: Job identifier to poll.
            poll_interval: Seconds between status checks.
            max_wait: Maximum total seconds to wait.

        Returns:
            Final status response when job completes or fails.

        Raises:
            DeepSearchTimeoutError: If max_wait exceeded.
            DeepSearchAPIError: If status check fails.
        """
        start_time = datetime.now(UTC)
        terminal_statuses = {
            DeepSearchJobStatus.COMPLETED,
            DeepSearchJobStatus.FAILED,
            DeepSearchJobStatus.CANCELLED,
        }

        while True:
            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed > max_wait:
                raise DeepSearchTimeoutError(
                    f"Job {job_id} did not complete within {max_wait}s"
                )

            status = await self.get_status(job_id)

            if status.status in terminal_statuses:
                # Emit terminal status event
                final_status = (
                    "completed"
                    if status.status == DeepSearchJobStatus.COMPLETED
                    else "failed"
                )
                emit_mission_status_change(
                    mission_id=job_id,
                    title=f"DeepSearch job {job_id}",
                    new_status=final_status,
                    previous_status="in_progress",
                )
                return status

            logger.debug(
                "Job %s status: %s (progress: %s%%), waiting %.1fs",
                job_id,
                status.status.value,
                status.progress_percent or "?",
                poll_interval,
            )
            await asyncio.sleep(poll_interval)

    def get_stats(self) -> dict[str, Any]:
        """Return current client statistics."""
        return {
            "execute_requests": self.stats.execute_requests,
            "execute_successes": self.stats.execute_successes,
            "execute_failures": self.stats.execute_failures,
            "execute_success_rate": self.stats.execute_success_rate,
            "status_requests": self.stats.status_requests,
            "status_successes": self.stats.status_successes,
            "status_failures": self.stats.status_failures,
            "status_success_rate": self.stats.status_success_rate,
            "total_retries": self.stats.total_retries,
        }


# Convenience function for one-off requests
async def execute_mission(
    mission_id: str,
    title: str,
    objective: str,
    success_criteria: list[str],
    callback_url: str,
    **kwargs: Any,
) -> DeepSearchExecuteResponse:
    """Convenience function to execute a mission without instantiating client.

    See DeepSearchClient.execute_mission for full parameter documentation.
    """
    client = DeepSearchClient()
    return await client.execute_mission(
        mission_id=mission_id,
        title=title,
        objective=objective,
        success_criteria=success_criteria,
        callback_url=callback_url,
        **kwargs,
    )


async def get_job_status(job_id: str) -> DeepSearchStatusResponse:
    """Convenience function to get job status without instantiating client."""
    client = DeepSearchClient()
    return await client.get_status(job_id)
