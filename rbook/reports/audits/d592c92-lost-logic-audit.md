# d592c92 lost-logic audit — "style: apply ruff formatting baseline"

**Audited:** 2026-09-12 (session PS-2026-09-12-001) · **Commit:** d592c923e7b1 (2026-03-13, PR #198 `setup_pass`) · **Parent / reference tree:** 8b049ed (Sprint 38 merge)

## Verdict

The sections below preserve the original pre-recovery audit. Current dispositions
for all 51 findings are in the RECOVER-2 closure ledger at the end and the JSON
`recovery` fields; original “missing on main” labels are historical evidence.

The commit was not a formatting pass. Its files match a lint-fixed (`ruff check --fix` UP/I/F401/SIM) and `ruff format`-ed copy of the tree from ~2026-03-09 (post-Sprint-32 merge 3bebb00, pre-Sprint-33 merge 773f894) far more closely than they match their true parent: `search_orchestrator.py` differs by 455 lines from 8b049ed but 106 from the 3bebb00 tree; `mission_protocol_service.py` 225 vs 50; `auth.py` 104 vs 52. The formatting pass ran on a stale checkout and was committed over up-to-date main, so every touched file silently reverted to Sprint-32-era content — a coherent revert of Sprint 33–38 work.

**Method.** 172 `app/` files changed by the commit, split into 16 groups; one sweep agent per group ran `git diff -w --ignore-blank-lines 8b049ed d592c92 -- <file>` and read both versions; every candidate got two independent verifiers (a refuter defaulting to "formatting only", and a restoration/impact checker against current main). 116/120 agents completed; the two `main.py` router-mount candidates lost their verifiers to a session limit and were confirmed by hand (see below). 52 candidates → **51 confirmed, 1 refuted.**

| | count |
|---|---|
| confirmed logic losses | 49 + 2 hand-verified = 51 |
| re-implemented later on main | 20 |
| partially restored | 2 |
| still missing on main | 27 + 2 router mounts = 29 |
| refuted | 1 |

## Still missing on main (restore candidates)

Reference for every restore: `git show 8b049ed:<file>`. Do **not** re-apply the commit's inverse wholesale — 20 items were re-implemented differently since (RBAC, PEDR scoping, ownership) and would conflict.

### Hand-verified: two API routers unmounted (severity: high)

`app/main.py` at 8b049ed imported `mission_events` and `decision_links` and mounted them (`include_router(mission_events.router, prefix=f"{api_v1_prefix}/missions", tags=["mission-events"])` and `include_router(decision_links.router, prefix=api_v1_prefix, tags=["decision-links"], dependencies=protected_dependencies)`). Current main contains neither name (`grep -n "mission_events\|decision_links" app/main.py` → no output) while both router files still exist under `app/api/v1/`. The T35.2 mission-event bridge (`POST /events/cmos`) and the T35.3 decision-link endpoints are therefore unreachable in production. Re-mounting must respect the S46+ router-level auth (`protected_dependencies`) and any RBAC scoping the routers never received.

### Severity: high (3)

**`app/services/document_ingestion.py` — DocumentIngestionService.process_document** (removed_branch; restored: no)  
Pre-commit, after PEDR cache invalidation and before `return result`, process_document ran a Stage 6 'Incremental edge materialization (T37.3)': it set current_stage = "edges_materialized", instantiated EdgeMaterializationService() and called materialize_implicit_edges(session=db, mode="incremental", project_id=<document.project_id or None>), timed it, emitted a logger.info with inserted/updated/skipped counts, wrote result["stages"]["edges_materialized"] = {status: success, inserted, updated, skipped, …  
*Prod impact:* Production (Railway auto-deploys main; d592c92 is an ancestor of main) no longer materializes implicit PEDR graph edges when a document is ingested. Before d592c92, every successful process_document call ran EdgeMaterializationService.materialize_implicit_edges(mode="incremental", project_id=...) and wrote document->project (belongs_to), project->document (contains), document->chunk (contains) and chunk->document …

**`app/services/document_ingestion.py` — module imports** (removed_statement; restored: no)  
The import of EdgeMaterializationService was removed. This was NOT an unused import: it was the sole dependency of the Stage 6 edge materialization block that d592c92 also deleted (see the companion finding). Restoring Stage 6 requires restoring this import.  
*Prod impact:* Stage 6 (incremental graph-edge materialization, T37.3) has been silently absent from the ingestion pipeline in production since d592c92 (2026-03-13), and Railway auto-deploys main. Consequences: (1) No document ingested in the last ~6 months has had its implicit graph edges (contains/belongs_to/part_of/references/derived_from/co_occurs/topic_similar) written to graph_edges, because the only other writer is the …

**`app/services/pedr/__init__.py` — module-level imports / __all__ (LayerDiagnostic re-export)** (removed_statement; restored: no)  
This is the package-level footprint of the ALREADY-CONFIRMED LayerDiagnostic T33.1 deletion, listed so the restore is complete: pre-commit, `from .search_orchestrator import (...)` included `LayerDiagnostic,` and `__all__` contained `"LayerDiagnostic",` under `# Search Orchestrator`. d592c92 removed both. Whoever restores `LayerDiagnostic` in search_orchestrator.py must also re-add this import line and the `__all__` entry in `app/services/pedr/__init__.py`, otherwise `from app.services.pedr import LayerDiagnostic` …  
*Prod impact:* Production (Railway auto-deploys main) serves PEDR search with NO per-layer diagnostics and NO `degraded` flag. Concretely on main today: (1) `from app.services.pedr import LayerDiagnostic` raises ImportError — the symbol is absent from the package import block (app/services/pedr/__init__.py:76-86) and `__all__` (lines 198-206), and the class itself is absent from app/services/pedr/search_orchestrator.py …

### Severity: medium (9)

**`app/services/evidence_auto_linking.py` — EvidenceAutoLinkingService._log_telemetry** (removed_statement; restored: no)  
Pre-commit (since 9d723f9, Sprint 36 'telemetry migration') the auto-linking completion event was written through the unified envelope helper `app.core.telemetry.emit_telemetry(path=self.telemetry_path, event_type="evidence.auto_linking.completed", source="tracelab", payload={...})`, which (a) wraps the record as {ts, event_type, source, payload} -- the schema app/core/telemetry.py documents as consumed by cmos-dashboard/analytics and checked by `validate_jsonl_file`/`is_envelope_format`, and (b) runs inside …  
*Prod impact:* Not restored; the flat, unguarded writer is what runs in production today (Railway deploys main = f9af702). Two concrete effects: (1) Lost exception guard. POST /deepsearch/ingest (app/api/v1/deepsearch.py:54) calls link_evidence with no try/except, and link_evidence always ends in _log_telemetry, which now does telemetry_path.parent.mkdir + telemetry_path.open("a") with no guard …

**`app/services/mission_protocol_service.py` — export_mission_yaml** (changed_return_value; restored: partial)  
Pre-commit export used the stored protocol in `mission.context` when present and otherwise fell back to `mission.to_mission_protocol()` (which exists on the Mission model at d592c92). d592c92 replaced it with `dump_mission_yaml(mission.mission_data)`, dropping both the context lookup and the to_mission_protocol fallback; `mission_data` is not a Mission attribute at d592c92.  
*Prod impact:* On main (deployed to prod via Railway), GET /api/v1/missions/{id}/export (default format=yaml) returns HTTP 500 for any mission whose `context` JSON lacks a `mission_id` key. That is the column default `{}` and is exactly what the canonical POST /api/v1/missions path stores when the client does not supply a protocol-shaped context -- which is the case for the frontend MissionForm (sends no `context`) and likely most …

**`app/services/pedr/relational.py` — RelationType** (removed_statement; restored: no)  
Two enum members added for T38.1 were deleted from `RelationType`. Post-commit, `RelationType("co_occurs")` / `RelationType("topic_similar")` raise ValueError and `RelationType.CO_OCCURS` / `.TOPIC_SIMILAR` raise AttributeError. Concrete runtime effect: app/api/v1/pedr_related.py parses the `relation_types` query string with `RelationType(t.strip().lower())` and converts ValueError into HTTP 400 "Invalid relation type in relation_types", so GET /api/v1/pedr/related?relation_types=co_occurs (or topic_similar), …  
*Prod impact:* Production (Railway auto-deploys main, which contains d592c92) rejects GET /api/v1/pedr/related/{urn}?relation_types=co_occurs (or topic_similar) with HTTP 400 "Invalid relation type in relation_types"; pre-commit the same request returned 200. The companion EDGE_TYPES registry in semantic_protocol.py is also still missing both entries, and the two tests that would have caught it …

**`app/services/pedr/search_orchestrator.py` — PEDRConfig.enable_graph** (changed_default; restored: no)  
Pre-commit the graph (L6) layer was enabled by default (flipped to True in aa32f9d 'Sprint 34 ... graph activation'). d592c92 set the default back to False, silently disabling graph expansion for any caller that relies on PEDRConfig defaults.  
*Prod impact:* NOT restored: main still ships `enable_graph: bool = False` (app/services/pedr/search_orchestrator.py:124), and d592c92 is an ancestor of main, so prod (Railway auto-deploys main) runs the reverted default today. Blast radius is narrower than "graph layer off everywhere": - UNAFFECTED: the primary PEDR search surface. POST /api/v1/pedr/search always passes `enable_graph=payload.enable_graph` …

**`app/services/pedr/search_orchestrator.py` — PEDRConfig.graph_depth** (changed_default; restored: no)  
Pre-commit default traversal depth was 2 (set by 9d723f9 / T36.2 tuning). d592c92 reverted to 1.  
*Prod impact:* Latent, not live. `PEDRConfig.graph_depth` on main is still 1 (app/services/pedr/search_orchestrator.py:149), so the T36.2-validated default of 2 is gone. But no production request path actually consumes the dataclass default today: (a) the REST endpoint always forwards `payload.graph_depth` (app/api/v1/pedr_search.py:150) from the Pydantic schema, whose own independent default is 1 …

**`app/services/pedr/search_orchestrator.py` — PEDRConfig.graph_top_k_seeds** (changed_default; restored: no)  
Pre-commit default seed count was 10 (set by 9d723f9 / T36.2 tuning). d592c92 reverted to 5.  
*Prod impact:* Production (Railway auto-deploys main, tip f9af702 2026-08-21) runs PEDRConfig.graph_top_k_seeds = 5, not the Sprint-36 tuned 10. graph_top_k_seeds is NOT exposed in the /pedr search API payload (no field in app/schemas/pedr_search.py or app/api/v1/pedr_search.py), so every API request uses the dataclass default; callers cannot compensate. Effect when it matters: the graph layer (L6) seeds BFS expansion from the …

**`app/services/pedr/search_orchestrator.py` — LayerDiagnostic / PEDRMetadata.layer_diagnostics / PEDRMetadata.degraded / PEDRSearchResponse.to_dict / __all__** (removed_function; restored: no)  
(ALREADY-CONFIRMED T33.1 feature, listed for completeness.) The LayerDiagnostic dataclass, the PEDRMetadata.layer_diagnostics and .degraded fields, the 'layer_diagnostics' and 'degraded' keys in PEDRSearchResponse.to_dict(), the `has_errors` computation, and the 'LayerDiagnostic' __all__ export were all removed. Consumers at the pre-commit: app/api/v1/pedr_search.py:180 iterates response.metadata.layer_diagnostics; app/schemas/pedr_search.py defines PEDRLayerDiagnostic; app/services/pedr/__init__.py re-exports …  
*Prod impact:* Not restored; the rest of the codebase was instead conformed to the loss. On main today, PEDRSearchOrchestrator.search() still degrades gracefully (a failing lexical/semantic/graph layer is logged at WARNING and healthy-layer results are returned), but the response carries NO degradation signal: PEDRMetadata has no layer_diagnostics/degraded fields, PEDRSearchResponse.to_dict() emits neither key, and the HTTP schema …

**`app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (Phase 1 pre-analysis)** (removed_branch; restored: no)  
Pre-commit, syntactic and pragmatic query analysis each ran inside `if config.enable_X: try/except Exception ... else:` with (a) an exception fallback that built neutral filters (auto_detect=False / intent_boost_enabled=False) and logged a warning, and (b) an else-branch that built those same neutral filters when the layer was disabled. d592c92 left an unconditional `syntactic_filters = self._analyze_syntactic(query, config)` / `pragmatic_filters = self._analyze_pragmatic(query, config)`. Two behavioral …  
*Prod impact:* Production (Railway auto-deploys main, HEAD f9af702) runs the unguarded Phase 1. Concrete effects: (1) If _analyze_syntactic/_analyze_pragmatic raise, PEDRSearchOrchestrator.search propagates; app/api/v1/pedr_search.py:248-250 turns it into HTTP 500 instead of the pre-commit degraded HTTP 200. Realistic likelihood is low: both analyzers are pure precompiled-regex matching over a str (syntactic.py:163-202, …

**`app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (Phase 4 syntactic boost / pragmatic boost / governance scoring)** (removed_branch; restored: no)  
Pre-commit each post-fusion layer call (`syntactic_service.apply`, `pragmatic_service.apply`, `quality_service.apply`) was wrapped in try/except Exception that logged a warning and recorded a diagnostic, so a failing layer degraded the response rather than failing the request; the governance block also recorded timings.governance_ms in the except path. d592c92 left the bare `.apply(...)` calls with no handler, so any exception in these layers now propagates out of search(). (The `if not any(d.layer == ... for d in …  
*Prod impact:* Production (main, Railway auto-deploy) now fails the whole PEDR search request when any post-fusion layer raises, instead of returning the already-fused results with a degraded flag. Concretely: (1) GovernanceScoringService.apply performs a live DB query per search (app/services/pedr/quality_scoring.py:208-228, session_factory + session.query(Document/Project/Mission)); a transient Postgres error, pool exhaustion, …

### Severity: low (16)

**`app/core/database.py` — module-level engine construction (engine = create_engine(...))** (removed_branch; restored: no)  
Before d592c92, the engine kwargs were built conditionally: when ENVIRONMENT == "test" and the configured database_url was SQLite, the engine used sqlalchemy.pool.StaticPool with connect_args={"check_same_thread": False} to prevent connection-pool race conditions during repeated drop_all/create_all cycles in the test suite (introduced by cf0518c, 'T34.1: Test suite health — fix all test failures'). d592c92 deleted the whole `_engine_kwargs` block and the `import os` that only it used, collapsing the call to an …  
*Prod impact:* Zero production impact. The deleted branch was gated on `os.environ.get("ENVIRONMENT") == "test" and "sqlite" in settings.database_url`; production runs ENVIRONMENT=production against Postgres (config default is postgresql://, app/core/config.py:17; Railway prod sets ENVIRONMENT=production per memory), so the gate was always False there and the production engine was built with exactly the same kwargs before and …

**`app/services/cache_manager.py` — CacheManager._write_telemetry** (removed_statement; restored: no)  
(Separate from the already-known stats-key/stats-invalidation loss.) Pre-commit cache metric snapshots were emitted via app.core.telemetry.emit_telemetry with event_type='cache.metrics.snapshot', source='tracelab', payload={'caches': snapshot} (TelemetryEnvelope format from T35.4/T38.3). d592c92 replaced it with a hand-rolled `{"ts": _utc_now_str(), "caches": snapshot}` raw JSON append to sprint-08-cache-metrics.jsonl, dropping the envelope (event_type/source/payload wrapper). `_utc_now_str` was dead code …  
*Prod impact:* Log-only / telemetry-shape regression, no user-visible or data-integrity effect. On main today, every GET /api/v1/cache/stats and POST /api/v1/cache/clear (app/api/v1/cache.py:45,54 call snapshot(log=True)) appends a pre-T35.4 legacy line {"ts", "caches"} to cmos/telemetry/events/sprint-08-cache-metrics.jsonl instead of a TelemetryEnvelope …

**`app/services/correction_queue.py` — CorrectionQueueService._log_telemetry** (other; restored: no)  
BEFORE (8b049eda4b, introduced by Sprint 36 commit 9d723f9 'telemetry migration'): correction events were written through the unified envelope helper app.core.telemetry.emit_telemetry, producing JSONL records of shape {"ts", "event_type": "correction.<event>", "source": "tracelab", "payload": {mission_id, evidence_id, error_type, retry_count, similarity, threshold, status, success}} and swallowing any Exception on write failure. AFTER (d592c92): the method body was replaced with the exact pre-Sprint-36 code …  
*Prod impact:* Not restored: main (f9af702, which Railway deploys) still ships the pre-Sprint-36 hand-rolled flat telemetry record in CorrectionQueueService._log_telemetry. Production effect is log-sink-only: the correction queue IS live in prod (app/api/v1/deepsearch.py:91-95 queues failed auto-link items; app/api/v1/corrections.py drives retry/process/summary), so every correction_queued / correction_attempt / correction_success …

**`app/services/cost_monitor.py` — CostMonitor._append_telemetry** (removed_statement; restored: no)  
Pre-commit cost events were emitted via app.core.telemetry.emit_telemetry with event_type='cost.monitor.event', source='tracelab' (TelemetryEnvelope). d592c92 replaced it with a raw `json.dumps(payload, ensure_ascii=False)` append to sprint-04-performance.jsonl, so new cost rows lose the envelope fields (event_type/source/payload) that the telemetry standardization introduced. Everything else in the file is formatting/typing only.  
*Prod impact:* Telemetry-file-only. Every CostMonitor.track_usage/record_cache_hit call in prod (rag_service, synthesis, monitoring router) appends a flat row to telemetry/events/sprint-04-performance.jsonl instead of a TelemetryEnvelope row, so the file (and any cmos-dashboard/analytics consumer expecting {ts,event_type,source,payload}) now holds mixed shapes: 1518 envelope rows followed by 74 raw rows on main (validator reports …

**`app/services/mission_protocol_service.py` — update_mission** (removed_branch; restored: partial)  
Pre-commit `update_mission` had a three-way dispatch: (a) payload carries mission_data -> use it as draft; (b) mission.context holds a stored protocol ('mission_id' key) -> reconstruct draft from context; (c) otherwise apply simple field updates (title, objective, success_criteria, status, tags), commit and return early. On the draft paths it wrote `mission.context`, merged into `mission.execution_metadata` (quality_gates, completion_percentage) and mapped status via `_map_protocol_status`. d592c92 replaced all of …  
*Prod impact:* Effectively nil today. On main, MissionProtocolService.update_mission has ZERO production callers: the PATCH /api/v1/missions/{id} route and the submit route both use `_service = MissionService()` (app/api/v1/missions.py:82, calls at :228 and :645), and every other update_mission caller (app/mcp_server/tools/missions.py:46, app/services/webhook_handler.py:49, app/adapters/repositories/sqlalchemy_mission_repo.py:18) …

**`app/services/pedr/__init__.py` — module-level imports / __all__ (PEDR exception hierarchy re-exports)** (removed_statement; restored: no)  
Before d592c92 the pedr package re-exported the full T33.1 exception hierarchy (added in 05a165d "PEDR exception hierarchy, per-layer LayerDiagnostic tracking"): `from .exceptions import (PEDRError, LexicalSearchError, SemanticSearchError, GraphLayerError, SyntacticLayerError, PragmaticLayerError, GovernanceLayerError, FusionError)` plus the eight matching `__all__` entries under the `# PEDR Exceptions` comment. d592c92 deleted the entire import block and all eight `__all__` strings; no replacement import was …  
*Prod impact:* None observable in production. The package-level re-exports (`from app.services.pedr import PEDRError` etc.) are still gone on main, but no runtime code path depends on them: (a) no file in the repo imports any of the eight exception names from the package or from `app.services.pedr.exceptions` on main; (b) even BEFORE d592c92 no production code ever `raise`d or `except`ed any of these classes — …

**`app/services/pedr/delta_sync.py` — DeltaSyncService._log_sync_event** (other; restored: no)  
d592c92 reverted the Sprint 36 T36.3 telemetry migration (commit 9d723f9, "Migrated 6 remaining telemetry emitters to emit_telemetry() envelope format. Zero legacy write patterns remain") for this emitter. Before d592c92, `_log_sync_event` called `emit_telemetry(path=self.telemetry_path, event_type="pedr.delta_sync.completed", source="pedr", payload={...})`, which writes a unified `TelemetryEnvelope` line (`ts` / `event_type` / `source` / `payload`) to cmos/telemetry/events/sprint-11-pedr-sync.jsonl and is what …  
*Prod impact:* Log-only, and effectively not reachable in the deployed API. DeltaSyncService.sync_missions/sync_documents are invoked only from the manual CLI (app/cli/pedr.py cmd_sync) — no API route, worker, cron, Dockerfile/railway entry, or GitHub workflow calls them — and the telemetry sink is a relative repo path (cmos/telemetry/events/sprint-11-pedr-sync.jsonl) that is a local-dev artifact, ephemeral inside a Railway …

**`app/services/pedr/preflight.py` — PreflightService._emit_telemetry** (other; restored: no)  
BEFORE (8b049eda4b, from Sprint 36 commit 9d723f9 / T36.3 'Migrated 6 remaining telemetry emitters to emit_telemetry() envelope format'): the method delegated to app.core.telemetry.emit_telemetry(), which wrote a unified-envelope JSONL line {"ts", "event_type": "preflight.query.completed", "source": "tracelab", "payload": {query, action, top_score, match_count, latency_ms, min_quality_gates, status_filters, agent}} to cmos/telemetry/events/sprint-11-preflight.jsonl (emit_telemetry itself mkdirs the parent, …  
*Prod impact:* No user-visible or DB data-integrity change. The preflight endpoint (POST /api/v1/pedr/preflight, app/api/v1/pedr_preflight.py:30,85) still returns the same recommendation; _emit_telemetry is fire-and-forget inside try/except (preflight.py:435-460) and only appends to a relative-path JSONL file (cmos/telemetry/events/sprint-11-preflight.jsonl under Dockerfile WORKDIR /app). railway.json declares no volume, the file …

**`app/services/pedr/relational.py` — RelationType (str, Enum)** (removed_statement; restored: no)  
OUT OF MY ASSIGNED FILE GROUP -- flagged because it is the same T38.1 feature as the semantic_protocol.py EDGE_TYPES loss and was verified directly from the d592c92 diff while tracing usages. Before d592c92, RelationType had enum members CO_OCCURS = "co_occurs" and TOPIC_SIMILAR = "topic_similar" after RELATED_TO. d592c92 removed both members (diff hunk @@ -51,8 +53,6 @@). At d592c92, `git grep` for "co_occurs"/"topic_similar" in relational.py returns nothing. Please route to whoever owns relational.py; I did not …  
*Prod impact:* Not restored: main's RelationType still has only the 6 original members (belongs_to, contains, references, derived_from, sibling_of, related_to). CO_OCCURS and TOPIC_SIMILAR are gone. However, the lost members were declaration-only: at d592c92^ the ONLY references to RelationType.CO_OCCURS / TOPIC_SIMILAR anywhere in app/ and tests/ were the two enum lines themselves; RelationalService (SQL-join traversal, not …

**`app/services/pedr/search_orchestrator.py` — DEFAULT_GRAPH_WEIGHT (module constant; feeds PEDRConfig.graph_weight and DEFAULT_LAYER_WEIGHTS)** (changed_default; restored: no)  
Pre-commit the tuned graph layer weight was 0.12 (set by 9d723f9 'Sprint 36: ... config reconciliation', comment '# Graph layer — tuned via T36.2 quality proof (sprint25 config validated)'). d592c92 reverted it to the pre-S36 value 0.08 and also dropped the T36.2 comment (now just '# Graph layer'). This changes default RRF layer weights for every PEDR search that does not pass graph_weight explicitly.  
*Prod impact:* For the claimed symbol alone: effectively none observable in production today, because DEFAULT_GRAPH_WEIGHT is dead on every production call path. (1) HTTP POST /api/v1/pedr/search always passes payload.graph_weight explicitly (app/api/v1/pedr_search.py:153) from the Pydantic schema default, which is 0.08 (app/schemas/pedr_search.py:207-208) and was ALREADY 0.08 at 9d723f9 (Sprint 36 never touched the schema) — so …

**`app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (lexical/semantic/graph failure logging)** (other; restored: no)  
Structured failure log lines that carried layer=, query=%r and error_type=%s fields were reduced to bare '%s' messages. Pre: `"Lexical search failed: layer=lexical query=%r error_type=%s error=%s", query[:80], type(lexical_error).__name__, lexical_error` (same shape for semantic and graph). Post: `logger.warning("Lexical search failed: %s", lexical_error)` etc. Anything grepping/parsing these fields (error_type=, layer=) no longer sees them.  
*Prod impact:* Log-only degradation. On main (which Railway deploys) the three PEDR layer-failure warnings are still emitted, but as bare "Lexical/Semantic/Graph search failed: <error>" with no layer=, query=%r, or error_type= fields. Operators grepping Railway logs for error_type= or layer=lexical|semantic|graph will get no hits for PEDR layer failures, and the truncated query text that aided triage is gone. No search results, …

**`app/services/pedr/search_orchestrator.py` — _emit_graph_telemetry** (removed_statement; restored: no)  
Pre-commit graph telemetry was written through the unified TelemetryEnvelope emitter (app.core.telemetry.emit_telemetry, event_type='pedr.graph.telemetry', source='pedr'; legacy 'ts'/'event' keys popped so the envelope supplies them). This was the T35.4 / T38.3 telemetry standardization. d592c92 replaced it with a raw `json.dumps(payload)` append that writes the legacy flat record (including `"event": "pedr_graph_telemetry"` and its own `ts`), so new rows in sprint-26-graph-telemetry.jsonl no longer conform to the …  
*Prod impact:* Production (Railway auto-deploys main) still runs the reverted code: _emit_graph_telemetry writes a raw legacy flat record (`{"ts":..., "event":"pedr_graph_telemetry", ...}`) via json.dumps instead of the {ts,event_type,source,payload} TelemetryEnvelope. No user-visible behavior changes: the write is gated behind self.telemetry_enabled, is best-effort (exceptions swallowed to logger.warning), and targets a relative …

**`app/services/pedr/semantic_protocol.py` — EDGE_TYPES (module-level frozenset constant, exported in __all__)** (removed_statement; restored: no)  
Before d592c92, the EDGE_TYPES frozenset contained the two T38.1 semantic edge types "co_occurs" and "topic_similar" alongside the standard graph edge types. d592c92 reformatted the frozenset({...}) literal onto multiple lines and dropped those two members, leaving only belongs_to/contains/references/derived_from/related_to/requires/binds_to/part_of/sibling_of. The producers of these edge types still exist at d592c92 (app/services/pedr/edge_materialization.py lines 716, 725, 904, 914 still emit …  
*Prod impact:* No user-visible or data-integrity change in production today. EDGE_TYPES has zero runtime consumers on main: its only references are its own definition (app/services/pedr/semantic_protocol.py:95) and the __all__ export (line 1741). Edge.__post_init__ (lines 348-355) does not validate edge_type against it; graph_layer's allowed_edge_types defaults to None (= all types, graph_layer.py:28); the search API's …

**`app/services/quality_checks.py` — _QualityAutomationTelemetry.__call__** (other; restored: no)  
Telemetry emission regression (T38.3 'Telemetry Migration Completion' undone). Pre-commit the sink called `app.core.telemetry.emit_telemetry` which wraps the payload in the unified TelemetryEnvelope (event_type 'quality.automation.<check_type>', source 'quality'), creates dirs, and swallows IO errors. d592c92 replaced it with the legacy inline writer: builds a flat dict with an extra 'ts' key, and does `json.dumps` + manual append to self.path with no envelope and no error guard. Any consumer expecting …  
*Prod impact:* Prod (Railway auto-deploys main; d592c92 is an ancestor of main) runs the legacy inline writer. Every automated quality check executed in prod — triggered on mission create/update via MissionProtocolService -> QualityAutomationRunner.schedule (app/services/mission_protocol_service.py:329) and via POST /quality-automation/run (app/api/v1/quality_automated.py:54) — appends a flat {ts, entity_type, entity_id, …

**`app/services/quality_gate_service.py` — _FileTelemetrySink.__call__** (removed_statement; restored: no)  
Pre-commit quality-gate events were emitted via app.core.telemetry.emit_telemetry with event_type='quality.gate.evaluated', source='quality', with the payload's own 'ts' popped so the envelope supplied the timestamp (docstring: 'via TelemetryEnvelope'). d592c92 replaced it with a raw `json.dumps(payload)` append to quality-gates.jsonl and dropped 'via TelemetryEnvelope' from the docstring, so new rows are legacy flat records without event_type/source/payload. Remaining diff in this file is formatting/typing only …  
*Prod impact:* Not restored: main today still writes raw json.dumps(payload) rows to telemetry/events/quality-gates.jsonl with no event_type/source/payload envelope, so every quality-gate evaluation since the 2026-04-11 merge of d592c92 (PR #199) has emitted non-conformant legacy records — the T38.3 "telemetry migration completion" is silently reverted for this emitter. The committed quality-gates.jsonl already shows the …

**`app/services/webhook_client.py` — WebhookClient._log_telemetry** (other; restored: no)  
Pre-commit, _log_telemetry delegated to app.core.telemetry.emit_telemetry(path=self.telemetry_path, event_type=f"webhook.{event}", source="tracelab", payload={...}). That helper writes the unified TelemetryEnvelope JSONL shape {"ts", "event_type": "webhook.webhook_success"|"webhook.webhook_failed", "source": "tracelab", "payload": {mission_id, evidence_id, notification_type, success, status_code, duration_ms, attempt, error, context}} and catches ALL exceptions (logging 'Telemetry write failed (%s): %s'). d592c92 …  
*Prod impact:* Webhook delivery itself (retries, DLQ, stats) is unchanged; only the telemetry side-channel regressed. On main today, every correction-loop webhook outcome is appended to cmos/telemetry/events/sprint-11-corrections.jsonl as a FLAT legacy record ({"ts","event":"webhook_success"|"webhook_failed",...}) instead of the unified TelemetryEnvelope …

### Severity: none (1)

**`app/models/chunk.py` — DocumentChunk.content_tsv** (changed_default; restored: no)  
Pre-commit, the ORM column `content_tsv` was declared `nullable=True`. d592c92 changed it to `nullable=False` inside a commit labeled formatting-only. Ruff's formatter never rewrites keyword-argument values, and `git log -S'nullable=False,' -- app/models/chunk.py` shows d592c92 is the only commit that ever introduced this value. Effect: SQLAlchemy `create_all` (used by the SQLite test DB) now emits NOT NULL on content_tsv, and Alembic autogenerate compares against a different model nullability. Mitigating context: …  
*Prod impact:* Zero production impact, and restoring the old value would be a regression. Production schema is owned solely by Alembic (app/main.py:91-95, create_all removed from runtime), and migration 006 created document_chunks.content_tsv as NOT NULL before d592c92 ever existed (pre-commit alembic/versions/006_add_fulltext_search.py:26 = `nullable=False`; unchanged at main lines 27-28). SQLAlchemy does not enforce …

## Re-implemented later on main (verify completeness, no action unless noted)

- `app/api/v1/auth.py` — login (removed_statement): 1) `git show main:app/api/v1/auth.py` — line 8 imports `Request`; line 12 `from app.core.rate_limit import auth_rate_limiter, client_ip, register_rate_limiter`; lines 57-63: ``` def login( payload: LoginRequest, request: Request, db: Session = Depends(get_db) …
- `app/api/v1/auth.py` — register (removed_statement): 1) `git show main:app/api/v1/auth.py` — lines 8 (imports Request), 12 (`from app.core.rate_limit import auth_rate_limiter, client_ip, register_rate_limiter`), 101-107: `def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db))` …
- `app/api/v1/auth.py` — login (removed_statement): 1. `git show main:app/api/v1/auth.py | sed -n '1,120p'` — main:app/api/v1/auth.py:67-77 inside `login()`: `if not db_user or not verify_password(...)` → `logger.warning(f"auth_failure reason=invalid_credentials email={_log_safe(payload.email)} …
- `app/api/v1/auth.py` — register (removed_statement): 1) Current main file: `git show main:app/api/v1/auth.py` — register() at app/api/v1/auth.py:101; duplicate-email path logs `auth_failure reason=email_registered` at :112-115 then raises 409 at :116; invalid-invite path logs `auth_failure …
- `app/api/v1/auth.py` — _get_client_ip / _log_auth_failure (removed_function): 1. `git show main:app/api/v1/auth.py | grep -n ...` -> no `_get_client_ip`/`_log_auth_failure`/`# --- Audit Logging ---`; instead `auth_failure` log lines at app/api/v1/auth.py:71 (invalid_credentials), :83 (account_disabled), :113 (email_registered), :129 …
- `app/api/v1/auth.py` — module imports (other): 1) Loss confirmed: `git show d592c92 -- app/api/v1/auth.py` removed `import logging`, `Request`, `from app.core.rate_limit import auth_rate_limiter`, `logger = logging.getLogger(__name__)`, the `request: Request` params on login/register, both …
- `app/api/v1/deepsearch.py` — ingest_deepsearch_payload (removed_statement): 1) `git show main:app/api/v1/deepsearch.py | sed -n 40,95p` -> lines 69-79: `try: mission = _mission_service.create_mission_from_draft(db, project_id=project.id, draft=draft_payload, requested_status=mission_payload.status) except MissionProtocolServiceError …
- `app/api/v1/deepsearch.py` — ingest_deepsearch_payload (removed_statement): 1. `git show main:app/api/v1/deepsearch.py | grep -n -A6 -B6 evidence_linking` -> main lines 81-83: 81: execution_metadata = dict(mission.execution_metadata or {}) 82: execution_metadata["evidence_linking"] = auto_link_result.as_dict() 83: …
- `app/api/v1/deepsearch.py` — ingest_deepsearch_payload (changed_return_value): 1) Current main: `git show main:app/api/v1/deepsearch.py | sed -n 70,125p` -> lines 110-112: `quality_summary = (mission.execution_metadata or {}).get("quality_gates", report.as_dict())`, fed into `DeepSearchIngestResponse(... quality_gates=quality_summary …
- `app/api/v1/deepsearch.py` — ingest_deepsearch_payload (changed_return_value): 1) `git show main:app/api/v1/deepsearch.py | grep -n "mission_id=mission\|mission_data"` -> line 115: `mission_id=mission.mission_id,`; no `mission_data` references remain. Same on HEAD (codex/ledger-3); `git diff main HEAD -- app/api/v1/deepsearch.py` is …
- `app/api/v1/missions.py` — import_mission (POST /import) (other): 1) Current main: `git show main:app/api/v1/missions.py | grep -n "^from typing\|payload: "` -> line 13 `from typing import Any`; line 797 `payload: dict[str, Any]` (route decorator at 791-795, def import_mission at 796). Runtime check loading main's module …
- `app/core/security.py` — require_authenticated_user_sse (removed_statement): 1) `git show main:app/core/security.py | grep -n Optional` -> no matches; imports at lines 3-19 contain no `typing` import; `require_authenticated_user_sse` at main:361-364 reads `credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)`, …
- `app/schemas/pedr_search.py` — module imports / PEDRLayerDiagnostic, PEDRSearchMetadata (removed_statement): 1) `git show main:app/schemas/pedr_search.py | grep -n -E "^from typing|Optional|List\[|__future__"` -> only line 9 `from typing import Any, Literal`; no `Optional`/`List[` usages remain (all fields use `str | None` / `list[...]`, e.g. lines 73, 80, 280, …
- `app/services/mission_protocol_service.py` — create_mission_from_draft (removed_function): 1. `git show main:app/services/mission_protocol_service.py | grep -n "def "` -> `77: def create_mission_from_draft(` present on main; file is 337 lines. Body at :77-116 calls _ensure_draft, quality_gate_service.evaluate, evaluate_progress, _determine_status, …
- `app/services/mission_protocol_service.py` — create_mission (removed_branch): 1) `git show main:app/services/mission_protocol_service.py | grep -n "def create_mission\b" -A 60` -> line 71-75: create_mission delegates to self.mission_service.create_mission(db, payload) then _after_write(mission.id); lines 77-116 …
- `app/services/mission_protocol_service.py` — _PROTOCOL_STATUS_MAP / _map_protocol_status (removed_function): 1. `git show main:app/services/mission_protocol_service.py` — no `_PROTOCOL_STATUS_MAP`/`_map_protocol_status`; replacement present: `_protocol_status` (lines 285-290: {'completed':'complete','validation_failed':'review'}) and `_canonical_status` (lines …
- `app/services/mission_protocol_service.py` — _determine_status (changed_condition): 1) Loss confirmed: `git show d592c92 -- app/services/mission_protocol_service.py` shows `-if normalized_request in {"complete", "review", "completed"}:` / `+... {"complete", "review"}` and `-if status in ("complete", "completed"):` / `+if status == …
- `app/services/mission_protocol_service.py` — import_mission_yaml (changed_return_value): 1) `git show main:app/services/mission_protocol_service.py` lines 165-180: import_mission_yaml calls `self.create_mission_from_draft(db, project_id=project_id, draft=draft, requested_status=draft.status)` (line 175-180). `diff` of the import_mission_yaml …
- `app/services/pedr/edge_materialization.py` — EdgeMaterializationService._collection_cooccurrence_edges (reached via _implicit_edge_specs / materialize_implicit_edges) (removed_statement): 1) `git show main:app/services/pedr/edge_materialization.py | grep -n Collection` -> line 15 ` Collection,` in the `from app.models import (...)` block; line 687 `).join(Collection, CollectionItem.collection_id == Collection.id)`. 2) `ruff check --select …
- `app/services/quality_checks.py` — QualityAutomationService.evaluate (removed_branch): 1) `git show main:app/services/quality_checks.py | sed -n 150,185p` — app/services/quality_checks.py:153-175 on main: `protocol_data = (mission.context if isinstance(mission.context, dict) and "mission_id" in mission.context else {})`; `if protocol_data: try: …

## Refuted

- `app/services/pedr/edge_materialization.py` — EdgeMaterializationService._collection_cooccurrence_edges, materialize_topic_similarity_edges, _topic_similarity_edge_specs: The claim is accurate in its facts but, by its own admission, is not a behavior change, and the diff confirms that: the Optional/Dict/List/Tuple references that d592c92 orphaned are all annotation-only. Under PEP 563 (`from __future__ import annotations`) function parameter annotations are stored as strings and never evaluated at def time; PEP 526 annotations on local variables inside a function …

## Files reviewed with no behavior change

172 files reviewed, 0 skipped. Full per-finding evidence (commands run, file:line refs, refuter reasoning) is in `d592c92-lost-logic-audit.json` beside this file.

## Related
- CMOS learnings #142 (second casualty), #144 (mechanism); decision #376 (stats-cache restore).
- Stats-cache restore branch: `fix/project-stats-cache-key`.
- Prior known casualty: T33.1 LayerDiagnostic (S49 planning note).


## RECOVER-1 implementation ledger — 2026-09-12

The historical audit above remains a record of `0d63d97` and its ancestors.
This ledger records the surgical restoration against `8b049ed`; it does not
claim production completion before the deployment checks pass. The roadmap
remains the intent authority: `cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md`.

| Audited loss | Recovery commit | Regression coverage |
| --- | --- | --- |
| Ingestion Stage 6 and its import | `2f9c183` | `tests/test_ingestion_edge_materialization.py` (including durable document/chunk edges after caller rollback) |
| `LayerDiagnostic` class, metadata fields, serializer and package re-export | `2f9c183` | `tests/unit/test_recovery_search_diagnostics.py`; `tests/test_recovery_routes.py::test_full_pedr_http_preserves_diagnostics_and_emits_layer_events` |
| PEDR exception hierarchy package re-exports | `2f9c183` | `test_package_reexports_diagnostics_and_exception_hierarchy` |
| `enable_graph`, depth, seed count, graph weight and derived layer weights | `2f9c183` | `test_tuned_defaults_reach_the_rest_search_request` |
| Phase 1 syntactic/pragmatic fallbacks | `2f9c183` | `test_analysis_failure_uses_neutral_filters_without_retrying_broken_service`; `test_disabled_layers_do_not_run_analysis_or_boost` |
| Phase 4 syntactic/pragmatic/governance fallbacks | `2f9c183` | `test_failed_layer_keeps_results_and_reports_degradation`; `test_governance_failure_cannot_bypass_explicit_filters` |
| Structured lexical/semantic/graph failure logging | `2f9c183` | `test_failed_layer_keeps_results_and_reports_degradation` asserts layer and exception fields |
| `RelationType.CO_OCCURS`, `TOPIC_SIMILAR` (both audit entries) and `EDGE_TYPES` | `2f9c183` | `tests/test_semantic_edge_types.py`; package/enum contract coverage |
| Evidence auto-linking telemetry envelope and write-failure isolation | `2f9c183` | `tests/unit/test_recovery_evidence_telemetry.py`; `tests/test_evidence_auto_linking.py` |
| YAML export stored-protocol/canonical fallback | `2f9c183` | `tests/test_mission_protocol_service.py::test_export_canonical_mission_without_legacy_protocol`; existing YAML round trip |
| Mission update explicit protocol / stored protocol / canonical dispatch | `2f9c183` | `test_update_canonical_mission_without_legacy_protocol`; existing protocol update tests |
| Mission-events router mount and authenticated EventSource | `2f9c183` | `tests/test_recovery_routes.py`; `tests/test_mission_events.py`; `tests/test_e2e_smoke.py` |
| Decision-links router mount | `2f9c183` | `test_openapi_registers_restored_verbs_once`; admin read/write and non-admin denial cases in `tests/test_recovery_routes.py` |

### Adaptations to current contracts

- `materialize_implicit_edges(session=db)` no longer commits caller-owned sessions;
  ingestion now commits successful edge writes and rolls back a failed edge stage
  without losing the already committed document/chunks.
- REST graph defaults now match the tuned dataclass defaults. The old restore alone
  would leave normal HTTP searches on disabled graph / depth 1 / weight .08.
- Failed query analysis uses neutral dataclasses, so its fallback cannot call the
  same failed service again. Failed responses bypass the result cache. Explicit
  governance filters fail closed if scoring cannot evaluate them.
- CMOS decisions have no TraceLab owner or Space; every decision-link route is
  admin-only before SQLite access. Event lists/replay/live delivery filter real
  mission IDs/UUIDs using `accessible_filter`; unscoped CMOS/PEDR events are privileged
  only. CMOS event writes use the existing service-principal boundary under RBAC.
- The EventSource route has an authenticated SSE mount, preserving query-token
  support; JSON reads use `protected_dependencies`. The bridge has a separate
  service mount with `require_authenticated_principal`, matching the existing
  mission log/evidence mounts. Real JWT and API-key tests cover both RBAC states;
  dependency overrides must not hide the shared human gate. Subscription
  begins before replay, snapshots the history deque, and closes on disconnect.
- Twenty-four quarantined tests are re-enabled (46 → 22). Six evidence fixtures
  needed current owner/Space columns; one event smoke needed the current PATCH
  verb. One scoped-search test had conformed to the diagnostics deletion and now
  checks the restored metadata while retaining its scope assertions.

### Validation record

New search/telemetry/canonical-dispatch regressions failed before restoration;
all 14 new route tests also failed in an isolated `origin/main` checkout at
`0d63d97`. Targeted recovery and RBAC harness runs pass. Frontend: 66 tests, type-check,
and production build pass. Ruff, secret scan, and foundational refs pass.
The legacy CMOS asset runner passes 13/15 checks; the missing Boomerang
directory and obsolete agent-heading checks also fail on baseline. The full backend pass recorded 2,343 passing tests, three test-contract failures,
three explicit skips and 22 deselections. After correcting those contracts, the
final targeted recovery/RBAC suite passed 149 tests with no skips. PostgreSQL
recorded 124 passes, four explicit skips and one stale telemetry assertion; the
complete affected ingest file then passed all 10 tests. Hosted CI/deploy outcomes
remain required before mission closure. Telemetry emitter
losses outside evidence auto-linking, SQLite test-engine kwargs, schema parity,
and the later-restoration completeness sweep remain RECOVER-2 work.

### RECOVER-1 final verification

Merged in PR #254 as `429ac59` after all six required checks passed on `7ca1d7c`:
2,352 backend tests passed, three explicit skips, and 22 quarantined deselections.
PostgreSQL integration passed. Service authentication was corrected in `83b3c4f`;
real JWT/API-key tests cover the service mount, and `7ca1d7c` adapts the duplicate
route guard to both eager and lazy FastAPI routers.

Railway deployed `429ac59`. Thirty production HTTP checks passed: test ingestion
inserted four graph edges (60,301 → 60,305), full PEDR returned six diagnostics with
`degraded=false`, restored routes appeared in OpenAPI, and member/viewer/service
route boundaries held. The complete owner-based live RBAC harness passed after
deploy, with its existing scope notes retained in the validation record. Test
users and the mission were purged; the smoke document/project were soft-deleted
through the supported APIs. API health and frontend returned HTTP 200.

An extra local full-suite reproduction hit the existing 5 ms graph-latency
assertion; the isolated baseline also fails that threshold. The final hosted
suite passes the unchanged test. The two legacy CMOS asset-runner failures
remain disclosed above. See `cmos/reports/sprint-50/recover-1-validation.json` and
`cmos/reports/sprint-50/recover-1-production-smoke.json` for the recorded evidence.

## RECOVER-2 closure ledger — 2026-09-12

Implementation: `93ab9fb`. All **51 findings** now have explicit dispositions: **43 restored**, **7 superseded**, **1 intentionally-declined**. The count is the 49 confirmed entries plus the two originally unverified router candidates; the single refuted candidate remains excluded. Separate footprints of the same feature retain separate IDs.

### Every finding

| ID | File / symbol | Disposition | Commit | Reason |
|---|---|---|---|---|
| F01 | `app/services/pedr/__init__.py` — module-level imports / __all__ (LayerDiagnostic re-export) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F02 | `app/services/document_ingestion.py` — DocumentIngestionService.process_document | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F03 | `app/services/document_ingestion.py` — module imports | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F04 | `app/services/pedr/search_orchestrator.py` — PEDRConfig.enable_graph | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F05 | `app/services/pedr/search_orchestrator.py` — PEDRConfig.graph_depth | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F06 | `app/services/pedr/search_orchestrator.py` — PEDRConfig.graph_top_k_seeds | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F07 | `app/services/pedr/search_orchestrator.py` — LayerDiagnostic / PEDRMetadata.layer_diagnostics / PEDRMetadata.degraded / PEDRSearchResponse.to_dict / __all__ | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F08 | `app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (Phase 1 pre-analysis) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F09 | `app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (Phase 4 syntactic boost / pragmatic boost / governance scoring) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F10 | `app/services/pedr/relational.py` — RelationType | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F11 | `app/services/mission_protocol_service.py` — export_mission_yaml | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F12 | `app/services/evidence_auto_linking.py` — EvidenceAutoLinkingService._log_telemetry | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F13 | `app/services/pedr/search_orchestrator.py` — DEFAULT_GRAPH_WEIGHT (module constant; feeds PEDRConfig.graph_weight and DEFAULT_LAYER_WEIGHTS) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F14 | `app/services/pedr/search_orchestrator.py` — PEDRSearchOrchestrator.search (lexical/semantic/graph failure logging) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F15 | `app/services/pedr/search_orchestrator.py` — _emit_graph_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F16 | `app/services/cache_manager.py` — CacheManager._write_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F17 | `app/services/cost_monitor.py` — CostMonitor._append_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F18 | `app/services/quality_gate_service.py` — _FileTelemetrySink.__call__ | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F19 | `app/services/mission_protocol_service.py` — update_mission | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F20 | `app/services/quality_checks.py` — _QualityAutomationTelemetry.__call__ | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F21 | `app/services/pedr/semantic_protocol.py` — EDGE_TYPES (module-level frozenset constant, exported in __all__) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F22 | `app/services/pedr/relational.py` — RelationType (str, Enum) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F23 | `app/services/correction_queue.py` — CorrectionQueueService._log_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F24 | `app/services/pedr/__init__.py` — module-level imports / __all__ (PEDR exception hierarchy re-exports) | restored | `2f9c183` | RECOVER-1 restored this behavior with regression coverage, green hosted CI, and authenticated production smoke; see recover_1_verification. |
| F25 | `app/services/pedr/delta_sync.py` — DeltaSyncService._log_sync_event | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F26 | `app/services/webhook_client.py` — WebhookClient._log_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F27 | `app/services/pedr/preflight.py` — PreflightService._emit_telemetry | restored | `93ab9fb` | Real writer delegates to emit_telemetry with the Sprint-36/38 event type, source, and payload; append and unwritable-sink regressions pass. |
| F28 | `app/core/database.py` — module-level engine construction (engine = create_engine(...)) | restored | `93ab9fb` | Test SQLite URLs use StaticPool and check_same_thread=False; a fresh-interpreter cross-thread test shares committed data. Production SQLite and PostgreSQL keep existing pool options. |
| F29 | `app/schemas/pedr_search.py` — module imports / PEDRLayerDiagnostic, PEDRSearchMetadata | restored | `2f9c183` | Typed PEDRLayerDiagnostic and metadata layer_diagnostics/degraded are present and mapped from service responses; RECOVER-1 restored the behavior that the earlier annotation-only audit had overstated. |
| F30 | `app/api/v1/auth.py` — login | restored | `2cd6d67` | Login calls auth_rate_limiter.check(request) before user lookup or password verification; success and failure attempts consume the budget. |
| F31 | `app/api/v1/auth.py` — register | superseded | `3f3955f` | Registration is throttled before DB/bcrypt using its own register_rate_limiter budget; retain Sprint-48 isolation from the login budget and trusted proxy keying. |
| F32 | `app/api/v1/auth.py` — login | restored | `2cd6d67` | Failed login emits auth_failure with sanitized email/client IP and a uniform invalid_credentials reason; disabled accounts are also audited. |
| F33 | `app/api/v1/auth.py` — register | restored | `3f3955f` | Duplicate-email, invalid-invite, and expired-invite registration paths each emit sanitized auth_failure warnings before rejecting. |
| F34 | `app/api/v1/auth.py` — _get_client_ip / _log_auth_failure | superseded | `3f3955f` | Shared client_ip(request) and _log_safe replace the deleted helpers; trusted rightmost-XFF handling and sanitized direct warnings preserve auditing with stronger spoof/injection defenses. |
| F35 | `app/api/v1/auth.py` — module imports | restored | `2cd6d67` | logging, Request, the rate-limit helpers, and module logger are imported and used by the live login/register routes. |
| F36 | `app/services/mission_protocol_service.py` — create_mission_from_draft | restored | `21271b5` | create_mission_from_draft validates quality/progress, maps to canonical MissionCreate, retains the draft in context, writes quality metrics in execution_metadata, and synchronizes evidence. |
| F37 | `app/services/mission_protocol_service.py` — create_mission | superseded | `21271b5` | Canonical create_mission delegates to MissionService; legacy protocol input has the explicit create_mission_from_draft entry point. The removed mission_data schema/ORM field is intentionally not revived. |
| F38 | `app/services/mission_protocol_service.py` — _PROTOCOL_STATUS_MAP / _map_protocol_status | superseded | `21271b5` | _protocol_status/_canonical_status translate completed/complete and review/in_progress at the service boundary; current typed drafts supply the draft default rather than the old nullable map. |
| F39 | `app/services/mission_protocol_service.py` — _determine_status | superseded | `21271b5` | Callers normalize completed to complete before _determine_status; failed gates still reject completion/review and prevent automatic completion. The old extra completed literal is unnecessary at this internal boundary. |
| F40 | `app/services/mission_protocol_service.py` — import_mission_yaml | restored | `21271b5` | YAML import validates MissionProtocolDraft then invokes create_mission_from_draft with requested_status=draft.status; round-trip service coverage passes. |
| F41 | `app/services/quality_checks.py` — QualityAutomationService.evaluate | restored | `6a3c514` | QualityAutomationService.evaluate uses stored Mission Protocol context when valid, otherwise canonical mission_id/title; malformed legacy context is logged and falls back safely. |
| F42 | `app/models/chunk.py` — DocumentChunk.content_tsv | intentionally-declined | `93ab9fb` | Keep nullable=False: migration 006 and read-only live PostgreSQL inspection both declare a NOT NULL generated tsvector. Restoring the older nullable=True model would introduce drift; no migration needed. |
| F43 | `app/api/v1/missions.py` — import_mission (POST /import) | superseded | `065a452` | POST /missions/import uses dict[str, Any] with Any imported, eliminating the stale Dict annotation while preserving the YAML adapter route. |
| F44 | `app/services/pedr/edge_materialization.py` — EdgeMaterializationService._collection_cooccurrence_edges (reached via _implicit_edge_specs / materialize_implicit_edges) | restored | `065a452` | Collection is imported and used in the co-occurrence join; semantic edge materialization coverage executes the query. |
| F45 | `app/core/security.py` — require_authenticated_user_sse | superseded | `065a452` | SSE auth uses modern union annotations and validates query JWTs/header credentials; current human/service boundaries and RECOVER-1 real-token route tests remain intact. |
| F46 | `app/api/v1/deepsearch.py` — ingest_deepsearch_payload | restored | `21271b5` | DeepSearch ingest calls create_mission_from_draft after real evidence linking and quality checks; the re-enabled HTTP test persists a canonical mission. |
| F47 | `app/api/v1/deepsearch.py` — ingest_deepsearch_payload | restored | `21271b5` | Evidence linking metadata is merged into execution_metadata without dropping existing quality/progress entries; the deterministic HTTP test verifies the persisted keys. |
| F48 | `app/api/v1/deepsearch.py` — ingest_deepsearch_payload | restored | `21271b5` | DeepSearch quality_gates response reads execution_metadata with report fallback; the HTTP regression compares response and stored quality gates. |
| F49 | `app/api/v1/deepsearch.py` — ingest_deepsearch_payload | restored | `21271b5` | DeepSearch response mission_id comes directly from the canonical Mission column; the HTTP regression asserts it equals the submitted protocol ID. |
| F50 | `app/main.py` — module-level app.include_router(...) sequence (mission_events router mount) | restored | `83b3c4f` | Router mounted and verified with real JWT/API-key authorization at actual app mounts; CMOS bridge uses the dedicated service-principal boundary. Production smoke and owner RBAC matrix passed. |
| F51 | `app/main.py` — module-level app.include_router(...) sequence (decision_links router mount) | restored | `83b3c4f` | Router mounted and verified with real JWT/API-key authorization at actual app mounts; CMOS bridge uses the dedicated service-principal boundary. Production smoke and owner RBAC matrix passed. |

### Completeness of the 20 earlier reimplementation claims

- **F29** — `2f9c183` (confirmed at `93ab9fb`): Typed PEDRLayerDiagnostic and metadata layer_diagnostics/degraded are present and mapped from service responses; RECOVER-1 restored the behavior that the earlier annotation-only audit had overstated.
- **F30** — `2cd6d67` (confirmed at `93ab9fb`): Login calls auth_rate_limiter.check(request) before user lookup or password verification; success and failure attempts consume the budget.
- **F31** — `3f3955f` (confirmed at `93ab9fb`): Registration is throttled before DB/bcrypt using its own register_rate_limiter budget; retain Sprint-48 isolation from the login budget and trusted proxy keying.
- **F32** — `2cd6d67` (confirmed at `93ab9fb`): Failed login emits auth_failure with sanitized email/client IP and a uniform invalid_credentials reason; disabled accounts are also audited.
- **F33** — `3f3955f` (confirmed at `93ab9fb`): Duplicate-email, invalid-invite, and expired-invite registration paths each emit sanitized auth_failure warnings before rejecting.
- **F34** — `3f3955f` (confirmed at `93ab9fb`): Shared client_ip(request) and _log_safe replace the deleted helpers; trusted rightmost-XFF handling and sanitized direct warnings preserve auditing with stronger spoof/injection defenses.
- **F35** — `2cd6d67` (confirmed at `93ab9fb`): logging, Request, the rate-limit helpers, and module logger are imported and used by the live login/register routes.
- **F36** — `21271b5` (confirmed at `93ab9fb`): create_mission_from_draft validates quality/progress, maps to canonical MissionCreate, retains the draft in context, writes quality metrics in execution_metadata, and synchronizes evidence.
- **F37** — `21271b5` (confirmed at `93ab9fb`): Canonical create_mission delegates to MissionService; legacy protocol input has the explicit create_mission_from_draft entry point. The removed mission_data schema/ORM field is intentionally not revived.
- **F38** — `21271b5` (confirmed at `93ab9fb`): _protocol_status/_canonical_status translate completed/complete and review/in_progress at the service boundary; current typed drafts supply the draft default rather than the old nullable map.
- **F39** — `21271b5` (confirmed at `93ab9fb`): Callers normalize completed to complete before _determine_status; failed gates still reject completion/review and prevent automatic completion. The old extra completed literal is unnecessary at this internal boundary.
- **F40** — `21271b5` (confirmed at `93ab9fb`): YAML import validates MissionProtocolDraft then invokes create_mission_from_draft with requested_status=draft.status; round-trip service coverage passes.
- **F41** — `6a3c514` (confirmed at `93ab9fb`): QualityAutomationService.evaluate uses stored Mission Protocol context when valid, otherwise canonical mission_id/title; malformed legacy context is logged and falls back safely.
- **F43** — `065a452` (confirmed at `93ab9fb`): POST /missions/import uses dict[str, Any] with Any imported, eliminating the stale Dict annotation while preserving the YAML adapter route.
- **F44** — `065a452` (confirmed at `93ab9fb`): Collection is imported and used in the co-occurrence join; semantic edge materialization coverage executes the query.
- **F45** — `065a452` (confirmed at `93ab9fb`): SSE auth uses modern union annotations and validates query JWTs/header credentials; current human/service boundaries and RECOVER-1 real-token route tests remain intact.
- **F46** — `21271b5` (confirmed at `93ab9fb`): DeepSearch ingest calls create_mission_from_draft after real evidence linking and quality checks; the re-enabled HTTP test persists a canonical mission.
- **F47** — `21271b5` (confirmed at `93ab9fb`): Evidence linking metadata is merged into execution_metadata without dropping existing quality/progress entries; the deterministic HTTP test verifies the persisted keys.
- **F48** — `21271b5` (confirmed at `93ab9fb`): DeepSearch quality_gates response reads execution_metadata with report fallback; the HTTP regression compares response and stored quality gates.
- **F49** — `21271b5` (confirmed at `93ab9fb`): DeepSearch response mission_id comes directly from the canonical Mission column; the HTTP regression asserts it equals the submitted protocol ID.

### Schema, quarantine, and validation

`DocumentChunk.content_tsv` remains NOT NULL, matching migration 006 and the live generated column at Alembic head `043_deepsearch_evidence`. CMOS decision #382 records why the nullable=True declaration was declined. See [read-only schema evidence](../sprint-50/recover-2-schema-verification.json).

Ten tests return to the required backend suite (22 → 12 quarantines). Eight cover recovered telemetry, one exercises real DeepSearch linking/persistence with deterministic external providers, and one covers all twelve graph queries. Remaining reasons name reproduced failures: ten historical evaluators do not unwrap envelopes, the admin cost fixture is outside its rolling date window, and document detail lacks the test’s processing_events field. These are not evidence of a retired quality/telemetry contract.

The required lint job checks formatting-only claims against non-whitespace net deletions in every commit, preserving AST-equivalent Python formatting. It detects d592c92 and a bad intermediate commit hidden by a later repair. See [validation evidence](../sprint-50/recover-2-validation.json) for local and hosted results. Test-generated telemetry is excluded from commits.

### RECOVER-2 final verification

PR [#255](https://github.com/kneelinghorse/TraceLab/pull/255) merged as `6155d88` and deployed successfully on Railway (backend deployment `5096255a-d883-4cc3-ae06-9e44b927c2d2`). All six required CI checks pass on `1d47346`: backend **2,391 passed / 3 skipped / 12 deselected**, PostgreSQL integration **125 passed / 4 skipped**. Existing mypy/full-Ruff/frontend-lint advisories remain documented in the validation report; mypy stays at 1,039 errors.

The deployed-container smoke verified all nine real writers’ envelope fields, complete payloads, append behavior, and isolation from an unwritable sink against the exact merge commit, then removed its temporary files. Five live HTTP checks returned 200 (API health, profile, graph stats, cache stats, and frontend missions). See [production evidence](../sprint-50/recover-2-production-smoke.json). No generated telemetry was committed.
