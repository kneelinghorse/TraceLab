# CMOS Integration Testing Guide

This runbook describes how to execute and interpret the CMOS integration test runner so Sprint guardrails stay aligned with the FastAPI application. Use it alongside the orchestration references in `cmos/docs/AI-coding-assistant-workflows.md`, the security policies in `cmos/docs/cmos_Playbook.md`, and the operational tips in `agents.md` + `cmos/agents.md`.

## Pre-Flight Checklist

1. **Workspace health**
   - `python cmos/scripts/validate_parity.py --check`
   - `./cmos/cli.py validate health` and `./cmos/cli.py db show current`
2. **Dependencies**
   - Python 3.11 virtualenv with `pip install -r requirements.txt`
   - Node 18+ for the runner modules under `cmos/context`
3. **Mission context**
   - Load `agents.md` then `cmos/agents.md`
   - Confirm the active mission in SQLite via `python - <<'PY' ... mission_runtime.next_mission()` if unsure

## Running the Integration Test Runner

```bash
node cmos/context/integration_test_runner.js \
  --output telemetry/events/testing-summary.json
```

- The manifest at `cmos/tests/integration/test_manifest.json` enumerates suites for guardrails, performance, and structured prompting.
- Override `--manifest` when testing an experimental scenario file.
- The CLI emits a red/green summary to stdout and writes the full JSON report to `cmos/telemetry/events/testing-summary.json`.

## Guardrails Covered

| Suite | Focus | Key Assets |
| --- | --- | --- |
| core-integration | Presence of `agents.md`, `cmos/docs/integration-testing-guide.md`, CLI/runtime assets | Docs + runtime tree |
| security-guardrails | OWASP-style scans via `ContextSecurityValidator` | `tests/security/*.yaml` |
| quality-assurance | Static signal checks from `CodeQualityAssurance` | `tests/quality/*.js` |
| performance-benchmarks | Token + latency deltas from `tests/performance/benchmarks.json` | Telemetry fixtures |
| structured-prompting | Ensures agents + contexts mention security + orchestration cues | `cmos/agents.md`, `cmos/context/MASTER_CONTEXT.json` |

### Boundary Enforcement (CMOS ↔ app)

CMOS scripts must remain application-agnostic. Run the following before promoting a mission to confirm no `app.services` imports slipped into `cmos/`:

```bash
rg -n "app\\.services" cmos --type-add 'code:*.py,*.js,*.ts' --type code
```

No matches should be reported. If one appears:

1. Move the shared logic into `app/services/` and expose it through an API or telemetry artifact.
2. Refactor the CMOS helper to consume exported JSON, CLI commands, or telemetry snapshots instead of importing from `app`.
3. Document the change in mission notes and rerun the integration test runner.

## Failure Triage

1. Inspect `status` + `testsFailed` in the JSON report.
2. Drill into the failing suite entry and note `target`, `error`, and `missing` fields.
3. For documentation failures, update the referenced file then rerun the runner.
4. For guardrail/security failures, adjust the offending context fixture and re-execute the suite.

## Reporting & Telemetry

- Append a mission event via `context.mission_runtime` (`start`, `complete`, `block`) so SQLite + `cmos/SESSIONS.jsonl` stay in sync.
- Store the resulting `telemetry/events/testing-summary.json` artifact with the mission evidence.
- Update `MASTER_CONTEXT` + `PROJECT_CONTEXT` through `context.db_client.SQLiteClient` to capture new guardrails, then mirror to files via the migration scripts if needed.

Following this guide keeps integration guardrails reproducible and ensures CMOS never leaks FastAPI implementation details.
