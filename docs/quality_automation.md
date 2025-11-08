# Quality Automation (Sprint 04)

Mission **B4.2 – Quality Gate Automation** introduces a deterministic automation layer that extends the Sprint 03 quality gates. The new services run whenever a mission is created or updated and record an audit trail in the `quality_checks` table plus telemetry under `telemetry/events/quality-automation.jsonl`.

## Components

| Component | Path | Purpose |
|-----------|------|---------|
| Bias detector | `app/services/bias_detection.py` | Flags leading questions and demographic imbalance using `discussion_guide` + `methodology_details`. |
| Traceability validator | `app/services/traceability_validator.py` | Ensures evidence maintains chunk links, valid `insight_sources`, and healthy relevance scores. |
| Methodology rigor checker | `app/services/methodology_rigor.py` | Verifies participant counts, required metadata, and documented validation steps via project documents. |
| Synthesis analyzer | `app/services/synthesis_analyzer.py` | Evaluates insight depth, recommendation coverage, and actionable next steps. |
| Orchestrator + background runner | `app/services/quality_checks.py` | Coordinates detectors, persists `QualityCheck` rows, emits telemetry, and runs asynchronously when invoked from the API. |

## Mission Workflow

1. `MissionProtocolService` now accepts a `QualityAutomationRunner`. The missions API constructs the service with `QualityAutomationRunner(async_enabled=True)` so each mission create/update schedules an async job.
2. The runner opens a fresh DB session, reloads the mission, and calls `QualityAutomationService.run_for_mission`.
3. Each detector returns a structured `QualityAutomationCheckResult`. The orchestrator persists the result as a new row in `quality_checks` and appends telemetry:

```json
{
  "ts": "2025-11-09T04:12:00Z",
  "entity_id": "a552d...",
  "check_type": "traceability",
  "status": "warning",
  "metrics": {"chunk_backed": 3, "broken_chunks": 1}
}
```

## API Surface

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST /api/v1/quality/automated/run` | Runs all automation checks immediately and returns the new `quality_checks` rows. |
| `GET /api/v1/quality/automated/history/{mission_id}` | Streams historical audit entries for the mission (latest first). |

Both responses use `QualityCheckRead` payloads so the UI can reuse existing schema serialization.

## Mission Data Additions

- `discussion_guide`: ordered moderator prompts used by the BiasDetector.
- `methodology_details`: optional structure (participant segments, validation steps, consent flag) used by the MethodologyRigorChecker.

These fields are optional, ensuring existing Mission Protocol payloads remain valid while providing richer context for automation-aware missions.

## Testing & Validation

- Unit tests cover each detector (`tests/test_bias_detection.py`, `tests/test_traceability_validator.py`, `tests/test_methodology_rigor.py`, `tests/test_synthesis_analyzer.py`).
- `tests/integration/test_quality_automation.py` verifies that mission updates trigger audit trail entries and exercises the new API endpoints.
- Before packaging, run `pytest tests/test_bias_detection.py tests/test_traceability_validator.py tests/test_methodology_rigor.py tests/test_synthesis_analyzer.py tests/integration/test_quality_automation.py`.
