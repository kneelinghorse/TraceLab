# Telemetry Automation

TraceLab's Sprint 08 telemetry initiative automates `telemetry/events/testing-summary.json`
so every pytest, Playwright, and integration run produces auditable evidence.

## Components

| Component | Path | Description |
|-----------|------|-------------|
| Pytest plugin | `cmos/scripts/pytest_telemetry_plugin.py` | Captures per-test results, durations, and metadata for any pytest invocation. Loaded via `tests/conftest.py`. |
| Playwright reporter | `cmos/scripts/playwright_telemetry_reporter.js` | Custom reporter executed from `frontend/playwright.config.ts` that writes telemetry for UI tests. |
| Integrations | `cmos/context/integration_test_runner.js` | Existing Node runner that now feeds the aggregator via `.artifacts/integration-runner.json`. |
| Aggregator | `cmos/scripts/aggregate_test_telemetry.py` | Merges pytest + Playwright + integration artifacts into `telemetry/events/testing-summary.json` and mirrors it under `cmos/telemetry/events/`. |
| CI workflow | `.github/workflows/test-telemetry.yml` | Executes pytest, Playwright, and aggregation on every push / PR. |

## Local Workflow

```bash
# 1. Run pytest (plugin auto-loads via conftest)
python -m pytest tests/test_health.py

# 2. Run Playwright from frontend/
cd frontend
NEXT_PUBLIC_E2E_AUTH_TOKEN=test-playwright npx playwright test tests/e2e/mission-protocol.spec.ts --project=chromium --workers=1

# 3. Aggregate telemetry (runs integration tests automatically)
cd ..
python cmos/scripts/aggregate_test_telemetry.py
```

The aggregator exits with a non-zero code if any suite failed. Use
`--allow-failures` when you only need the artifact during debugging.

## CI Expectations

`.github/workflows/test-telemetry.yml` mirrors the steps above:

1. Install Python deps and run pytest.
2. Install Node deps, browsers, and run Playwright.
3. Execute `python cmos/scripts/aggregate_test_telemetry.py`.
4. Upload `telemetry/events/testing-summary.json` as a workflow artifact.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_E2E_AUTH_TOKEN` | Enables Playwright auth flows in Mission Protocol UI tests. |
| `PYTEST_DISABLE_TELEMETRY` | Optional override to disable telemetry writes (should remain unset in CI). |
| `PLAYWRIGHT_TELEMETRY_OUTPUT` | Override output path for the Playwright reporter during bespoke runs. |

## File Layout

```
telemetry/
  events/
    .artifacts/
      pytest-latest.json
      playwright-latest.json
      integration-runner.json
    testing-summary.json          # aggregated artifact (auto-generated)
cmos/telemetry/events/testing-summary.json  # mirrored copy for Mission Protocol evidence
```

Keep the `.artifacts` directory out of commits if you only need transient data;
the aggregator regenerates everything when tests rerun.
