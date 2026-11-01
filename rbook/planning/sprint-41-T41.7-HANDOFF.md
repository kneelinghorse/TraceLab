# T41.7 Hand-off — Tool-Grouping Refactor

**Created:** 2026-04-27 by build session PS-2026-04-27-001 after shipping T41.1, T41.2, T41.3, T41.4, T41.5, T41.6 in one session.

**Why hand off:** T41.7 is the largest mission of sprint-41 — refactoring ~30 individual MCP tools into ~10-11 topical clusters touches the entire MCP surface. The cluster-boundary decision is the costly part (the mission spec explicitly flags this). A fresh session has clean context and can thoroughly survey both TL's current MCP surface and the cmos-mcp pattern before committing to boundaries. The previous session shipped 6 missions and is approaching the point where late-mission compaction risks introducing subtle dispatch bugs in a refactor that touches everything.

## Mission goal

Reduce TraceLab's MCP visible-tool count from ~30 to **~10-11 topical clusters**, matching the cmos-mcp pattern where each cluster dispatches by an `action` parameter:

```
# Today (TraceLab MCP):
create_mission(...)
update_mission(...)
get_mission(...)
list_missions(...)
submit_mission(...)
get_mission_status(...)
preview_mission_contract(...)

# After T41.7 (target — cmos-mcp shape):
tracelab_mission(action="create"|"update"|"get"|"list"|"submit"|"status"|"preview", ...)
```

## Why this matters

1. **Cognitive load for agents:** ~30 flat tools is a lot for an agent to discover and reason about. Clustering by domain reduces the mental surface to the same number of nouns the user thinks about (mission, project, collection, report, etc.).
2. **Discoverability:** Each cluster's tool description lists its actions, so agents see the surface in one place rather than across N tool entries.
3. **Sets up T41.9 npm publish (deferred to S42):** v1 of `@aquex/tracelab-mcp` should ship with the final shape. Refactoring after publish requires a major-version bump and migration guide; refactoring before publish is internal.
4. **User explicitly asked for this in sprint-41 planning** — matches the cmos-mcp pattern they prefer.

## Current state (as of session end)

**TS package** at `packages/tracelab-mcp/src/index.ts` exposes the TOOLS array starting around line 58. Visible tools include (counted from grep `grep -n "^    name:" packages/tracelab-mcp/src/index.ts`):
- `search_knowledge`
- `list_projects`, `create_project`, `update_project`, `get_project_stats`
- `list_collections`, `get_collection`, `export_collection`, `create_collection`, `add_to_collection`, `synthesize`
- `create_report`, `list_reports`, `get_report`, `export_report`
- `upload_document`, `get_document_content`
- `create_mission`, `list_missions`, `get_mission`, `update_mission`, `submit_mission`, `get_mission_status`, `preview_mission_contract`

(Run `grep -n "^    name:" packages/tracelab-mcp/src/index.ts` for the exact count and current order — the list above may be slightly out of date by the time you read this.)

**Python MCP server** at `app/mcp_server/tools/missions.py` exposes a smaller subset (only mission tools); Python MCP isn't reachable in production (see "Two surfaces" learning below). Refactor priority is the TS package; Python side can mirror or be left alone with a note.

## Recommended cluster boundaries (preliminary — sanity-check before committing)

Based on the current tool list:

| Cluster | Actions | Approx existing tools |
| --- | --- | --- |
| `tracelab_search` | `knowledge` | search_knowledge |
| `tracelab_project` | `list, create, update, stats` | list_projects, create_project, update_project, get_project_stats |
| `tracelab_collection` | `list, get, export, create, add` | list_collections, get_collection, export_collection, create_collection, add_to_collection |
| `tracelab_synthesize` | (single-action — could merge into collection) | synthesize |
| `tracelab_report` | `create, list, get, export` | create_report, list_reports, get_report, export_report |
| `tracelab_document` | `upload, get_content` | upload_document, get_document_content |
| `tracelab_mission` | `create, list, get, update, submit, status, preview` | create_mission, list_missions, get_mission, update_mission, submit_mission, get_mission_status, preview_mission_contract |

That's **7 clusters**, less than the ~10-11 target. A few options to consider:
- Promote `synthesize` to its own cluster if it'll grow (`tracelab_synthesize` with future actions).
- Split `tracelab_mission` into `tracelab_mission` (CRUD) + `tracelab_mission_execution` (submit, status, preview) since their callers/lifecycles differ.
- Or accept 7-9 clusters as the natural shape and don't pad to hit ~10-11.

**This decision is the costly part** — get it wrong and the next refactor is annoying. Spend time here before writing code.

## What's already in place that helps

- **T41.4 codified `slim`/`include_execution_metadata` flag** on get_mission. This translates cleanly into `action="get"` with a sibling param. No special handling needed.
- **T41.6 made project_id required at mission create.** Mirror this in the new `action="create"` schema (the JSON schema's `required` list).
- **T41.5 added project_id to mission update.** Mirror in `action="update"`.
- **T41.2 fix** for `_serialize_mission` (Python) and `handleGetMission`/`handleListMissions` (TS) — these emit the full T40.1 field set. Refactor must preserve this.
- **CLAUDE-equivalent rule** at `agents.md` — MCP Contract Guard section requires regression tests through the actual MCP client for any surface change. This refactor IS a surface change for every tool; budget time for tests.

## Critical context for the refactor

### Two MCP serialization surfaces (T41.4 learning)

TraceLab has TWO MCP serializers; only the TS one reaches users in production. Documented at `cmos/contracts/mission-authoring-contract.md` under "Two MCP serialization surfaces". When refactoring, focus the production-correctness effort on the TS package. The Python MCP server can be:
- (a) mirror-refactored alongside (cleaner but doubles the work)
- (b) left as-is with a note that it doesn't ship to users
- (c) deleted entirely if no one needs it

Decision is yours. If unsure, default to (b) — it's the lowest-blast-radius option and the Python MCP is already production-dark.

### Local MCP install is stale relative to the dist

Every TS-side change requires a Claude Code restart for the user to verify live. Prior sessions hit this with T41.4 and T41.5 — the deployed FastAPI was correct, but the local MCP binary was loaded at session start and didn't pick up rebuilds. Plan accordingly: the user will need to restart Claude Code to verify T41.7. Mention this in the deploy hand-off when you ship.

### Backwards-compat decision

The mission spec calls this out: hard-cut vs deprecation period. Two patterns to consider:

**Hard-cut** (matches cmos-mcp's recent refactor): old tool names removed. Agent code that calls `mcp__aquex__tracelab__create_mission(...)` breaks immediately. Migration guide explains the new shape. Forces all consumers to update simultaneously.

**Deprecation period:** keep old tool names alongside the new clustered ones. Each old tool delegates to the new dispatcher. Eventually delete old tools in a future release. More UX-friendly but doubles the visible surface during the transition.

Recommendation: **hard-cut**, since (a) v1 npm publish hasn't happened yet (so there's no externally-published API to break), (b) the TraceLab MCP is currently used internally, (c) the cmos-mcp precedent went hard-cut, (d) deprecation period adds cognitive load for agents (which actions are old, which are new?). Document the migration in a one-page note.

### Live MCP verification path

Once shipped:
1. User restarts Claude Code → reloads the new dist
2. Verify each new cluster works by calling at least one action per cluster against the canonical test mission `585f20f1-10ec-4808-9ac1-b066b59e7648` or a fresh create
3. Update `cmos/contracts/mission-authoring-contract.md` if the field map changes (it shouldn't, but the MCP-param column will reference the new tool name like `tracelab_mission(action="create")`)
4. DS status_update with the new shape and a one-line migration sketch

## Suggested execution order

1. **First 30 min:** Read the cmos-mcp source in `~/portfolio/cmos-mcp` to see exactly how they dispatched. Note their tool naming, action parameter shape, error handling pattern.
2. **Next 30 min:** Lock the cluster boundaries (the costly decision). Write them down as a comment block at the top of the new `index.ts` before refactoring.
3. **Refactor TS:** Replace the TOOLS array with the new clustered shape. Each tool's input schema has `action` as a required enum + the union of all action-specific params. Each tool's handler dispatches via a `switch (input.action)` to the existing per-action implementations (which are the current handler bodies — minimal logic change, mostly plumbing).
4. **Decide on Python MCP:** mirror, leave-as-is with note, or delete. Don't bikeshed — pick and move on.
5. **Tests:** at least one TS unit test per cluster covering 2 actions to prove dispatch works. Reuse the existing fetch-mock harness in `index.test.ts`. Plus a "every old tool still has a corresponding new action" parity test so nothing gets lost.
6. **Build clean:** `cd packages/tracelab-mcp && npm run build` must succeed without TS errors. The strict TS config will catch most dispatch bugs at compile time.
7. **Update agents.md** to mention the new tool surface.
8. **Update boundary contract doc** (`cmos/contracts/mission-authoring-contract.md`) — the MCP param column changes from `mission_id` (a top-level param) to `tracelab_mission.mission_id` (cluster param). Cosmetic but should be correct.
9. **Commit + ask user to deploy + restart Claude Code + verify.**
10. **DS status_update** with migration sketch.
11. **CMOS complete** with notes capturing the cluster-boundary decision and any surprises.

## What NOT to do

- **Don't refactor the api-client (`api-client.ts`).** It's the HTTP layer; its method signatures stay 1:1 with the FastAPI REST endpoints. Only the MCP-tool wrapper changes.
- **Don't change the FastAPI REST API.** This is purely an MCP-layer refactor. REST stays exactly as-is.
- **Don't bundle other improvements into T41.7.** It's already large. If you spot something worth fixing, file it as a follow-up mission.
- **Don't remove the `preview_mission_contract` tool's `{preview, full}` response wrapper** that wraps the slim summary + full payload — that's intentional UX from T40.4 and unrelated to T41.4's slim/full split for get_mission. Mirror it in `tracelab_mission(action="preview")` exactly.

## Definition of done

- [ ] TS MCP TOOLS array is ~7-11 topical clusters (down from ~30)
- [ ] Each cluster uses `action` param for dispatch
- [ ] Each cluster's tool description enumerates available actions and their action-specific params
- [ ] Backwards-compat decision documented (recommend hard-cut)
- [ ] All current functionality preserved (no behavior regressions)
- [ ] `npm run build` clean
- [ ] At least one test per cluster proving dispatch works + parity test
- [ ] `agents.md` updated to mention the new shape
- [ ] `cmos/contracts/mission-authoring-contract.md` updated
- [ ] Live verification post-deploy (requires Claude Code restart)
- [ ] DS status_update with migration sketch
- [ ] CMOS T41.7 marked Completed with cluster-boundary decision in notes

## Files to read first (priority order)

1. `~/portfolio/cmos-mcp/src/index.ts` (or wherever its dispatcher lives) — the pattern reference
2. `packages/tracelab-mcp/src/index.ts:58-810` — the current TOOLS array
3. `packages/tracelab-mcp/src/index.ts:2070-2090` — the current dispatch switch
4. `packages/tracelab-mcp/src/index.test.ts` — the test harness pattern
5. `cmos/contracts/mission-authoring-contract.md` — what NOT to break

Good luck.
