# Saved Searches Feature

Mission **B9.5 Saved Searches** introduces reusable query bookmarks so researchers can
pin their most effective prompts, replay them instantly, and manage the list without
leaving TraceLab. The implementation mirrors the `foundational-docs/tech_arch_template.md`
expectations: schema + migration, FastAPI service layer, React components, and pytest
coverage.

## Data Model

| Column | Description |
| --- | --- |
| `id` | UUID primary key (generated server-side). |
| `name` | User-provided label (per-user unique). |
| `description` | Optional free-form summary for teams. |
| `query_text` | Saved query string. |
| `search_mode` | `semantic`, `keyword`, or `hybrid` (currently defaults to `semantic`). |
| `filters` | JSON serialization of the applied project/type/date filters. |
| `top_k` | Chunk fan-out for semantic retrieval. |
| `owner` | Username from `require_authenticated_user`. |
| `use_count` | Number of executions recorded via the API. |
| `last_used_at` | UTC timestamp updated whenever the saved search runs. |
| `created_at` / `updated_at` | Timestamps managed by SQLAlchemy. |

The schema is delivered via `alembic/versions/009_add_saved_searches.py`, which enforces:

- Unique `(owner, name)` combinations
- Indexed `owner + created_at` lookups for quick dashboards
- 50-entry per-user guardrail (enforced in `SavedSearchService`)

## API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v1/saved-searches` | GET | List searches for the authenticated user + return quota metadata. |
| `/api/v1/saved-searches` | POST | Create a saved search (name, description, query, filters, `top_k`). |
| `/api/v1/saved-searches/{id}` | PUT | Update name/description/query settings. |
| `/api/v1/saved-searches/{id}` | DELETE | Remove a saved search (and free up quota). |
| `/api/v1/saved-searches/{id}/execute` | POST | Run the saved search, returning semantic + RAG payloads and logging usage in search history. |

Execution reuses `RagService` plus `RetrievalService`, then records a new row via
`SearchHistoryService` with `metadata.saved_search_id=<id>` so telemetry can track
derivative usage.

## Frontend Integration

- **Search experience (`SearchExperience.tsx`)**
  - Adds SWR-powered saved-search quick access alongside query history.
  - Inline `SaveSearchButton` handles creation from the active query or from a history entry.
  - `SavedSearchesList` surfaces run, load filters, and delete actions with usage stats.
  - Running a saved search calls the execute endpoint, updates UI state, and refreshes SWR caches.

- **Management page (`pages/saved-searches.tsx`)**
  - Dedicated AuthGate-protected page for editing metadata, adjusting `Top K`, or cleaning up entries.
  - Shares the same SWR key so updates propagate instantly back to the search experience.

All client requests go through `frontend/src/lib/api/savedSearches.ts`, which keeps
snake_case payloads aligned with the FastAPI schema.

## Validation & Tests

- **Pytest**: `tests/test_saved_searches.py` covers CRUD, retention limits, and execute flow (with stubbed RAG/retrieval services).
- **Manual checks**: exercise `/saved-searches` UI, leverage quick access panel on `/search`, and confirm history entries can be saved.
- **Docs + Parity**: Exported backlog/context mirrors via `./cmos/cli.py db export backlog|contexts`,
  regenerated `cmos/SESSIONS.jsonl`, and ran `python cmos/scripts/validate_parity.py --check` (green).

Before shipping, re-run `pytest tests/test_saved_searches.py tests/test_search_history.py`
plus any impacted suites, then capture telemetry per `cmos/docs/AI-coding-assistant-workflows.md`.
