# Sprint 11 Backlog Draft (Phase 2 Integration)

**Source references:** `cmos/reports/sprint-10/retrospective.md`, `cmos/reports/sprint-10/integration-readiness-report.md`, `cmos/planning/DeepSearch-TraceLab-Integration-Contract.md`

## Context
Sprint 10 proved the DeepSearch → TraceLab ingestion path, PEDR quality boosts, and integration test harness. Sprint 11 (Week 7 coordination window) moves into Phase 2: automated correction loops, PEDR delta exports, and operator tooling so DeepSearch can self-correct without manual review. The backlog below keeps TraceLab accountable for the remaining gaps the contract called out (correction loop, PEDR bridge, operator console, schema distribution, and retrospective).

## Proposed Missions
| Proposed ID | Objective | Key Deliverables | Dependencies |
| --- | --- | --- | --- |
| **B11.1 Auto-Link Correction Loop & Observability** | Turn auto-link telemetry into actionable retries and dashboards so DeepSearch payloads self-heal. | Error taxonomy, retry queue, `/api/v1/deepsearch/corrections` endpoint, Grafana-ready JSONL summaries, and mission annotations for failed attempts. | B10.2 (ingestion), B10.5 (integration suite), telemetry in `cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl`. |
| **B11.2 PEDR Delta Sync Service** | Stream validated missions and relationship context into PEDR with governance metadata. | Delta detector, PEDR export job (CLI + schedule), parity checks, and documentation covering index rebuilds. | B10.1 (quality metadata), B10.4 (relationship API). |
| **B11.3 Mission Protocol Console (Read-Only UI)** | Ship an operator console that consumes the Relationship Context API + telemetry. | FastAPI or Next.js dashboard surfacing missions, evidence, telemetry summaries, correction status, and download/export buttons. | B10.4 API, B11.1 telemetry outputs. |
| **B11.4 Schema Distribution & Contract Hardening** | Publish `tracelab_schemas` to the internal package index and lock the ingestion contract. | Package publishing workflow, semantic version guardrails, contract doc updates, and CI check ensuring DeepSearch + TraceLab pin the same version. | B10.3 package scaffolding. |
| **B11.5 PEDR Pre-Flight Query Service** | Prevent duplicate research by letting DeepSearch query PEDR before launching new missions. | `/api/v1/pedr/preflight` endpoint, Mission Protocol summarizer, CLI example for DeepSearch agent, and telemetry on reuse vs new research. | B10.1 search service, B11.2 PEDR sync. |
| **B11.6 Sprint 11 Retrospective & Parity** | Standard closure mission documenting correction-loop outcomes, PEDR sync metrics, and backlog updates. | Retrospective report, telemetry, MASTER_CONTEXT updates, backlog export, parity validation. | Entire sprint. |

All missions remain “standard” sized except B11.1 (medium) because it spans retry infrastructure + dashboards. Split B11.1 into orchestration vs telemetry sub-missions if scoping tightens mid-sprint.

## Readiness Checklist
- Evidence auto-link telemetry is flowing (file: `cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl`).
- Integration suite + docs for ingestion/auto-link already shipped (B10.5), so correction loop work can build on deterministic tests.
- `tracelab_schemas` exists locally; only publishing + CI guardrails remain.
- Relationship Context API is live and cached; Mission Protocol Console can read from it immediately.
- PEDR contract + architecture decisions captured in `cmos/planning/DeepSearch-TraceLab-Integration-Contract.md` and `docs/quality-aware-search.md`.

## Open Questions to Resolve Early in Sprint 11
1. Decide whether correction loop retries should block the ingestion endpoint or run async with webhook notifications.
2. Confirm PEDR sync cadence (event-driven vs hourly) and how deletions/updates are reconciled.
3. Choose UI surface for the Mission Protocol Console (FastAPI server-side vs expanding the existing Next.js bundle).
4. Establish the internal package index for `tracelab_schemas` (Artifactory vs GitHub Packages) and access controls for DeepSearch.
5. Define success criteria for PEDR pre-flight queries (score threshold, “reuse vs proceed” guidance) so DeepSearch agents can automate the decision.
