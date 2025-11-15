# CMOS Integration Testing Guide

This guide documents the Mission Protocol integration checks that back the
`cmos/context/integration_test_runner.js` automation. The runner combines file
existence checks, security scans, and historical guardrails before emitting
`telemetry/events/testing-summary.json` via the telemetry aggregator.

## Workflow Overview

1. **Pytest telemetry** – execute the FastAPI suites with the
   `cmos/scripts/pytest_telemetry_plugin.py` plugin enabled
   (automatically loaded by `tests/conftest.py`). The plugin writes a structured
   artifact to `telemetry/events/.artifacts/pytest-latest.json` that captures
   test metadata, durations, and failures.
2. **Playwright telemetry** – run `npx playwright test` inside `frontend/`.
   The shared reporter defined in `cmos/scripts/playwright_telemetry_reporter.js`
   emits `telemetry/events/.artifacts/playwright-latest.json` with per-test
   results and browser context details.
3. **Integration runner** – run `node cmos/context/integration_test_runner.js`
   (optionally via `python cmos/scripts/aggregate_test_telemetry.py` which
   handles the Node invocation). The runner validates that documentation,
   security fixtures, and compatibility artifacts remain present.
4. **Aggregation** – execute
   `python cmos/scripts/aggregate_test_telemetry.py` to merge all artifacts into
   `telemetry/events/testing-summary.json` and mirror the file under
   `cmos/telemetry/events/` for mission evidence.

## Validation Checklist

- `pytest tests/...` completes without failures (plugin writes telemetry)
- `cd frontend && NEXT_PUBLIC_E2E_AUTH_TOKEN=test-playwright npx playwright test tests/e2e/mission-protocol.spec.ts --project=chromium`
- `python cmos/scripts/aggregate_test_telemetry.py` exits with `status:"passed"`
- `telemetry/events/testing-summary.json` contains all suites with fresh
  timestamps and is copied to `cmos/telemetry/events/testing-summary.json`

## Troubleshooting

- **Integration suite fails** – run `node cmos/context/integration_test_runner.js --output telemetry/events/.artifacts/integration-debug.json` to
  inspect missing files or guardrail regressions.
- **Telemetry missing** – ensure you did **not** override the default reporters
  (do not pass `--reporter` to `npx playwright test`) and verify the `.artifacts`
  directory is writable.
- **CI pipeline** – see `.github/workflows/test-telemetry.yml` for the automated
  execution order.

Keep this guide updated whenever new integration suites or telemetry sources
are added so automated guardrails stay in sync with Mission Protocol
expectations.
