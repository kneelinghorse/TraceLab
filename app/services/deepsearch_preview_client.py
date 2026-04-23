"""Client for DeepSearch's POST /api/v1/missions/preview endpoint (T40.4).

Signs the outbound body with the shared HMAC secret and normalizes transport
errors into a single :class:`ContractPreviewError` so callers (the FastAPI
route, the MCP tool) don't have to sniff httpx internals.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services.deepsearch_hmac_signer import HmacSigningError, sign_payload

logger = logging.getLogger(__name__)


class ContractPreviewError(RuntimeError):
    """Raised when the preview call cannot complete.

    ``status_code`` is set when the upstream returned an HTTP status we want
    to surface to the caller (e.g. 422 from the compiler); ``None`` means
    the call never reached or understood DeepSearch (timeout, DNS failure,
    auth not configured).
    """

    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ContractPreview:
    """Compiled-contract view returned by DeepSearch's preview endpoint."""

    named_entities: list[str]
    objectives: list[dict[str, Any]]
    evidence_slots: list[dict[str, Any]]
    acceptance_checks: list[dict[str, Any]]
    deliverable_schemas: list[dict[str, Any]]
    coverage_thresholds: dict[str, float]
    validation_thresholds: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "named_entities": self.named_entities,
            "objectives": self.objectives,
            "evidence_slots": self.evidence_slots,
            "acceptance_checks": self.acceptance_checks,
            "deliverable_schemas": self.deliverable_schemas,
            "coverage_thresholds": self.coverage_thresholds,
            "validation_thresholds": self.validation_thresholds,
        }


def _resolve_preview_url() -> str:
    """Return the fully-qualified URL of DeepSearch's preview endpoint.

    Prefers the explicit :attr:`settings.deepsearch_preview_url`; otherwise
    derives ``<deepsearch_api_url>/api/v1/missions/preview``. Raises when
    neither is set so misconfiguration surfaces early instead of becoming a
    cryptic 404.
    """
    explicit = getattr(settings, "deepsearch_preview_url", None)
    if explicit:
        return explicit.rstrip("/")

    base = getattr(settings, "deepsearch_api_url", None)
    if not base:
        raise ContractPreviewError(
            "DeepSearch preview URL is not configured. Set "
            "DEEPSEARCH_PREVIEW_URL or DEEPSEARCH_API_URL."
        )
    return f"{base.rstrip('/')}/api/v1/missions/preview"


def build_mission_context_from_mission(mission) -> dict[str, Any]:
    """Assemble the mission_context payload DeepSearch's preview endpoint expects.

    Mirrors :class:`MissionContractPreviewRequest` in DeepSearch.alpha at the
    pinned commit (see ``schemas/VERSIONS.md``). Fields the author didn't
    populate are omitted so DeepSearch's ``exclude_none`` normalization sees
    a clean payload.
    """
    payload: dict[str, Any] = {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "success_criteria": list(mission.success_criteria or []),
        "deliverables": list(mission.deliverables or []),
    }

    # Authoring fields — skip None/empty so the upstream compiler applies its
    # own defaults rather than receiving a bag of nulls.
    optional_fields = (
        "background",
        "focus",
        "references",
        "required_entities",
        "excluded_entities",
        "expected_output_schema",
        "coverage_thresholds",
        "validation_thresholds",
        "deliverable_format",
        "max_loops",
        "min_loops",
    )
    for field in optional_fields:
        value = getattr(mission, field, None)
        if value in (None, "", [], {}):
            continue
        payload[field] = value

    # Constraints has the transitional fallback: if the column is empty but
    # the legacy context['constraints'] is populated, thread it through.
    constraints = getattr(mission, "constraints", None)
    if not constraints and isinstance(getattr(mission, "context", None), dict):
        legacy = mission.context.get("constraints")
        if legacy:
            constraints = legacy
    if constraints:
        payload["constraints"] = constraints

    research_depth = getattr(mission, "research_depth", None)
    if research_depth:
        payload["research_depth"] = research_depth

    return payload


def preview_mission_contract(
    mission,
    *,
    client: httpx.Client | None = None,
) -> ContractPreview:
    """Sign and proxy the mission to DeepSearch's preview endpoint.

    Args:
        mission: A :class:`Mission` ORM instance (duck-typed — any object
            with the documented attributes works, which is what the tests
            rely on).
        client: Optional injected httpx client — tests pass a mock/transport;
            production lets the function manage its own client.

    Returns:
        :class:`ContractPreview` describing the compiled contract.

    Raises:
        ContractPreviewError: on network, signing, or upstream failures.
    """
    url = _resolve_preview_url()
    payload = build_mission_context_from_mission(mission)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    try:
        signed = sign_payload(body)
    except HmacSigningError as exc:
        raise ContractPreviewError(
            f"Cannot sign preview request: {exc}"
        ) from exc

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **signed.headers,
    }

    timeout = getattr(settings, "deepsearch_timeout", 30.0)

    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        try:
            response = http_client.post(url, content=signed.body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ContractPreviewError(
                f"Preview request timed out after {timeout}s",
            ) from exc
        except httpx.RequestError as exc:
            raise ContractPreviewError(
                f"Preview request failed: {exc}",
            ) from exc
    finally:
        if owns_client:
            http_client.close()

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise ContractPreviewError(
            f"DeepSearch preview returned {response.status_code}",
            status_code=response.status_code,
            detail=detail,
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ContractPreviewError(
            "DeepSearch preview returned a non-JSON body.",
            status_code=response.status_code,
            detail=response.text,
        ) from exc

    try:
        return ContractPreview(
            named_entities=list(data.get("named_entities", [])),
            objectives=list(data.get("objectives", [])),
            evidence_slots=list(data.get("evidence_slots", [])),
            acceptance_checks=list(data.get("acceptance_checks", [])),
            deliverable_schemas=list(data.get("deliverable_schemas", [])),
            coverage_thresholds=dict(data.get("coverage_thresholds", {})),
            validation_thresholds=dict(data.get("validation_thresholds", {})),
        )
    except (TypeError, ValueError) as exc:
        raise ContractPreviewError(
            "DeepSearch preview returned an unexpected response shape.",
            status_code=response.status_code,
            detail=data,
        ) from exc
