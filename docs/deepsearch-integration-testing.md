# DeepSearch Integration Testing Guide

_This format follows the sprint-level expectations in `cmos/docs/integration-testing-guide.md` so TraceLab and DeepSearch share a single source of truth for Week 7 validation._

## Scope & Goals
TraceLab uses this suite to prove the DeepSearch ingestion contract end-to-end: MissionProtocol JSON → quality gates → evidence auto-linking → RAG search surfaces. The tests run entirely against the FastAPI application with the SQLite test database (`tests/test_ingestion.db`) and never mutate the Mission Protocol SQLite runtime.

## Environment Checklist
- Activate the repo's Python 3.11 environment and install `requirements.txt`.
- Ensure these env vars mirror the pytest fixtures:
  - `DATABASE_URL=sqlite:///./tests/test_ingestion.db`
  - `ENVIRONMENT=test`
  - `AUTH_USERNAME=tracelab-admin`, `AUTH_PASSWORD=changeme`
- Generated evidence chunks rely on the JSON fixtures under `tests/fixtures/deepsearch_missions/` (6 scenarios covering onboarding, security, SRE, diary studies, AI infra, market signals).
- Auto-link telemetry is redirected to the per-test tmp dir via `EvidenceAutoLinkingService(telemetry_path=tmp_path / "auto-linking.jsonl")` to avoid polluting production metrics.

## Execution
Run the full integration suite from repo root:

```bash
pytest tests/integration/test_deepsearch_integration.py -q
```

The suite currently executes ~6.5s on a MacBook Pro (M3 Max) and produces 10 atomic cases. When debugging a single scenario use `-k <name>` or `pytest tests/integration/test_deepsearch_integration.py -k onboarding`.

## Test Matrix
| Test | Purpose | Key Coverage |
| --- | --- | --- |
| `test_ingest_customer_onboarding_links_all_evidence` | Golden-path ingestion | Mission persisted, 3 evidence rows auto-linked, chunk IDs stored |
| `test_ingest_security_payload_exposes_match_metadata` | Match metadata health | Confirms `/api/v1/deepsearch/ingest` returns `matches[]` with previews |
| `test_ingest_auto_creates_project_when_requested` | Auto-create fallback | Validates DeepSearch can seed projects when `project_id` missing |
| `test_ingest_requires_project_identifier_without_auto_create` | Input validation | Ensures non-auto-create requests without `project_id` fail fast |
| `test_ingest_similarity_threshold_override_blocks_links` | Threshold guardrail | Raising threshold to `1.0` shows gates fail when no traceability |
| `test_ingest_quality_gate_failure_returns_structured_error` | Gate telemetry | Exercises QUALITY_GATE_FAILURE payload + failing gate metadata |
| `test_ingest_skips_prelinked_evidence_entries` | Pre-linked evidence | Verifies EvidenceAutoLinking does not override provided `chunk_id`s |
| `test_ingest_writes_auto_linking_telemetry` | Observability | Confirms telemetry JSONL entry written with mission ID + summary |
| `test_ingest_project_scoped_linking` | Project isolation | Ensures auto-linking respects `project_id` boundary despite other chunks |
| `test_ingested_mission_available_via_search_endpoint` | Search propagation | Patches RAG + history dependencies to confirm `/api/v1/search` returns newly-ingested evidence and logs search events |

## Fixtures & Mock Data
- `tests/fixtures/deepsearch_missions/*.json` supplies six MissionProtocolComplete payloads that cover onboarding, incident comms, SRE, diary studies, AI infra, and market signals. Each file contains:
  - Full research statements, answered key questions, synthesis sections.
  - ≥3 evidence entries so quality gates pass once chunk IDs attach.
  - Methodology metadata (participant segments, validation steps) pulled from the starter template in `foundational-docs/tech_arch_template.md`.
- `tests/integration/test_deepsearch_integration.py` seeds documents and chunks in SQLite for every test. The helper `_seed_chunks` writes `Document` + `DocumentChunk` rows so EvidenceAutoLinking can match summaries deterministically.

## Reporting & Telemetry
- Every pytest run appends an entry to `cmos/telemetry/events/sprint-10-integration-testing.jsonl` (see repo root for latest payload). Include this artifact in sprint validation notes per `cmos/docs/cmos_Playbook.md`.
- For parity tracking, capture the pytest command, duration, and commit hash in sprint notes or TraceLab telemetry dashboards.

## Next Steps
- Extend fixtures with PEDR JSON once DeepSearch includes Phase 2 payloads.
- Wire this suite into CI alongside the existing `tests/test_deepsearch_ingestion.py` unit coverage so ingestion regressions surface immediately.
- When Qdrant or OpenAI environments change, update `_FakeRagService` in the integration test to mirror the latest routing metadata expectations (model name, cache flags, quality scoring).
