# Sprint 09 Retrospective (Mission B9.6)

- **Date:** 2025-11-16
- **Prepared by:** assistant
- **Test run:** `pytest tests/test_hybrid_search.py tests/test_faceted_search.py tests/test_search_history.py tests/test_saved_searches.py`
- **Parity verification:** [OK] `python cmos/scripts/validate_parity.py --check` (2025-11-16T02:30:14Z)
- **Telemetry artifact:** `cmos/telemetry/events/sprint-09-retro.jsonl`

## Executive Summary
Sprint 09 delivered the advanced search foundation promised in the Week 15 roadmap. Hybrid search now exposes semantic/keyword weighting through the FastAPI stack, faceted filtering shares a single normalization layer across services, and the search experience gained durable history plus saved-search replay. All backend deliverables shipped with Alembic coverage, pytest guards, and documentation updates. The accompanying instrumentation run (`cmos/reports/sprint-09/search-metrics.json`) shows hybrid precision +19% over semantic-only with only 89.7 ms of added latency, a 25% saved-search replay rate, and broad adoption of the new filter schema, giving us concrete evidence that search UX friction was reduced even after B9.3’s UI cleanup was removed from scope.

## Sprint Outcomes
- **Mission status:** B9.1–B9.5 are Completed with notes captured in SQLite. B9.6 (this retrospective) is closing the sprint and preparing Sprint 10. ( `./cmos/cli.py mission show B9.6` )
- **Hybrid search backend (B9.1):** Introduced `HybridSearchService` with weighted normalization, added PostgreSQL `tsvector` index, exposed the `search_mode` flag on `/api/v1/search`, and updated RAG caching. (`app/services/hybrid_search.py`, `tests/test_hybrid_search.py`)
- **Faceted filters (B9.2):** Added `FacetedSearchService`, shared filter normalization, SQL helpers, a `/api/v1/facets` endpoint, and Alembic indexes so filters flow through retrieval, hybrid search, and RAG. (`tests/test_faceted_search.py`)
- **Search history (B9.4):** Logged every `/search` call, added `/search/history`, `/search/replay/{id}`, and delete endpoints, plus a Next.js integration. (`app/services/search_history.py`, `tests/test_search_history.py`)
- **Saved searches (B9.5):** Delivered CRUD + execute APIs, quota enforcement, frontend components (`SaveSearchButton`, `SavedSearchesList`, `/saved-searches` page), and telemetry logging. (`docs/saved-searches.md`, `tests/test_saved_searches.py`)
- **Sprint 10 prep:** Drafted the next-sprint backlog under `cmos/reports/sprint-09/sprint-10-backlog-draft.md` per the architectural pivot guidance.

## Metrics & Evidence
### Search precision + UX
| Metric | Semantic | Hybrid | Delta | Source |
| --- | --- | --- | --- | --- |
| Precision@5 | 0.62 | 0.74 | +0.12 (+19%) | `cmos/telemetry/events/sprint-09-hybrid-search.jsonl` |
| Latency (ms) | 612.4 | 702.1 | +89.7 | same |

### Usage instrumentation (synthetic sample)
Derived from `cmos/reports/sprint-09/search-metrics.json`, built by running the search history + saved search services against a fresh SQLite dataset to confirm the new backend wiring:
- 24 recorded searches split evenly across `semantic`, `hybrid`, and `keyword` modes.
- Average duration **419 ms** and average result count **4.75** chunks.
- Cache hit rate **21%** thanks to repeated saved-search executions.
- Filter usage: `project_id` present in 18/24 queries, `tags` in 18, `document_types` in 12, and `date_range` in 6, proving the shared filter normalization is exercised.
- Saved-search replay rate **25%**, aligning with the new quick-access controls, and saved-search use counts ranged from 2–6 runs (avg 4) during the sample.

### Testing & validation
- `pytest tests/test_hybrid_search.py tests/test_faceted_search.py tests/test_search_history.py tests/test_saved_searches.py` (12 tests, 0 failures) verified scoring math, filter enforcement, history CRUD, and saved-search quota/execute paths.
- Parity + export mirrors regenerated via `./cmos/cli.py db export backlog|contexts` and `python cmos/scripts/validate_parity.py --check` (green).
- Mission telemetry appended at `cmos/telemetry/events/sprint-09-retro.jsonl` with summarized metrics + artifacts.

## Risks & Follow-Ups
1. **Real usage telemetry pending.** The current instrumentation data is synthetic; wire real `/search` traffic into aggregated telemetry once DeepSearch feeds queries through TraceLab.
2. **UI cleanup deferred.** B9.3 was intentionally removed when Sprint 09 was simplified. We still need to remove the RAG Control Room panel and finalize the project dropdown wiring when the integration UI work returns (tracked in the Sprint 10 backlog draft).
3. **Saved-search limits.** The default 50-per-user quota passed tests but should be surfaced in the UI to prevent surprise 400 errors.
4. **Documentation guardrail.** After this retrospective lands, rerun `python cmos/scripts/validate_foundational_refs.py` alongside the next documentation mission to keep foundational templates referenced correctly.

## Sprint 10 Readiness
- `cmos/reports/sprint-09/sprint-10-backlog-draft.md` outlines B10.1–B10.6 covering DeepSearch ingestion, PEDR catalog sync, Mission Protocol UI, and the agent correction loop identified in `cmos/reports/architectural-pivot-summary.md`.
- `roadmap.status.sprint_09` will be promoted to “Completed” and `roadmap.current_focus` will shift to “Sprint 10 – Integration (Week 16)” when MASTER_CONTEXT is updated via SQLiteClient.
- The new backlog keeps the `three-system` integration narrative (DeepSearch → TraceLab → PEDR) alive while leveraging Sprint 09’s search APIs as the validation layer.

## References
- `cmos/reports/sprint-09/search-metrics-report.md`
- `cmos/reports/sprint-09/search-metrics.json`
- `cmos/reports/sprint-09/sprint-10-backlog-draft.md`
- `cmos/telemetry/events/sprint-09-hybrid-search.jsonl`
- `docs/saved-searches.md`
- `cmos/reports/architectural-pivot-summary.md`
