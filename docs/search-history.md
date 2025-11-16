# Search History Feature

This feature implements mission **B9.4 Search History** using the templates and quality standards defined in
`foundational-docs/tech_arch_template.md`. It adds a persistent search log, replay APIs, and the corresponding
frontend panel so researchers can revisit high-signal queries quickly.

## Data Model

| Column | Description |
| --- | --- |
| `id` | UUID primary key (generated via `gen_random_uuid()` in PostgreSQL). |
| `query_text` | Full search query string submitted to `/api/v1/search`. |
| `search_mode` | `semantic`, `keyword`, or `hybrid`, normalized to lowercase. |
| `filters` | JSON document storing project/document filters, date ranges, tags, etc. |
| `result_count` | Number of supporting chunks returned for the run. |
| `top_k` | Requested chunk count for the semantic retrieval stage. |
| `duration_ms` | Latency in milliseconds when the query executed. |
| `cache_hit` | Whether either TTL cache or semantic cache served the response. |
| `user_label` | Username captured from `require_authenticated_user`. |
| `metadata_payload` | Additional details (currently latency, quality score, routing model, replay lineage). |
| `top_chunks` | Array of the first five chunk IDs, useful for audit tooling. |
| `created_at` / `updated_at` | UTC timestamps managed by SQLAlchemy. |

Retention is enforced server-side: keep the latest 100 entries and purge anything older than 30 days.

## API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v1/search` | POST | Runs a standard RAG search **and** automatically logs a history entry when successful. |
| `/api/v1/search/history` | GET | Returns recent entries plus retention metadata (`max_entries`, `max_age_days`). Accepts `limit` (1-100). |
| `/api/v1/search/history` | DELETE | Clears all history rows (used by the frontend “Clear history” control). |
| `/api/v1/search/replay/{history_id}` | POST | Replays a prior query, returning fresh semantic + RAG payloads and logging the replay event. |

Replay uses the stored filters to call both `RetrievalService.search` and `RagService.run_query`. Each replay is logged
with `metadata.replay_of = <original_id>` so telemetry and audits can trace derivative runs.

## Frontend Integration

The search experience now:

1. Pulls history via `searchApi.history()` using SWR caching.
2. Displays the latest entries (query, timestamp, filters, `Top K`) in the sidebar.
3. Provides a “Replay” action per row that calls `searchApi.replay(id)` and hydrates both semantic results and the RAG
   synthesis panel without an additional manual search.
4. Offers a “Clear history” button wired to `searchApi.clearHistory()`.

State updates trigger `mutateHistory()` so the UI stays synchronized with the backend retention checks.

## Validation & Tests

- **Database migration**: `alembic/versions/008_add_search_history.py` adds the `search_history` table and indexes.
- **Service tests**: `tests/test_search_history.py` covers logging via `/api/v1/search`, replay behaviors, and clearing.
- **UI smoke**: Next.js components rely on the same mission-driven schema from `foundational-docs/tech_arch_template.md`
  to keep filters consistent with Mission Protocol data contracts.

Run `pytest tests/test_search_history.py` plus existing search-related suites before deploying. Finish with
`python cmos/scripts/validate_parity.py --check` per agents.md to ensure Mission Protocol mirrors remain in sync.
