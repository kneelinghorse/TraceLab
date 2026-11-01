# GUEST-1 and BADGE-1 receipt (2026-09-22)

Two WALK-1 findings fixed as Derek ruled (decision #528; design #529). PR #360,
squash-merged as `34b6c30`, deployed SUCCESS on TraceLab and frontend,
`/api/v1/health` healthy at `34b6c30`. Session `PS-2026-09-22-007`.

## GUEST-1: a guest's new project lands in the guest's Space

Derek: "ok for now" to "a member of exactly one Space gets new projects in that
Space, your own account unchanged."

| change | where |
| --- | --- |
| `sole_space_id(user, db)`: the one Space a non-privileged member belongs to, else None | `app/core/authorization.py` |
| `default_workspace_id(db, caller=None)` returns that Space when a caller is passed and has one | `app/services/ownership.py` |
| `ProjectQueryService.create_project(..., caller=)`; only `POST /projects` passes the caller (also the Librarian's inline create) | `app/services/project_query_service.py`, `app/api/v1/projects.py` |

Untouched: owner and admin callers, members of zero or several Spaces, and the
five other `default_workspace_id` call sites (documents, collections, reports,
DeepSearch, synthesize). Existing projects are not migrated; the guest's WALK-1
project `d2d6519c` stays in Default Workspace, visible to the guest by ownership.

Tests: `tests/test_project_management_api.py::TestProjectSpaceForMembers`
(member of one Space creates there; members of none or several keep Default;
owner and admin with one Space keep Default).

> **Corrected at the Sprint 58 close (2026-09-23, session `PS-2026-09-22-012`,
> receipt re-verification per decision #509).** PERSONAL-1 replaced this
> placement in PR #363 (`fec1893`, decision #532). `sole_space_id()` is gone
> from `app/core/authorization.py`. `default_workspace_id(db, caller)` now
> returns the caller's personal Space for every human caller, and
> `TestProjectSpaceForMembers` became
> `TestProjectLandsInPersonalSpace`. PERSONAL-2 (PR #366, `2bcc766`, decision
> #533) then let a caller name one of their own Spaces. The migration moved
> `d2d6519c` to the guest's personal Space. The table, the test line and the
> first production line above describe the code at `34b6c30`. Decisions #528
> and #529 are superseded by #534, which restates their BADGE-1 halves, and
> the BADGE-1 half of this receipt still holds.

**Production, as the re-enabled guest `walk1-guest@tracelab.local`:**

```
POST /projects as guest  -> workspace_id e0d2ba43-d4ca-4d4e-b59a-0c40d2d6f1ed  (Walkthrough Guest)
POST /projects as owner  -> workspace_id 00000000-0000-0000-0000-000000000001  (Default)
```

Both verification projects (`63a5b48e`, `c3fc78ae`) were soft-deleted afterwards.

## BADGE-1: opening a group of evidence marks the whole group seen

Derek: "yes, marked on open of the entire group of evidence."

What the code showed before the fix: evidence activity was already one item per
group (project, mission, session, origin), so the badge read "Evidence, 1 new"
for the 296-entry run; the defect was that nothing on the Evidence page or the
mission page ever marked a group viewed, only a click on the Home stream did.

| change | where |
| --- | --- |
| `PUT /activity/viewed/evidence` `{project_id, mission_id?, session_key?}`: marks every readable group in scope at its latest entry, through the same grouping query the stream and summary use | `app/api/v1/activity.py`, `app/services/activity.py`, `app/adapters/repositories/sqlalchemy_activity_repo.py`, `app/ports/activity.py`, `app/schemas/activity.py` |
| Evidence page marks the opened scope once (a ref stops re-marking on every page fetch); mission page marks its run when the Evidence tab opens | `frontend/src/pages/evidence.tsx`, `frontend/src/pages/missions/[id].tsx`, `lib/hooks/useActivitySummary.ts`, `lib/api/activity.ts` |
| Parity manifest row (rest-only-by-design, like `markViewed`); RBAC harness probes the route | `cmos/contracts/mcp-parity-manifest.json`, `scripts/rbac_verify.py`, `tests/test_rbac_verify_harness.py` |

Not done, and why: the report page does not mark evidence, because a report
carries no mission id and so cannot name its run's group.

Tests: `tests/test_activity_api.py` (a 300-entry group cleared by one call and
one `user_item_views` row; a member cannot mark a group they cannot read),
`evidence.test.tsx` (marked once per opened scope, not per page),
`missions.test.tsx` (marked when the Evidence tab opens, not before).

**Production, as the guest, on the WALK-1 run `76c97203`:**

```
GET /activity/summary            -> {'mission': 0, 'report': 0, 'evidence': 1}
PUT /activity/viewed/evidence    -> {"viewed": 1, "new_total": 0}
GET /activity/summary            -> {'mission': 0, 'report': 0, 'evidence': 0}
```

## Gates

ruff clean on every changed file; CI's pytest invocation locally 2795 passed
with only the 12 quarantined failures; tsc, eslint, OODS token gate clean;
vitest 249/249; `mcp_parity_audit.mjs` exit 0; PR #360 ten of ten checks
after two harness-list additions (learning #240). Secret scan clean.

## Criteria

| mission | # | result |
| --- | --- | --- |
| GUEST-1 | 1 rule recorded in Derek's words before code | met, #528 |
| GUEST-1 | 2 tests for one-Space member and for the owner path | met |
| GUEST-1 | 3 both create paths follow the rule; background creates untouched | met (one endpoint serves both) |
| GUEST-1 | 4 verified in production with the guest; `d2d6519c` still visible | met |
| GUEST-1 | 5 no migration of existing projects | met |
| BADGE-1 | 1 rule recorded in Derek's words | met, #528 |
| BADGE-1 | 2 one open clears a 300-entry run; test proves no 300 renders | met |
| BADGE-1 | 3 Missions and Reports badges unchanged; API shapes unchanged | met (additive route only) |
| BADGE-1 | 4 verified in production on `76c97203` as the guest | met |
