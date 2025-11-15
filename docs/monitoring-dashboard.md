# Cost Monitoring Dashboard

The admin dashboard at `/admin/dashboard` provides a single page view of OpenAI usage, cache efficiency, query performance, and core system health. It is rendered server-side with Jinja2 and auto-refreshes every 30 seconds so operators can keep tabs on spend and latency without leaving the FastAPI service.

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

The aggregator is exposed via `get_metrics_aggregator()` so API endpoints and the HTML page share the same logic. Failures talking to external systems (database, Qdrant, telemetry files) are captured in the response payload instead of raising hard errors, ensuring the dashboard always renders.

## Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /admin/dashboard` | Authenticated HTML dashboard with live charts and auto-refresh |
| `GET /api/v1/admin/dashboard` | Same HTML view scoped to API prefix |
| `GET /api/v1/admin/dashboard/data` | JSON payload for SPA refreshes or automation |
| `GET /api/v1/admin/dashboard/export?format=csv` | CSV download of flattened metrics |

All routes require a valid bearer token (`/api/v1/auth/login`). When the HTML page is loaded with an `Authorization` header, the same token is injected into the client-side refresh script so subsequent AJAX calls stay authorized.

## Usage

1. Authenticate to retrieve a JWT:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"tracelab-admin","password":"changeme"}'
   ```
2. Hit `/admin/dashboard` or `/api/v1/admin/dashboard` with the `Authorization: Bearer <token>` header using your browser helper or HTTP client.
3. Use the "Export CSV" button or hit `/api/v1/admin/dashboard/export?format=csv` programmatically to archive metrics.

## Tests

`tests/test_admin_dashboard.py` covers aggregator behavior, JSON export, CSV export, and template rendering. Run them with:

```bash
pytest tests/test_admin_dashboard.py
```

These tests stub the underlying services so CI can verify dashboard behavior without live Qdrant or OpenAI dependencies.
