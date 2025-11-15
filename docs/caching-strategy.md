# Query Result Caching Strategy

Sprint 08 introduces a dedicated application-level caching layer that wraps the most expensive read paths with short-lived, in-memory TTL caches. The goal is to reduce OpenAI/Qdrant usage, flatten database load, and give the monitoring endpoints clear insight into cache efficiency.

## Architecture

- `app/core/cache.py` provides a thread-safe `TTLCache` wrapper with stats, invalidation helpers, and a decorator for simple memoisation.
- `app/services/cache_manager.py` centralises cache configuration, key builders, invalidation helpers, and telemetry logging (`cmos/telemetry/events/sprint-08-cache-metrics.jsonl`).
- Cached operations use the manager's `cached_value` helper so every request receives a fresh copy of the cached payload while statistics stay accurate.

## Cache Targets & TTLs

| Cache Bucket | TTL | Description |
|--------------|-----|-------------|
| `rag_query_results` | 5 minutes | Wraps `RagService.run_query` before embeddings/retrieval are computed. Cached responses skip OpenAI/Qdrant but still inherit semantic cache metadata. |
| `document_lists` | 2 minutes | Caches the paginated payload returned by `GET /api/v1/documents`. Invalidated on uploads, metadata updates, processing, deletions, and onboarding events. |
| `project_metadata` | 5 minutes | Covers `GET /api/v1/projects` (list) and `GET /api/v1/projects/{id}`. Invalidated by onboarding project create/update operations. |
| `quality_gates` | 60 seconds | Caches `GET /api/v1/quality/missions/{mission_id}/quality`. Invalidated whenever missions update, are created/deleted, or quality automation runs. |
| `mission_validation` | 30 seconds | Memoises `MissionProtocolService` draft validation so the Mission Protocol CRUD endpoints can re-validate identical payloads without re-running every Pydantic check. Invalidated with mission lifecycle changes. |

All cache hits include `cache.layer="ttl"` metadata on the response plus the configured TTL so client telemetry can distinguish TTL hits from the existing semantic cache.

## Invalidation Rules

- **Documents** – uploading, registering, updating, processing, or deleting a document (via FastAPI or onboarding APIs) calls `CacheManager.invalidate_document_lists(project_id)` so filters/page caches refresh immediately.
- **Projects** – onboarding project create/update hooks call `invalidate_project_metadata`, removing the detail cache for that ID and list caches for all filters.
- **Missions** – Mission CRUD operations clear both mission validation and quality gate caches. Quality automation runs also clear cached quality reports to ensure the next read hits the database.
- **Manual controls** – `POST /api/v1/cache/clear` allows operators to flush any subset of caches on demand while streaming a metrics snapshot back to the client.

## Monitoring & Telemetry

- `GET /api/v1/cache/stats` returns the live hit/miss counters, size, and TTL configuration for each bucket and appends the snapshot to `cmos/telemetry/events/sprint-08-cache-metrics.jsonl`.
- `GET /api/v1/monitoring/performance` now surfaces the TTL cache snapshot under `ttl_caches` in addition to the semantic cache metrics and routing data.
- Cache metrics use the same UTC timestamping as other telemetry feeds so parity checks can compare cache behaviour before and after missions.

## Testing Coverage

`tests/test_caching.py` verifies:

- The TTL decorator reuses results and isolates registries for unit tests.
- Document cache keys/invalidation behave as expected.
- Telemetry snapshots are written whenever the manager logs a snapshot.

Run `pytest tests/test_caching.py` (or the full suite) after modifying cache behaviour to ensure correctness.
