"""Vendored DeepSearch contract compiler — see vendor doc for resync ritual.

This package exposes the subset of DeepSearch's mission-contract compiler
that TraceLab needs to power `preview_mission_contract` locally, replacing
the brittle HTTP round-trip removed in T41.1 (sprint-41). DS runs only as a
worker in production — no HTTP API to call — so the proxy at T40.4 was
returning 502 against a service that doesn't exist. Vendoring the compiler
fixes the structural break and matches the existing pattern of vendoring DS's
expected_output_schema.

Pinned to DeepSearch.alpha commit `24e8810` (branch contract-driven-pipeline).
Source paths and resync steps live at
`cmos/contracts/deepsearch-compiler-vendor.md`.

Public API used by TraceLab:
- `compile_contract_from_state(state, *, origin)` — entry point
- `MissionContract` — return type, used for downstream `.model_dump()` shaping

Other symbols are exported for completeness so callers can introspect
intermediate models if needed, but they are not part of the stability
contract — DS may rename them between resyncs.
"""

from .contract import (
    AcceptanceCheck,
    DeliverableSchemaContract,
    EvidenceSlot,
    ExecutionBudget,
    MissionContract,
    ObjectiveContract,
    compile_contract_from_state,
)

__all__ = [
    "AcceptanceCheck",
    "DeliverableSchemaContract",
    "EvidenceSlot",
    "ExecutionBudget",
    "MissionContract",
    "ObjectiveContract",
    "compile_contract_from_state",
]
