# Mission Protocol Tutorial

This tutorial extends the architectural guardrails captured in `foundational-docs/tech_arch_template.md` and demonstrates how to capture, validate, and promote Mission Protocol payloads end-to-end.

## 1. Draft Creation
1. Start from the backlog export (`./cmos/cli.py db export backlog --output cmos/missions/backlog.yaml`).
2. Draft missions in YAML using the `MissionProtocolDraft` schema:
   ```bash
   ./cmos/cli.py missions add B4.4 --sprint sprint-04 --name "Testing & Documentation"
   ./cmos/cli.py missions update B4.4 --metadata '{"description": "Coverage + docs"}'
   ```
3. Use `app/services/mission_protocol_validation.parse_mission_yaml` to lint YAML before import.

## 2. Validation Workflow
1. Promote drafts to the `complete` state via the service helper:
   ```python
   from app.services.mission_protocol_validation import promote_to_complete
   payload = promote_to_complete(draft_payload)
   ```
2. Persist missions through the API:
   ```bash
   http POST :8000/api/v1/missions/ mission_id=B4.4 title="Testing & Documentation" ...
   ```
3. Run `pytest tests/test_mission_protocol_advanced.py` to exercise SQLite + Postgres constraint generation logic.

## 3. Quality Gates & Automation
1. Trigger automated gates exposed in `app/api/v1/quality.py`:
   ```bash
   http POST :8000/api/v1/quality/automated mission_id==B4.4 gate=="traceability"
   ```
2. Inspect the resulting telemetry under `cmos/telemetry/events/mission-protocol-*.jsonl` and ensure the gate verdicts align with `REQUIRED_COMPLETION_GATES` in `app/models/mission_protocol.py`.

## 4. Documentation & Evidence
1. Store research artifacts under `artifacts/` and index them via `app/services/evidence_linking.py`.
2. Reference evidence from Mission Protocol payloads using the `evidence_id` + `chunk_id` pair.
3. Include user-facing docs generated from this tutorial in `docs/README.md` so new contributors can find the Mission Protocol workflow quickly.

## 5. Completion Checklist
- Draft validated through `pytest tests/test_mission_protocol_validation.py` and API contract tests.
- Quality gates show `pass` for research statement, evidence links, synthesis, traceability, and contradictions.
- Mission marked `complete` using `cmos/context/mission_runtime.complete` with summary + next hint recorded in SQLite.
