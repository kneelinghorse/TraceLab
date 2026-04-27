# DeepSearch Contract Compiler — Vendoring & Resync Ritual

Sprint-41 mission **T41.1** vendored DeepSearch's mission-contract compiler
into TraceLab so `preview_mission_contract` could compile locally instead
of round-tripping over HTTPS to a service that isn't deployed (DS runs
worker-only in production). This doc is the source of truth for the pinned
revision, what files are vendored, why, and how to resync when DS lands a
relevant compiler change.

## Pinned source

| Field | Value |
| --- | --- |
| Source repo | `~/portfolio/DeepSearch.alpha` |
| Branch | `contract-driven-pipeline` |
| Commit | `24e88100624e6221e5fa957508ab77c4b0f519f9` (2026-04-27, "S59.1 — Worker boundary fix (3 changes)") |
| Vendored at | TraceLab sprint-41, mission T41.1 |

## Files vendored

| Source path (DS) | Destination (TraceLab) | Edits made |
| --- | --- | --- |
| `deepsearch/mission/contract.py` | `app/services/contract_compiler/contract.py` | Module docstring updated to flag vendor + link this doc; `from deepsearch.agent.deliverable_schemas import ...` rewritten to `from .deliverable_schemas import ...`; `from deepsearch.mission.title_utils import ...` rewritten to `from .title_utils import ...`. No behavior changes. |
| `deepsearch/agent/deliverable_schemas.py` | `app/services/contract_compiler/deliverable_schemas.py` | Module docstring vendor banner only. |
| `deepsearch/mission/title_utils.py` | `app/services/contract_compiler/title_utils.py` | Module docstring vendor banner only. |

`app/services/contract_compiler/__init__.py` is a TraceLab-authored facade
(not vendored). It exposes the public API surface used by
`deepsearch_preview_client.py` so internal compiler details remain
swappable when DS reorganizes its own modules.

## Why vendor instead of HTTP-call

T40.4 (sprint-40) shipped a TL→DS HTTP proxy that POSTed signed payloads
to `<DEEPSEARCH_API_URL>/api/v1/missions/preview`. Discovered 2026-04-27
that **DeepSearch in production runs worker-only** — there is no HTTP
service to receive that POST. Every production preview call returned 502
via Cloudflare. DS confirmed Option A (vendor in TraceLab) over Option B
(deploy a separate DS preview API) on the message thread initiated by
`3cf143ee-8cb9-43ac-bc22-f0029fcdd3ae`.

Tradeoff accepted: TraceLab now tracks DS compiler changes via this
ritual. The cost of one resync per DS schema-change is lower than the
cost of running DS as a second service for one read-only endpoint.

## Resync ritual (when to do it)

Resync **whenever** any of these happens upstream in DeepSearch:

1. `MissionContract` (or any of its nested models — `ObjectiveContract`,
   `EvidenceSlot`, `AcceptanceCheck`, `DeliverableSchemaContract`,
   `ExecutionBudget`) gains/loses/renames a field.
2. `compile_contract_from_state` signature changes (new keyword args, new
   required state keys, removed `origin` parameter, etc.).
3. Worker SELECT in `deepsearch/worker/poller.py` learns to read a new
   mission column — that means the compiler now expects it in
   `mission_context`, and TraceLab's
   `build_mission_context_from_mission` should forward it.
4. DS publishes a contract-schema version bump
   (`CONTRACT_SCHEMA_VERSION`).
5. DS fixes a compilation bug we want to inherit (entity extraction,
   schema inference, threshold defaults).

If the change is purely internal to DS's own runtime (worker scheduling,
LLM integration, retrieval logic) — **don't resync**. The compiler is
the boundary; everything else is DS's business.

## Resync ritual (steps)

```bash
cd ~/portfolio/DeepSearch.alpha
git fetch origin
git log -p --since="<last_resync_date>" -- \
    deepsearch/mission/contract.py \
    deepsearch/agent/deliverable_schemas.py \
    deepsearch/mission/title_utils.py \
    deepsearch/api/routes/missions.py    # check the HTTP adapter for state-shape changes

# Read the diff. Decide: are any of the resync triggers above met?
# If yes:

NEW_COMMIT=$(git rev-parse HEAD)
cd ~/portfolio/TraceLab

cp ~/portfolio/DeepSearch.alpha/deepsearch/mission/contract.py \
   app/services/contract_compiler/contract.py
cp ~/portfolio/DeepSearch.alpha/deepsearch/agent/deliverable_schemas.py \
   app/services/contract_compiler/deliverable_schemas.py
cp ~/portfolio/DeepSearch.alpha/deepsearch/mission/title_utils.py \
   app/services/contract_compiler/title_utils.py

# Re-apply the two patches the vendor needs:
#   1. The vendor banner in each module docstring
#   2. In contract.py only:
#        from deepsearch.agent.deliverable_schemas import (...)  →  from .deliverable_schemas import (...)
#        from deepsearch.mission.title_utils import normalize_mission_title  →  from .title_utils import normalize_mission_title

# Run the validation checklist:
source .venv/bin/activate
pytest tests/test_mission_contract_preview.py -v
pytest tests/test_missions_api.py -v   # contract-preview is invoked via the route
python -c "from app.services.contract_compiler import compile_contract_from_state, MissionContract; print('OK')"

# If preview-client adapter needs updating (compile_contract_from_state
# signature change, MissionContract field set change), update
# app/services/deepsearch_preview_client.py::_build_preview_state and/or
# _shape_contract — these are TraceLab-authored, NOT vendored, so they
# stay through resyncs unless the boundary itself shifted.

# Update this doc:
#   - Pinned commit row in the table above
#   - Append a one-line entry to the Resync log section below
```

## Validation checklist (pass before committing a resync)

- [ ] `pytest tests/test_mission_contract_preview.py` — all green
- [ ] `pytest tests/test_missions_api.py` — all green (route contract still holds)
- [ ] `python -c "from app.services.contract_compiler import compile_contract_from_state, MissionContract"` — imports clean
- [ ] Live ping against canonical mission UUID `2a781109-6122-4576-b5c2-052e5450d22e` (OODS-FIGMA-HOST-01) — `named_entities` includes the 5 declared `required_entities` (AWS Lambda, Google Cloud Run, Vercel Functions, Fly.io, Railway)
- [ ] Pinned commit row in this doc updated
- [ ] Resync-log entry appended below
- [ ] Status_update sent to `cmos://derek/deepsearch` so DS knows TraceLab is on a fresh compiler revision

## Resync log

| Date | New commit | Reason | Author |
| --- | --- | --- | --- |
| 2026-04-27 | `24e8810` | Initial vendor (T41.1) — replaces broken HTTP proxy | sprint-41 build session |

## Known boundary fields TraceLab forwards

Documented here so a resync that adds new mission_context fields knows
what TraceLab already sends. The authoritative list lives in
`app/services/deepsearch_preview_client.py::build_mission_context_from_mission`
and `app/services/deepsearch_preview_client.py::_OPTIONAL_AUTHORING_FIELDS`.

Required keys: `mission_id`, `title`, `objective`, `success_criteria`,
`deliverables`.

Optional keys (forwarded only when the mission has them set): `background`,
`focus`, `references`, `required_entities`, `excluded_entities`,
`expected_output_schema`, `coverage_thresholds`, `validation_thresholds`,
`deliverable_format`, `max_loops`, `min_loops`, `constraints`,
`research_depth`. The `constraints` slot has a fallback to legacy
`context['constraints']` for pre-T40.1 missions.

If DS's compiler starts reading a column TraceLab doesn't yet forward,
add it to `_OPTIONAL_AUTHORING_FIELDS` during the resync (and mention
the change in the log entry above).

## Related

- T41.3 boundary contract document at `cmos/contracts/mission-authoring-contract.md`
  is the field-by-field MCP↔DB↔REST↔compiler map. This doc explains the
  *implementation*; T41.3 explains the *contract*. Keep them in sync —
  if you add a field here, also add it to the boundary doc's table.
- Existing JSON-schema vendoring under `schemas/` (e.g.
  `expected_output_schema.schema.json`) follows a similar pin-and-ritual
  pattern; see `schemas/VERSIONS.md` for the precedent.
