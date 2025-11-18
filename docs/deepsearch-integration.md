# DeepSearch Ingestion & Evidence Auto-Linking

TraceLab now exposes a dedicated ingestion surface for DeepSearch agents so completed missions can be pushed into the Mission Protocol engine without manual review. The workflow centers on the `POST /api/v1/deepsearch/ingest` endpoint and an evidence auto-linking service that matches DeepSearch evidence to TraceLab document chunks before quality gates execute.

## Endpoint Overview

- **Path:** `POST /api/v1/deepsearch/ingest`
- **Auth:** Same Bearer token used for other `/api/v1` routes
- **Purpose:** Validate a `MissionProtocolComplete` payload, run quality gates, auto-link evidence to document chunks, persist the mission, and emit telemetry.

### Request Body

```jsonc
{
  "project_id": "existing-project-uuid",      // optional when auto_create_project is true
  "auto_create_project": false,
  "project_name": "DeepSearch Research Output", // required only for auto-create
  "similarity_threshold": 0.75,               // optional override (default 0.70)
  "mission": { ...MissionProtocolComplete JSON... }
}
```

Key call-outs:

1. `mission` **must** conform to `MissionProtocolComplete` (topic/scope/objective, ≥1 answered key question, ≥1 key insight, all five quality checkpoints present and set to `pass`).
2. When `project_id` is omitted, pass `auto_create_project: true` and `project_name`; TraceLab will create the project and associate the mission automatically.
3. `similarity_threshold` tunes evidence auto-linking. Values outside `[0, 1]` are clamped to valid range.

### Success Response

```json
{
  "mission_uuid": "08be...2fd5",
  "mission_id": "DSR.10.1",
  "project_id": "1ee7...0bc3",
  "status": "complete",
  "quality_gates_passed": true,
  "quality_gates": {
    "research_statement": { "status": "pass", "details": "..." },
    "...": "..."
  },
  "auto_linking": {
    "attempted": 3,
    "linked": 3,
    "skipped": 0,
    "success_rate": 1.0,
    "threshold": 0.7,
    "matches": [
      { "evidence_id": "EV-001", "chunk_id": "f6c9...f1d8", "similarity": 0.91 }
    ]
  }
}
```

### Failure Modes

| Scenario | Status | Body |
| --- | --- | --- |
| Schema validation failure | `422` | Standard FastAPI `{"detail": [...]}` list |
| Quality gate failure | `400` | `{"success": false, "error": {"code": "QUALITY_GATE_FAILURE", ...}}` |
| Unknown/unauthorised project | `404` / `401` | Normal API error semantics |

Quality gate failures include the failing gate names, gate metadata, originating Mission Protocol ID, and the auto-linking summary so DeepSearch can understand why traceability checks failed.

## Evidence Auto-Linking

DeepSearch supplies URL-only evidence; TraceLab enriches those entries by matching evidence summaries against stored document chunks:

- `app/services/evidence_auto_linking.py` loads recent chunks for the target project and uses `difflib.SequenceMatcher` to score similarity between evidence summaries and chunk content.
- Matches above the configurable threshold update `chunk_id` and `relevance_score` in-memory before validation executes, ensuring the `evidence_links` and `traceability` gates evaluate against chunk-backed evidence.
- Results (attempted/skipped/linked, per-evidence similarity measurements, and success rate) are written to `cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl` for auditing.

> **Note:** Tests override the telemetry sink to avoid mutating repository fixtures, but production deployments should keep the default path to satisfy the CMOS mission deliverable.

## Quality Gates & Storage

1. Payload is parsed via `MissionProtocolComplete` (422 on failure).
2. Evidence auto-linking runs synchronously; missions without chunk matches will fail quality gates.
3. `QualityGateService.evaluate` runs all five blocking gates. Failure returns the structured 400 error above.
4. When all gates pass, the mission is persisted via `MissionProtocolService.create_mission` and the evidence-linking metadata is recorded in `missions.evidence_linking_metadata`.

## Telemetry

- Auto-linking telemetry: `cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl`
- Quality gate telemetry still flows through `telemetry/events/quality-gates.jsonl` because `QualityGateService` emits one event per gate evaluation.

## Testing

Two dedicated suites cover the feature:

1. `tests/test_evidence_auto_linking.py` – unit tests for similarity scoring, threshold overrides, and telemetry behaviour.
2. `tests/test_deepsearch_ingestion.py` – API-level tests covering successful ingestion (with DB assertions) and quality gate failures.

Run them with:

```bash
pytest tests/test_evidence_auto_linking.py tests/test_deepsearch_ingestion.py
```

This ensures the ingestion contract, auto-linking heuristics, and telemetry sinks stay aligned with the CMOS Sprint 10 requirements.
