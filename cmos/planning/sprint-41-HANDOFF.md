# Sprint 41 — Hand-off for Fresh Session

**Created:** 2026-04-27 | **Theme:** DeepSearch Unblock + Agent UX Polish | **Status:** Planning complete, ready for execution

## Why this sprint exists

DeepSearch sent a question on 2026-04-27 06:30 UTC (CMOS message `3cf143ee-8cb9-43ac-bc22-f0029fcdd3ae`) reporting two issues:

1. **Production outage:** `preview_mission_contract` returns 502 (since at least 2026-04-27 06:21 UTC, multiple Cloudflare Ray IDs)
2. **Quality regression:** mission UUID `2a781109-6122-4576-b5c2-052e5450d22e` (OODS-FIGMA-HOST-01) had `required_entities` declared but matrix rendered 0/5 of them. Quality dropped 7.8 → 5.3.

We replied at 06:40 UTC ([cmos_message](cmos://derek/deepsearch) status: replied). DS confirmed **Option A** for the architecture fix (vendor compiler in TraceLab, not deploy a separate DS HTTP service).

**Two architectural realities discovered during triage** that the original Sprint 41 plan didn't account for:

1. T40.4's preview proxy depends on a DeepSearch HTTP API that isn't deployed in production (DS runs only as a worker). The 502 is structural, not a transient bug. → T41.1
2. The MCP `_serialize_mission` at [app/mcp_server/tools/missions.py:36-75](app/mcp_server/tools/missions.py#L36-L75) silently strips all 12 T40.1 mission-authoring fields. The REST API returns them, the DB has the columns, but MCP agents can't see them. → T41.2

## DS commitments (the clock is ticking)

From the reply we sent (2026-04-27 06:40 UTC):

- **T41.2 within 24h** (by 2026-04-28 06:40 UTC) — quick-win serializer fix
- **T41.1 + T41.3 by sprint close** — preview restoration + boundary contract document
- Send `status_update` to `cmos://derek/deepsearch` when each lands

DS is unblocked on the column-name front already (we sent them all 14 T40.1 column names so they can update their worker SELECT). They cannot diagnose the OODS-FIGMA-HOST-01 quality regression until preview is restored (T41.1).

## Missions (in execution order)

| # | ID | Name | ETA | Critical files |
|---|---|---|---|---|
| 1 | T41.2 | MCP _serialize_mission fix | 24h | [app/mcp_server/tools/missions.py:36-75](app/mcp_server/tools/missions.py#L36-L75), [app/api/v1/missions.py:50-111](app/api/v1/missions.py#L50-L111) (mirror this) |
| 2 | T41.1 | Vendor DS contract compiler (Option A) | sprint close | DS repo at `~/portfolio/DeepSearch.alpha`: `deepsearch/mission/contract.py` (lines 418, 861-902 cited by DS), `deepsearch/worker/converter.py`, `deepsearch/mission/output_schema.py`. TL files: [app/services/deepsearch_preview_client.py](app/services/deepsearch_preview_client.py), [app/api/v1/missions.py:664-725](app/api/v1/missions.py#L664-L725) |
| 3 | T41.4 | Graceful payload (slim/full split) | mid-sprint | Same `_serialize_mission` as T41.2 — sequence after T41.2 |
| 4 | T41.6 | Require project_id at create | mid-sprint | [app/schemas/mission.py:80](app/schemas/mission.py#L80), [app/api/v1/missions.py](app/api/v1/missions.py), [app/mcp_server/tools/missions.py:109-112](app/mcp_server/tools/missions.py#L109-L112), [packages/tracelab-mcp/src/index.ts](packages/tracelab-mcp/src/index.ts), frontend mission create form |
| 5 | T41.5 | Edit project_id on existing | mid-sprint | [app/schemas/mission.py:173](app/schemas/mission.py#L173), MCP update_mission tool |
| 6 | T41.3 | Boundary contract doc | sprint close | New file: `cmos/contracts/mission-authoring-contract.md`. Reference: T41.1 vendored compiler + all T40.1 fields |
| 7 | T41.7 | Tool-grouping refactor | last | Reference: `~/portfolio/cmos-mcp` — they have ~10-11 topical clusters with action params (e.g. `cmos_session(action="start"|"capture"|"complete")`). Refactor [packages/tracelab-mcp/src/index.ts](packages/tracelab-mcp/src/index.ts) flat tool list |

**Why this order:** T41.2 first (24h commitment); T41.1 starts in parallel (largest mission); T41.4 builds on T41.2's serializer; T41.5/T41.6 paired (both touch project_id semantics); T41.3 captures all field-mapping decisions; T41.7 LAST so it absorbs the new tool surface from T41.4-T41.6 cleanly without churn.

## Codification task (not a mission, single edit)

Add to [CLAUDE.md](CLAUDE.md) (or contributing docs):

> **MCP contract-guard test rule.** Any MCP surface change requires a regression test that hits the deployed verb via the MCP client, not just the server route directly. Origin: T40.0 PUT/PATCH 405 incident — tests with `client.put` against the server passed, but DS's paid smoke caught the verb mismatch in production. Pattern: `TestMissionVerbContract` in `tests/test_missions_api.py`.

Drop in alongside any of the missions, no scheduling required.

## Deferred to Sprint 42

- **T41.8** — Auth modernization (device-code-style, no API key in MCP snippet, mirror cmos-mcp's recent pattern)
- **T41.9** — `@aquex/tracelab-mcp` npm publish (requires T41.7 first so v1 ships with topical-cluster shape)
- **Domain cutover** to `tracelab.aquex.ai` — DS workflow currently runs off `api.namozine.com`; no value flipping during their workflow recovery

## Key context for picking up cold

### DS message thread

- Inbound: `3cf143ee-8cb9-43ac-bc22-f0029fcdd3ae` (DS → TL, 2026-04-27 06:30 UTC, status: replied)
- Their build hash: `8734243925336194b04e6acf6aa087397c884c80ac8824770e2f39b98c99e63c` (DeepSearch branch `contract-driven-pipeline` @ `6479b99`)
- Their canonical bug-repro mission: `2a781109-6122-4576-b5c2-052e5450d22e` (OODS-FIGMA-HOST-01, project `fbd3bd03-5ddc-49ee-8013-529163a99290`)

### What DS will see when each mission ships

- **After T41.2:** They can `get_mission` via MCP and see `required_entities` and the other 11 T40.1 fields. (They mostly use direct DB SELECT in their worker, so this is for *authoring* visibility, not their worker's runtime path.)
- **After T41.1:** They can call `preview_mission_contract` again and disambiguate the 5.3 quality regression. This is the unblock for their Sprint 59 paid-smoke retests.
- **After T41.3:** They have a single document to reference for the field contract instead of asking us via paid smoke.

### Architectural decisions that shaped this sprint

1. **Option A (vendor) over Option B (DS deploys preview API).** Captured in PS-2026-04-24-003. DS confirmed in reply. Tradeoff accepted: TL tracks DS compiler changes via `cmos/contracts/deepsearch-compiler-vendor.md` resync ritual.
2. **T41.7 last in sequence.** Refactoring tool surface before T41.4-T41.6 land would create rebase churn. Putting it last means v1 npm package (T41.9, deferred) ships with the final shape.
3. **Domain cutover stays deferred.** User confirmed DS envs work off current domain; no point flipping mid-recovery.

### Existing infra to leverage

- **HMAC sender** at [app/services/deepsearch_hmac_signer.py](app/services/deepsearch_hmac_signer.py) — already wired, uses `settings.effective_deepsearch_service_secret`. T41.1 will probably retire this (no more outbound HTTP), but keep the receiver side.
- **Pydantic schemas** at [app/schemas/mission.py:322-365](app/schemas/mission.py#L322-L365) — `MissionResponse` is correct; T41.2 just needs to mirror its field list into `_serialize_mission`.
- **Pre-commit dist guard** from T40.5 — packages/*/dist/ is gitignored, pre-commit blocks accidental dist commits. Run `npm run build` in `packages/tracelab-mcp/` after TS changes; the prepublishOnly hook handles publish-time regen.

### Things to verify before claiming done

For each mission's "Status_update sent to DeepSearch" success criterion:
- Use `cmos_message(action="send", targetAddress="cmos://derek/deepsearch", type="status_update", ...)`
- Reference message ID `3cf143ee-8cb9-43ac-bc22-f0029fcdd3ae` so DS can thread it
- Include the deployed Railway commit hash and a brief verification result

### Stale-decision notes (for context)

Sprint 40 review (PS-2026-04-24-002) and CMOS cleanup (also 2026-04-24) closed out 10 sprints worth of drift. The cleanup is done — `currentSprint` should pick up sprint-41 once it has Active missions. If onboarding shows a stuck pointer, check that no sprints with status=Planned/Active accidentally got recreated.

## How to start

1. `cmos_agent_onboard` — confirm sprint-41 is current
2. Pick T41.2 (smallest, 24h commitment)
3. Read [app/mcp_server/tools/missions.py:36-75](app/mcp_server/tools/missions.py#L36-L75), mirror [app/api/v1/missions.py:50-111](app/api/v1/missions.py#L50-L111)
4. Test against mission `2a781109-6122-4576-b5c2-052e5450d22e`
5. Ship to Railway, verify, send DS status_update referencing message `3cf143ee`
6. Move to T41.1

Good luck. The DS message thread is the source of truth for the unblock — anything written here that conflicts with their actual current state, defer to checking the inbox.
