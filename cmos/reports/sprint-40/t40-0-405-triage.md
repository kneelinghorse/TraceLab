# T40.0 — Production 405 Triage Report

**Sprint:** 40
**Mission:** T40.0 — Triage and fix production 405 on `update_mission` and `submit_mission`
**Date:** 2026-04-23
**Status:** Code fix landed on branch `sprint-39`; production deploy pending user authorization

## Summary

Two independent root causes, not one:

| Endpoint | Symptom | Root cause | Scope of failure |
|---|---|---|---|
| `PATCH /api/v1/missions/{id}` (MCP `update_mission`) | 405 Method Not Allowed | FastAPI route registered as `@router.put`, MCP client sends `PATCH` | **Every environment** (local, staging, prod) — code bug |
| `POST /api/v1/missions/{id}/submit` (MCP `submit_mission`) | 405 Method Not Allowed | Route does not exist on `main` branch; deployed code is ~267 commits stale | **Production only** — deploy lag |

The DeepSearch paid smoke on `ACC-BIB-EVID-01` hit both at once, so the failures looked like a single problem.

## Cause 1 — `update_mission` verb mismatch

### Evidence

- MCP client: [`packages/tracelab-mcp/src/api-client.ts:711`](../../../packages/tracelab-mcp/src/api-client.ts#L711)
  ```ts
  return this.request<Mission>('PATCH', `/api/v1/missions/${missionId}`, data);
  ```
- Server route (pre-fix): `app/api/v1/missions.py:377`
  ```python
  @router.put("/{mission_id}", response_model=MissionResponse)
  def update_mission(...)
  ```
- Zero `@router.patch(...)` registrations existed for `/missions/{id}` anywhere in `app/`.

### Why it was invisible

The API-level tests in `tests/test_missions_api.py::TestMissionUpdate` all used `client.put(...)`, matching the (wrong) server side. The MCP side had no end-to-end test hitting the real server, so the two halves of the contract were never exercised together. Agent-authored updates had been routing through the MCP, which kept silently 405-ing until DeepSearch's paid smoke surfaced it.

### Fix

- `app/api/v1/missions.py:377` — `@router.put` → `@router.patch` (partial-update semantics match PATCH)
- `app/api/v1/missions.py:123,133` and `app/mcp_server/tools/missions.py:421,437` — suggestion strings updated from `"Use PUT /api/v1/missions/..."` to `"Use PATCH ..."`
- `tests/test_missions_api.py` — 11 existing `client.put(...)` calls flipped to `client.patch(...)`; class docstring updated
- New class `TestMissionVerbContract` in `tests/test_missions_api.py` with three guards:
  1. `test_patch_update_mission_returns_200` — locks PATCH as the canonical verb
  2. `test_put_update_mission_returns_405` — regression: ensures no one silently re-adds a PUT registration
  3. `test_post_submit_mission_route_exists` — regression: asserts the submit route is present (catches the cause-2 failure in any deployed environment)

**Zero production callers used PUT.** Search covered `packages/tracelab-mcp/src/`, `frontend/src/`, `app/`, `tests/`. The only PUT references were the route definition, test fixtures, and two suggestion strings — all updated.

## Cause 2 — `main` is 267 commits behind `sprint-39`

### Evidence

- `git log main..sprint-39 | wc -l` → **267 commits**
- `main` HEAD: `1138522` dated **2025-12-05** (Sprint 12 era)
- `sprint-39` HEAD: `69c0953` dated 2026-04-16 (Sprint 39)
- `git show main:app/api/v1/missions.py` lists only `POST /`, `PUT /{id}`, `DELETE /{id}`, `POST /import`. No `/submit` route, no `/create-and-submit`, no `/promote-report`.

### Why

Every sprint from 13 through 39 landed on a sprint-branch. PRs merged into later sprint branches rather than back to `main`. `main` drifted into a pre-Sprint-13 snapshot while Railway kept deploying from it.

### Fix

The code for `POST /{id}/submit` already exists on `sprint-39` at `app/api/v1/missions.py:569`. **There is no code to write for cause 2** — the fix is a branch-sync operation:

- Option A (simplest): merge `sprint-39` → `main`, let Railway redeploy
- Option B (cleaner): open a Sprint-40-prep PR from `sprint-39` → `main`, review the 267-commit diff in sections, then merge

Either option is a shared-state mutation (production deploy) that requires explicit user authorization. This report does not execute it.

## Regression prevention

Beyond the three tests above, the stale-main class of failure deserves a process guard. Candidate mitigations for a follow-up discussion (not in T40.0 scope):

- Branch-protection rule on `main` that fails CI if `main` diverges more than N commits from the most recent sprint branch
- Weekly automated PR opening sprint-branch → main
- Move Railway deploy target to the active sprint branch (would require rewrapping the release process)

## Verification

```
$ pytest tests/test_missions_api.py tests/test_mission_model.py tests/test_mission_validation.py -q
141 passed, 27 warnings in 9.11s
```

All 11 converted tests and 3 new contract-guard tests pass. No test-suite regressions introduced.

## Outstanding (for user decision)

1. **Production deploy authorization** — required to satisfy success criteria "PATCH returns 200 in production" and "POST /submit returns 200 in production."
2. **Branch-sync strategy** — merge `sprint-39` → `main` directly, or route through a review PR first.
3. **MCP dist regeneration** — `packages/tracelab-mcp/dist/*` has uncommitted changes from Sprint 39. T40.5 plans to retire dist/ from git entirely; recommend either committing the current dist or waiting for T40.5 to land first.
4. **DeepSearch notification** — status update to confirm production unblock, blocked on (1).

## Files touched

- `app/api/v1/missions.py`
- `app/mcp_server/tools/missions.py`
- `tests/test_missions_api.py`
- `cmos/reports/sprint-40/t40-0-405-triage.md` (this file)
