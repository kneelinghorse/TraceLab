# Mission Protocol API

Mission Protocol endpoints expose CRUD + YAML workflows powered by the validation stack described in `docs/mission_protocol_validation.md`. Every request flows through the same Pydantic models to keep API, business logic, and database constraints in lockstep.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/missions/` | List missions (filter via `?project_id=`). |
| `POST` | `/api/v1/missions/` | Create a mission from Mission Protocol JSON. |
| `GET` | `/api/v1/missions/{mission_id}` | Retrieve a mission with derived progress metadata. |
| `PUT` | `/api/v1/missions/{mission_id}` | Update mission payload; progress + status recalc automatically. |
| `DELETE` | `/api/v1/missions/{mission_id}` | Remove a mission. |
| `POST` | `/api/v1/missions/import` | Import Mission Protocol YAML (optional promotion to complete state). |
| `GET` | `/api/v1/missions/{mission_id}/export` | Export Mission Protocol YAML derived from `mission_data`. |
| `GET` | `/api/v1/missions/{mission_id}/quality` | Run quality gates and return pass/fail state for each validator. |

## Request/Response Schemas

- Mission CRUD uses `app/schemas/mission.py`:
  - `MissionCreate` expects `project_id` plus `mission_data: MissionProtocolDraft`.
  - `MissionRead` returns derived `completion_percentage`, `quality_gates`, and canonical `mission_data`.
- YAML helpers use `app/schemas/mission_protocol.py` for import/export envelopes.

Mission payload structure is defined by `app/models/mission_protocol.py`. Validation happens twice: first via FastAPI request binding, then through `MissionProtocolService` before hitting the `missions` table `CHECK` constraint created in migration `004_mission_protocol_validation.py`.

## Progress + Quality Tracking

`app/services/mission_progress.py` calculates completion checkpoints:

```python
from app.services.mission_progress import evaluate_progress, derive_status

snapshot = evaluate_progress(mission_payload)
status = derive_status(snapshot, requested_status)
```

Each response includes:

- `completion_percentage` – ratio of satisfied structural requirements (research statement, answered question, evidence, checkpoints, etc.).
- `quality_gates` – map of every gate (`research_statement`, `evidence_links`, `synthesis_quality`, `traceability`, `contradictions_resolved`, plus optional gates detected in payload) with current status + validation metadata derived from the automated validators.
- `status` – normalized lifecycle stage (`draft`, `in_progress`, `review`, `complete`). Requests to advance to `review`/`complete` while any gate fails now return a 400 error; implicit promotions are downgraded to `review` until the gates pass.

## YAML Workflow

Import/export uses `app/services/yaml_handler.py`:

```python
from app.services.yaml_handler import load_mission_yaml, dump_mission_yaml

draft = load_mission_yaml(yaml_text)
yaml_out = dump_mission_yaml(draft)
```

The API import route accepts raw YAML, parses it with `MissionProtocolDraft`, optionally promotes to `MissionProtocolComplete`, and persists it via the shared MissionProtocolService. Export returns a canonical YAML rendering of `mission_data` so researchers can round‑trip between files and the database.

## Evidence Linking

When evidence entries include `insight_id` and `chunk_id`, the service routes them through `app/services/evidence_linking.py` to synchronise the `insight_sources` junction table. Links update automatically on create/update without requiring a separate endpoint.

## Testing

Run the targeted suites before shipping Mission Protocol changes:

```bash
pytest tests/test_mission_protocol_validation.py \
       tests/test_mission_protocol_service.py \
       tests/integration/test_mission_validation_flow.py \
       tests/integration/test_mission_api.py
```

These tests cover Pydantic validation, database constraints, MissionProtocolService logic, and REST endpoints.
