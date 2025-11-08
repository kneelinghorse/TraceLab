# Mission Protocol Validation Framework

The Mission Protocol validation stack enforces research rigor with a single Pydantic-based source of truth that feeds every layer of the system—FastAPI request parsing, business-layer quality gates, and PostgreSQL safeguards. This document explains the new models, helper utilities, and migration so Mission Protocol data stays consistent across runtime environments.

## Model Overview

Mission Protocol data is represented by the classes in `app/models/mission_protocol.py`:

- **Nested models** capture domain objects (`ResearchStatement`, `KeyQuestion`, `Evidence`, `Synthesis`, `QualityCheckpoint`).
- **`MissionProtocolDraft`** accepts partially-filled missions used during authoring.
- **`MissionProtocolComplete`** inherits from the draft model but re-declares required fields and enforces quality gates via `@model_validator`. Completion requires:
  - At least one answered key question.
  - At least one evidence item.
  - `synthesis.key_insights` populated.
  - Required checkpoints (`research_statement`, `evidence_links`, `synthesis_quality`, `traceability`, `contradictions_resolved`) marked `pass`.

Developers can promote drafts using `MissionProtocolDraft.promote()` or the service helper `promote_to_complete`.

## Multi-Layer Validation

1. **API Layer** – `app/schemas/mission.py` now binds request bodies to `MissionProtocolDraft`, giving FastAPI automatic structural validation for every mission endpoint.
2. **Business Layer** – `MissionProtocolComplete` encapsulates promotion logic while `app/services/quality_gate_service.py` runs the blocking gates (research statement, evidence links, contradictions, synthesis quality, traceability) and logs telemetry. The helper in `app/services/mission_protocol_validation.py` exposes:
   - `parse_mission_yaml` – YAML → `MissionProtocolDraft`.
   - `validate_mission_payload(payload, state=...)` – dict validation for draft/complete states.
   - `promote_to_complete` – upgrade drafts before persisting.
3. **Database Layer** – The Alembic migration adds a `missions_mission_data_check` constraint generated from `MissionProtocolDraft.model_json_schema()` and `MissionProtocolComplete.model_json_schema()`. The helper `build_mission_data_check_constraint()` ensures the CHECK clause stays in sync with the models.

## Error Transformation

`app/services/validation_errors.py` converts `ValidationError` instances into structured API responses:

```python
try:
    payload = MissionProtocolComplete.model_validate(input_payload)
except ValidationError as exc:
    return JSONResponse(
        status_code=422,
        content=transform_validation_error(
            exc,
            summary="Mission Protocol payload invalid.",
            next_hint="Ensure evidence and checkpoints are populated before completion.",
        )
    )
```

Each detail entry includes `field`, `message`, `type`, and the original Pydantic context to help UI and telemetry layers surface actionable guidance.

## YAML Workflow

```
yaml_text  ──parse_mission_yaml──▶ MissionProtocolDraft
    │                                        │
    └──────────────validate_mission_payload──┤
                                             ▼
                                     promote_to_complete
                                             ▼
                                      MissionProtocolComplete
```

Use this flow when importing Mission Protocol YAML, validating API submissions, or promoting drafts to completed missions prior to persistence.

## Testing & Validation

- Unit tests: `pytest tests/test_mission_protocol_validation.py`
- Integration tests (YAML → DB round trip): `pytest tests/integration/test_mission_validation_flow.py`
- Database guardrail verified via Alembic migration `004_mission_protocol_validation.py`.

Running these suites ensures draft/complete transitions, YAML parsing, error shaping, and database constraints stay aligned whenever the Mission Protocol schema evolves.
