# Admin observability — UX-4

Guided by the application architecture in `foundational-docs/tech_arch_template.md` and the UI definition of done in `cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md`.

`GET /api/v1/admin/stats` requires an authenticated admin or owner even when the RBAC rollout flag is disabled. Anonymous callers receive 401; member and service principals receive 403. The response is private and not cacheable.

The repository queries SQL aggregates over the full system, independent of the six recent mission rows or any list page size. `missions.total` and `missions.by_status` use the persisted seven-status vocabulary, including `completed` and `validation_failed`. Projects and documents exclude soft-deleted rows; chunks exclude soft-deleted parent documents. Reports, ingestion jobs, graph edges by type, ledger entries, canonical sources and working notes count all retained records, including records associated with deleted projects. Ingestion state names come directly from storage.

The service adds a five-second bounded probe of the existing worker health URL. Missing, negative or malformed counters stay null. A timeout says the observation is unavailable; it does not assert that the worker is offline or that it completed zero missions. Observed zero remains zero. Worker counters cover its process lifetime. Reconciler `last_run_at` and correction-queue totals come from the current API process; the UI explicitly states that these observations reset on restart. A failed correction dependency does not erase persisted aggregates or pretend the queue is empty.

`/admin/observability` and `/admin/corrections` use the shared authenticated HTTP client and fail-closed `RequireAdmin`. User-scoped SWR snapshots refresh every 30 seconds and expose their update time, initial loading, retry, and stale-on-refresh-error states. The observability page links recent missions to the canonical mission route. Quality is not inferred from mission status.

Permanent server redirects preserve inbound bookmarks and queries:

| Old path | Destination |
| --- | --- |
| `/console` | `/admin/observability` |
| `/console/corrections` | `/admin/corrections` |
| `/console/missions` | `/missions` |
| `/console/missions/:id` | `/missions/:id` |

The duplicate console pages and page-derived dashboard aggregation have been removed. Corrections retain the existing trigger, process and clear-completed API operations with explicit user actions, server result notices and retryable errors. The dead-letter view reports the API's complete count separately from the first 50 returned items. Its unimplemented Clear All button has been removed. Existing correction API authorization and worker contracts are unchanged.

Validation: `tests/test_admin_stats.py`, `tests/integration/test_admin_stats_postgres.py`, `frontend/src/__tests__/admin/observability.test.tsx`, and `frontend/tests/e2e/console.spec.ts`. `frontend/scripts/admin-smoke.mjs` checks the built or deployed UI in both themes at 390/820/1440 pixels, verifies whole-system mission totals against list totals for each status, and blocks every API write. Mutation behavior is exercised through mocked UI responses and existing correction API tests, not production queue changes.
