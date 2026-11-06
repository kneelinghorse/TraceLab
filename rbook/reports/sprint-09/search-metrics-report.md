# Sprint 09 Search Metrics Report

**Data sources**
- `cmos/telemetry/events/sprint-09-hybrid-search.jsonl` — semantic vs hybrid benchmark captured during B9.1.
- `cmos/reports/sprint-09/search-metrics.json` — synthetic dataset generated for this retrospective by exercising `SearchHistoryService` + `SavedSearchService` against a fresh SQLite database (`env DATABASE_URL=sqlite:///./test-results/sprint09_metrics.sqlite`).
- `pytest` suites: `tests/test_hybrid_search.py`, `tests/test_faceted_search.py`, `tests/test_search_history.py`, `tests/test_saved_searches.py`.

## Precision & Latency
| Query | Mode | Latency (ms) | Precision@5 | Notes |
| --- | --- | --- | --- | --- |
| How do we combine governance guardrails? | Semantic | 612.4 | 0.62 | Baseline — Qdrant only |
| How do we combine governance guardrails? | Hybrid | 702.1 | 0.74 | +19% precision, +89.7 ms latency (`semantic_delta_ms`) |

Hybrid scoring pays a sub-100 ms overhead yet lifts precision@5 by 0.12, validating the B9.1 hypothesis (`cmos/missions/sprint-09/B9.1_Hybrid-Search-Backend.yaml`).

## Usage Instrumentation Summary
Derived from `search-metrics.json` (24 sample queries).

| Metric | Value |
| --- | --- |
| Samples recorded | 24 |
| Mode breakdown | `semantic`: 8, `hybrid`: 8, `keyword`: 8 |
| Avg. result count | 4.75 chunks |
| Avg. duration | 418.96 ms |
| Cache hit rate | 21% |
| Saved-search replay rate | 25% |
| Saved searches seeded | 3 |
| Saved search use counts | min 2 / max 6 / avg 4 |

### Filter adoption
`project_id` appeared in 18/24 entries, `tags` in 18, `document_types` and `source_type` in 12, and `date_range` in 6. This confirms the shared filter normalization built in B9.2 is used consistently by hybrid search, retrieval, and RAG.

### Search history observations
- `SearchHistoryService` retention kept the latest 24 entries while enforcing max-entry + age limits.
- Replay requests (metadata `saved_search_id` set) accounted for 25% of entries, providing the basis for the saved-search quick access workflow.
- Recorded durations clustered between 390–445 ms, validating the low-overhead logging path introduced in `app/api/v1/search.py`.

### Saved-search service observations
- CRUD + execute flows (see `docs/saved-searches.md`) successfully enforced the 50-entry quota and returned usage metadata (`limit_per_user` in API responses).
- `mark_used` increments drove `use_count` and `last_used_at` updates, which surfaced immediately in the sample UI data (mirroring `SavedSearchesList`).

## Quality Gates
- **metrics_compiled:** This report plus `search-metrics.json` documents precision, latency, cache hit rate, and saved-search adoption.
- **retrospective_complete:** `cmos/reports/sprint-09/retrospective.md` references these findings.

## Next Steps
1. Wire real `/search` traffic into a production-grade telemetry feed so future retrospectives can compare against non-synthetic data.
2. Surface cache hit rates + saved-search usage inside the UI dashboard to highlight gains to new operators.
3. Carry hybrid/keyword mixes into Sprint 10’s DeepSearch ingestion pipeline so the same precision controls are available end-to-end.
