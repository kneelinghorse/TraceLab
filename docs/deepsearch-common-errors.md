# DeepSearch Integration – Common Errors & Remedies

_Reference: structured after the troubleshooting checklist in `cmos/docs/AI-coding-assistant-workflows.md` to keep remediation steps in sync with Mission Protocol guardrails._

## QUALITY_GATE_FAILURE (evidence_links / traceability)
**Symptom:** `/api/v1/deepsearch/ingest` responds with `{"error":{"code":"QUALITY_GATE_FAILURE"...}}` and `failing_gates` includes `evidence_links` or `traceability`.

**Root Causes**
- DeepSearch payload omitted `evidence[].chunk_id` and no TraceLab chunk matched.
- Average linked sources per insight < `min_sources_per_insight` (default 1).
- Project-scoped documents do not exist (wrong `project_id`).

**Resolution Workflow**
1. Confirm the JSON mission references at least one evidence entry per key insight. Our fixtures in `tests/fixtures/deepsearch_missions/*.json` are good templates.
2. When DeepSearch has traceability data, populate `chunk_id` before hitting the API so EvidenceAutoLinking can skip the entry.
3. If linkages should be automatic, ensure the corresponding document/chunk exists for the provided `project_id`. Use `_seed_chunks` helper as shown in `tests/integration/test_deepsearch_integration.py` for local verification.
4. Retry ingestion and re-check telemetry `cmos/telemetry/events/sprint-10-integration-testing.jsonl` to confirm auto-linking succeeded.

## project_id missing when auto_create_project=false
**Symptom:** `HTTP 400` with detail `"project_id is required unless auto_create_project is true"`.

**Fix:** Either supply an existing project UUID or set `auto_create_project=true` with a non-empty `project_name`. See `test_ingest_auto_creates_project_when_requested` for a working payload (note: when auto-creating, include `chunk_id`s so quality gates pass immediately).

## Excessive similarity_threshold
**Symptom:** Raising `similarity_threshold` to `1.0` causes every evidence row to miss chunk matches, leading to QUALITY_GATE_FAILURE even though documents exist.

**Fix:** Keep the override below the expected fuzzy match score (0.7–0.9). `test_ingest_similarity_threshold_override_blocks_links` documents this behavior so the DeepSearch team understands the failure mode.

## Search endpoint uses real RAG dependencies
**Symptom:** Running `/api/v1/search` in tests triggers live Qdrant/OpenAI calls (404 for missing collection or missing API key).

**Fix:** Patch `get_rag_service` / override `get_search_history_service` with deterministic fakes before calling the endpoint. `test_ingested_mission_available_via_search_endpoint` shows the exact monkeypatching + `app.dependency_overrides` needed.

## Auto-linking telemetry missing
**Symptom:** `cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl` does not update because tests write elsewhere.

**Fix:** The integration suite intentionally redirects telemetry to a tmp file per test. When running manual verification, set `EVIDENCE_TELEMETRY_PATH` or instantiate `EvidenceAutoLinkingService(telemetry_path=Path("cmos/telemetry/events/sprint-10-deepsearch-ingestion.jsonl"))` to send output to the canonical location.
