"""Local mission-contract preview backed by the vendored DeepSearch compiler.

Originally (T40.4) this signed a request and proxied it to DeepSearch's
`POST /api/v1/missions/preview` HTTP endpoint. That endpoint never existed
in production — DeepSearch runs only as a worker (DB-polling, no HTTP API),
so the proxy hung and Cloudflare returned 502, breaking
`preview_mission_contract` end-to-end and blocking DS from disambiguating
mission-quality regressions.

T41.1 swaps the HTTP round-trip for a local call into the vendored compiler
at `app/services/contract_compiler/`. The public surface (function name,
:class:`ContractPreview` shape, :class:`ContractPreviewError` raises) is
unchanged so callers — the FastAPI route at
``app/api/v1/missions.py::contract_preview`` and any future MCP wrapper —
keep working without modification. The ``client`` keyword argument is kept
on `preview_mission_contract` for backwards source compatibility but is
ignored; nothing makes outbound HTTP calls anymore.

See ``cmos/contracts/deepsearch-compiler-vendor.md`` for the pinned commit
hash and the resync ritual that keeps the vendored compiler in step with
DeepSearch's evolution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.contract_compiler import (
    MissionContract,
    compile_contract_from_state,
)

logger = logging.getLogger(__name__)


class ContractPreviewError(RuntimeError):
    """Raised when the local preview compilation fails.

    ``status_code`` mirrors what the upstream HTTP boundary used to surface
    (422 for compiler validation rejections, ``None`` for everything else)
    so the FastAPI route's existing ``raise HTTPException`` mapping keeps
    working untouched.
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, detail: Any = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ContractPreview:
    """Compiled-contract view returned to API/MCP callers."""

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


# Authoring fields that are forwarded to the compiler when present. Lifted
# verbatim from the prior outbound payload so the compiler sees an
# identical mission_context shape.
_OPTIONAL_AUTHORING_FIELDS = (
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


def build_mission_context_from_mission(mission) -> dict[str, Any]:
    """Assemble the mission_context payload the compiler expects.

    Same shape the previous HTTP body produced — kept stable so any caller
    that constructed payloads independently (tests, future tools) doesn't
    need to change.
    """
    payload: dict[str, Any] = {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "success_criteria": list(mission.success_criteria or []),
        "deliverables": list(mission.deliverables or []),
    }

    for field in _OPTIONAL_AUTHORING_FIELDS:
        value = getattr(mission, field, None)
        if value in (None, "", [], {}):
            continue
        payload[field] = value

    # Constraints fallback: if the column is empty but legacy
    # context['constraints'] is populated, thread it through. Mirrors the
    # REST `_to_response` resolver and the prior client behavior.
    constraints = getattr(mission, "constraints", None)
    if not constraints and isinstance(getattr(mission, "context", None), dict):
        legacy = mission.context.get("constraints")
        if legacy:
            constraints = legacy
    if constraints:
        payload["constraints"] = constraints

    return payload


def _build_preview_state(mission_context: dict[str, Any]) -> dict[str, Any]:
    """Wrap mission_context in the AgentState-shaped dict the compiler reads.

    Mirrors DeepSearch's `_build_preview_state` adapter — see DS pinned
    commit, ``deepsearch/api/routes/missions.py::_build_preview_state``.
    Replicating the shape locally rather than importing it keeps TraceLab
    isolated from DS's HTTP-layer module organization.
    """
    mission_id = str(mission_context.get("mission_id") or "preview-mission").strip()
    objective = str(mission_context.get("objective") or "").strip()
    success_criteria = [
        str(item).strip()
        for item in mission_context.get("success_criteria") or []
        if str(item).strip()
    ]
    mission_objectives = success_criteria or ([objective] if objective else [])

    return {
        "mission_id": mission_id or "preview-mission",
        "mission_context": mission_context,
        "mission_objectives": mission_objectives,
        "deliverable_format": str(
            mission_context.get("deliverable_format") or "markdown"
        ),
        # T42.2 (sprint-42): research_depth was removed from the authoring
        # surface. The vendored compiler still keys depth_config off this
        # field, so the preview path pins it to "baseline" — the only tier
        # that was ever the default.
        "research_depth": "baseline",
        "max_loops": mission_context.get("max_loops") or 3,
        "min_loops": mission_context.get("min_loops") or 0,
        "depth_config": {},
    }


def _shape_contract(contract: MissionContract) -> ContractPreview:
    """Render a compiled MissionContract into the public ContractPreview view.

    Uses the same per-field JSON-mode dump DeepSearch applied at its HTTP
    boundary so wire-format-shaped consumers (the route response_model,
    cached snapshots) see byte-identical structure.
    """
    return ContractPreview(
        named_entities=list(contract.named_entities),
        objectives=[item.model_dump(mode="json") for item in contract.objectives],
        evidence_slots=[item.model_dump(mode="json") for item in contract.evidence_slots],
        acceptance_checks=[
            item.model_dump(mode="json") for item in contract.acceptance_checks
        ],
        deliverable_schemas=[
            item.model_dump(mode="json") for item in contract.deliverable_schemas
        ],
        coverage_thresholds=dict(contract.coverage_thresholds),
        validation_thresholds=dict(contract.validation_thresholds),
    )


def preview_mission_contract(
    mission,
    *,
    client: Any = None,  # retained for source-level back-compat; ignored
) -> ContractPreview:
    """Compile a mission into a preview contract using the vendored compiler.

    Args:
        mission: A :class:`Mission` ORM instance (duck-typed; any object
            exposing the documented attributes works, which is what the
            tests rely on).
        client: Ignored. Kept so existing call sites don't have to change
            during the HTTP→local cutover. Will be removed once the
            integration tests migrate fully (T41.3 boundary doc tracks this).

    Returns:
        :class:`ContractPreview` describing the compiled contract.

    Raises:
        ContractPreviewError: when the compiler rejects the input
            (`status_code=422`) or fails unexpectedly (`status_code=None`).
    """
    if client is not None:
        logger.debug(
            "preview_mission_contract received a `client` argument; ignored "
            "since T41.1 — preview is now local."
        )

    mission_context = build_mission_context_from_mission(mission)
    state = _build_preview_state(mission_context)

    try:
        contract = compile_contract_from_state(state, origin="api_preview")
    except ValueError as exc:
        # Mirrors DS's HTTP layer mapping: ValueError → 422 compiler reject.
        raise ContractPreviewError(
            str(exc) or "Mission contract preview failed",
            status_code=422,
            detail={"message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected failure compiling mission %s preview",
            getattr(mission, "mission_id", "<unknown>"),
        )
        raise ContractPreviewError(
            f"Mission contract preview failed: {exc}",
            status_code=None,
            detail=None,
        ) from exc

    return _shape_contract(contract)
