# Sprint 10 Backlog Draft (Integration Focus)

**Source references:** `cmos/reports/architectural-pivot-summary.md`, `cmos/planning/Answers-for-deepsearch.md`

## Context
Sprint 09 finished the advanced search foundation. Sprint 10 pivots to the “three-system” integration (DeepSearch → TraceLab → PEDR) highlighted in the architectural pivot summary. The backlog below keeps TraceLab as the validation/orchestration layer while wiring in the upstream (DeepSearch) and downstream (PEDR) systems plus a humane Mission Protocol surface for reviewers.

## Proposed Missions
| Proposed ID | Objective | Key Deliverables | Dependencies |
| --- | --- | --- | --- |
| **B10.1 DeepSearch Ingestion Endpoint** | Accept JSON payloads from DeepSearch workers (projects, documents, insights). | FastAPI `/api/v1/deepsearch/ingest` endpoint with schema validation, storage pipeline hooking into existing ingestion jobs, and telemetry on rejected payloads. | DeepSearch export format (Answers-for-deepsearch.md) |
| **B10.2 Ingestion Validation + Orchestrator** | Sanitize DeepSearch payloads, deduplicate documents, and queue ingestion jobs. | Validation service (schema + rule engine), dedupe utilities, orchestrator wiring to `document_processing_statuses`, webhook to Mission Protocol on failures. | B10.1 |
| **B10.3 PEDR Connector** | Publish TraceLab state into the PEDR catalog. | Sync service translating TraceLab missions/reports into PEDR JSON, scheduled sync job, delta telemetry. | Existing PostgreSQL schema, PEDR API contract |
| **B10.4 Mission Protocol Read-Only UI** | Replace the dormant form UI with a dashboard surfacing research outputs and telemetry. | Next.js (or FastAPI templated) dashboard listing completed missions, metrics, and telemetry references, plus export/download actions. | Completed Sprint 09 docs + PEDR connector |
| **B10.5 Agent Correction Loop** | Close the loop on ingestion errors so DeepSearch can self-correct. | Error classifier, retry queue, and `/api/v1/deepsearch/corrections` endpoint that sends actionable feedback to DeepSearch. Includes telemetry + documentation. | B10.1/B10.2 |
| **B10.6 Sprint 10 Retrospective** | Standard closure mission capturing integration readiness. | Retrospective report, telemetry, backlog sync, Master Context updates. | Entire sprint |

All build missions are sized as “standard” per previous retrospectives. If more missions are required, split B10.2 (validator) and B10.5 (correction loop) into separate worker-focused efforts.

## Readiness Checklist
- DeepSearch payload schema captured in `cmos/planning/Answers-for-deepsearch.md` section “Architecture finalization”.
- PEDR connector requirements listed under “Sprint 10+ (Integration Focus)” in the architectural pivot summary.
- Mission Protocol UI must stay read-only, pulling data exclusively from SQLite/telemetry exports.
- Keep `./cmos/cli.py db export backlog|contexts` + `python cmos/scripts/validate_parity.py --check` in the Definition of Done for every mission, mirroring Sprint 09.

## Open Questions to Resolve Early in Sprint 10
1. Finalize authentication/authorization story for the new ingestion endpoint (shared secret vs service account).
2. Confirm whether DeepSearch can batch multiple projects per payload or if each submission is per-project.
3. Determine PEDR sync cadence (event-driven vs scheduled) and how to reconcile deletions.
4. Decide whether the read-only Mission Protocol UI should live in FastAPI templates or reuse the existing Next.js frontend (based on deployment simplicity).
