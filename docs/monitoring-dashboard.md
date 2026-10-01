# Cost Monitoring Dashboard

The admin dashboard at `/admin/dashboard` provides a single page view of OpenAI usage, cache efficiency, query performance, and core system health. It is rendered server-side with Jinja2 and auto-refreshes every 30 seconds so operators can keep tabs on spend and latency without leaving the FastAPI service.

This is the legacy dashboard. The current frontend Observability page uses
`/api/v1/admin/stats` and `app/services/admin_stats.py`; its health is independent.

## Features

- **Multi-window cost snapshots** – today, trailing 7 days, and trailing 30 days with per-query averages plus separate embedding vs. generation totals.
- **Chart.js trend visualizations** – daily spend line chart and rolling latency chart fed directly from telemetry JSONL files.
- **Cache performance rollup** – semantic cache metrics and TTL cache inventory with hit-rate badges.
- **Query telemetry insights** – percentile latency cards, slow-query table, and per-hour throughput.
- **System health digest** – database connection health, Qdrant readiness, telemetry freshness, and vector counts.
- **Data exports** – JSON (`/api/v1/admin/dashboard/data`) for automation and CSV (`/api/v1/admin/dashboard/export?format=csv`) for spreadsheets.

## Architecture

`app/services/metrics_aggregator.py` gathers data from existing services:

- `CostMonitor.summary()` for live totals.
- Telemetry JSONL (`telemetry/events/sprint-04-performance.jsonl`) for historic spend/latency and slow-query extraction.
- `CacheManager.snapshot()` and `cache_metrics.snapshot()` for TTL and semantic cache data.
- SQLAlchemy engine health checks for Postgres/SQLite usage.
- `QdrantService` diagnostics for vector collection readiness.

The aggregator is exposed via `get_metrics_aggregator()` so API endpoints and the HTML page share the same logic. Database and Qdrant health failures are captured in their sections. Cache snapshot failures preserve other observations and report `ttl_status` / `semantic_status` as `unavailable`, with null aggregate values. Unknown event latency is excluded from the slow-query sort while the event remains in the cost history.

Cache counters have `scope: process_local_since_start`: they reset on process restart and are not a fleet-wide persistence measure. The existing hit counter also includes application-TTL replays from RAG. A hit rate alone does not prove a successful Qdrant write. `error_categories` separates initialize, lookup, write and maintenance failures into a fixed vocabulary; Prometheus exposes the same bounded labels through `semantic_cache_failures_total`. Warning logs contain only those labels, at most once per pair per minute. They never include exception text, queries, answers, vectors, credentials or URLs.

`python -m scripts.cache_diagnostic` verifies the deployed serializer/write/read
path without a model call. It generates a unique `s62-cache-diagnostic-*`
collection, writes one synthetic entry, verifies replay and a different-project
miss, then deletes only that invocation's collection. It does not write or clear
the configured application or semantic cache collection. Run it explicitly in
the target service and retain its output together with the serving SHA. Its
counters belong to the diagnostic process, not the API process. A passing check
cannot explain why the production cache was empty at an earlier observation.

## Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /admin/dashboard` | Authenticated HTML dashboard with live charts and auto-refresh |
| `GET /api/v1/admin/dashboard` | Same HTML view scoped to API prefix |
| `GET /api/v1/admin/dashboard/data` | JSON payload for SPA refreshes or automation |
| `GET /api/v1/admin/dashboard/export?format=csv` | CSV download of flattened metrics |

All routes require a valid bearer token (`/api/v1/auth/login`). When the HTML page is loaded with an `Authorization` header, the same token is injected into the client-side refresh script so subsequent AJAX calls stay authorized.

## Usage

1. Authenticate using the canonical [authentication guide](authentication.md).
2. Hit `/admin/dashboard` or `/api/v1/admin/dashboard` with the `Authorization: Bearer <token>` header using your browser helper or HTTP client.
3. Use the "Export CSV" button or hit `/api/v1/admin/dashboard/export?format=csv` programmatically to archive metrics.

## Tests

`tests/test_admin_dashboard.py` covers aggregator behavior, JSON export, CSV export, and template rendering. Run them with:

```bash
pytest tests/test_admin_dashboard.py
```

These tests stub the underlying services so CI can verify dashboard behavior without live Qdrant or OpenAI dependencies.

`tests/test_semantic_cache_diagnostics.py` additionally uses the real Qdrant SDK
serializer over `httpx.MockTransport`, exercises fresh RAG fallback and scoped
replay, injects failures, and checks bounded secret-free logging. The optional
`tests/integration/test_qdrant_isolation.py --disposable-qdrant` test proves the
round trip against a fixture-owned local Qdrant container.
