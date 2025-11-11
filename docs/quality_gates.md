# Mission Protocol Quality Gates

Mission Protocol missions now run through five blocking validators implemented in `app/services/quality_gates.py` and orchestrated by `app/services/quality_gate_service.py`. Gates execute automatically whenever a mission is created/updated or when `/api/v1/missions/{mission_id}/quality` is invoked.

## Gate Overview

| Gate | Purpose | Pass Criteria |
|------|---------|---------------|
| `research_statement` | Ensures the research statement anchors the mission. | `topic`, `scope`, and `objective` (hypothesis) are all non-empty. |
| `evidence_links` | Confirms insights are backed by document chunks. | Chunk-linked evidence meets the configured per-insight threshold (default: `>=1` chunk per insight). |
| `contradictions_resolved` | Forces contradictory findings to have follow-up plans. | Every `synthesis.contradictory_information` entry has a matching resolution note in `synthesis.contradiction_resolutions`. |
| `synthesis_quality` | Checks that synthesis moves beyond bullet lists. | Key insights contain ≥40 chars and the synthesis lists at least one recommendation plus one next step. |
| `traceability` | Verifies that evidence retains source pointers. | Evidence entries include `chunk_id` references; when `insight_sources` rows exist, each referenced insight reports at least one linked chunk. |

All five gates must pass before a mission can transition to `review` or `complete`. Explicit requests to promote while failures exist return `400 Bad Request` with the failing gate names. Implicit promotions downgrade to `review`.

## Telemetry

Every evaluation appends newline-delimited JSON to `telemetry/events/quality-gates.jsonl`:

```json
{
  "ts": "2025-11-08T16:44:00Z",
  "mission_id": "B3.3",
  "mission_uuid": "3e7f…",
  "gate": "traceability",
  "status": "fail",
  "details": "Evidence entries are missing chunk_id traceability.",
  "metadata": {
    "evidence_ids": ["EV-002"]
  }
}
```

These events feed Sprint 03 telemetry and the Sprint Efficacy Evaluator mission.

## API Surface

- `GET /api/v1/missions/{mission_id}/quality` re-runs the validators and returns a structured payload (`app/schemas/quality_gates.py`). It is safe for polling dashboards and UI indicators.

## Implementation Notes

- Gate logic operates on `MissionProtocolDraft` payloads, so YAML imports and API writes share the same enforcement code path.
- `QualityGateService` mirrors the gate results into `mission_data.quality_checkpoints`, ensuring progress snapshots and database constraints remain consistent.
- The evidence-threshold is configurable via `QualityGateService(evidence_threshold=...)` and defaults to 1 chunk per insight.

## Validation Checklist

Run the following regression tests before marking a gate remediation mission complete:

1. `pytest tests/test_presidio_redaction.py::test_redact_document_uses_pseudonymization_and_audit`
2. `pytest tests/test_rag_service.py::test_semantic_cache_hit_rate_reaches_target`

Record the passing evidence in mission telemetry and link the test output in the mission notes.
