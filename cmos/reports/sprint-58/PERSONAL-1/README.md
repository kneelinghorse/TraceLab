# PERSONAL-1 receipt: personal Spaces (2026-09-22)

Every human account now has a personal Space, and a new project lands in its creator's personal Space rather than Default Workspace. This is decision #530 (the Google Drive shape) with Derek's answers in #531. The placement rule was recorded as #532 before any code. It replaces GUEST-1's sole-Space rule (the GUEST-1 halves of #528 and #529; their BADGE-1 halves stand). PR #363 was squash-merged as `fec1893`. PR #364 followed it to fix the 390px picker width the baseline caught, merged as `fe4c112`. Session `PS-2026-09-22-011`.

## What changed

| change | where |
| --- | --- |
| `workspaces.personal_owner_id`: nullable, unique, FK `users.id` ON DELETE CASCADE. Set means personal; there is no kind column | `alembic/versions/052_personal_spaces.py`, `app/models/workspace.py` |
| Backfill: Derek-Private designated as Derek's personal Space. `<display_name>'s Space` plus a membership row for every other human; none for the service role. Member-owned projects leave Default with their documents, missions and reports. Child drift untouched. The downgrade moves every row back | migration 052 |
| `ensure_personal_space()`: idempotent, called only by `POST /auth/register` and `POST /admin/users`, same commit as the account | `app/services/ownership.py`, `app/api/v1/auth.py`, `app/api/v1/admin_users.py` |
| `default_workspace_id(db, caller)`: the caller's personal Space for every human caller of `POST /projects` (also the Librarian and the MCP create). Default for the service principal, for creates with no caller, and for a human with no row (logged). `sole_space_id()` removed | `app/services/ownership.py`, `app/core/authorization.py` |
| `GET /admin/spaces` returns `personal_owner_id`. Adding anyone but the owner to a personal Space is a 409. Assigning projects into one stays allowed | `app/api/v1/spaces.py`, `app/schemas/space.py` |
| Admin Spaces page: "Personal · <owner>" label, the viewer's own Space shown as "My Space", add-member disabled on a personal Space. Assignment select capped at half the row (#364) | `frontend/src/pages/admin/spaces.tsx`, `frontend/src/lib/api/admin.ts` |
| `rbac_verify` skips personal Spaces when it needs a Space for its temporary member grant | `scripts/rbac_verify.py` |

Untouched: the five child-resource create paths, `project_owner_workspace`, `authorize()` and `POLICY_VERSION`. The parity manifest gains and loses no operation; the changed operations keep their classifications, and `mcp_parity_audit.mjs` exits 0.

## Production

Deploys of `fec1893`: TraceLab `a299f323-d286-4f22-ba4a-72c7e4685a88` and frontend `439b4ff8-e844-41e1-ada2-e44cb51ba94f`, both SUCCESS. `/api/v1/health` reported healthy at `fec189319d5ffadc3017330b2a00e66e8c1b68d3`. Full outputs are in `production-checks.txt`.

**Migration outcome (read-only query in the deployed service):**

- `alembic_version` is `052_personal_spaces`.
- 8 personal Spaces, each with its owner as its only member:
  - Derek-Private, `081a5f9a`, designated for Derek (`007c8cb6`, owner).
  - Seven created: James Jamerson's, Birch's, Test's, kneelinghorse's (the legacy `@tracelab.local` admin account), Walkthrough Guest's (`1dbbe76f`), Syndy's, and d's.
- No human is left without one, and the service principal has none.
- `d2d6519c`, the only member-owned project in Default, is now in `1dbbe76f` with its 2 documents, 2 missions and 2 reports.
- Default Workspace still holds the owner's 37 projects (36 live).
- Child drift is unchanged at 176 documents, 89 missions and 46 reports (next-step #431).
- No project is without a Space.

**As the re-enabled guest `walk1-guest` (member, `148bcf80`)** — the JWT was minted inside the service and never printed:

```
POST /projects                  -> 201, workspace_id 1dbbe76f (Walkthrough Guest's Space; the guest is also in the shared "Walkthrough Guest")
GET  /projects/d2d6519c         -> 200, workspace_id 1dbbe76f
DELETE /projects/97515363       -> 200 (verification project soft-deleted)
```

**As Derek through his MCP credential (X-API-Key, the request `tracelab_project` create sends):**

```
POST /projects                  -> 201, workspace_id 081a5f9a (Derek-Private)
DELETE /projects/b446cb99       -> 200 (verification project soft-deleted)
GET  /admin/spaces              -> 200, 12 Spaces, 8 personal
POST /admin/spaces/1dbbe76f/members {Derek} -> 409 "A personal Space has one member; assign projects to it instead"
```

The 409 probe used a harmless target: Derek already reads everything, so a wrong 201 would have granted nothing.

**Guest disabled** again afterwards (`PATCH /admin/users/148bcf80/active` returned 200 with `is_active` false), which closes next-step #428.

**Baseline:** `/admin/spaces` in Light and Dark at 1440 and 390, read-only, after #364 deployed. 4 checks at `fe4c112` (TraceLab `f93b58d7-a969-409e-9f8b-bebefde977eb`, frontend `be367f76-7563-4a5f-a8c8-91c07fad328f`, both SUCCESS): status 200, no overflow, 0 axe violations, 0 page errors. One earlier attempt stopped after three clean shots with the script's credential-safe "could not finish" on a loaded machine; the complete re-run is the one archived. See `summary.json`, `results.json` and the four PNGs here. The first run at `fec1893` had passed its checks too (4 of 4, no overflow), but the 390px shot showed project names squeezed to a few characters a line beside the longer option labels. The Sprint 52 baseline shows them whole, and #364 fixed it.

## Gates

| gate | result |
| --- | --- |
| ruff 0.8.0 on every changed `.py`; Secret Scan on tracked files | clean |
| CI's backend-suite invocation, locally | 2808 passed, 3 skipped, 12 deselected (the quarantine) |
| migration tests on Postgres 15 (all 17 files) | CI backend-integration green; 052's two tests pass locally |
| tsc, eslint (max-warnings 0), OODS token gate; vitest | clean; 253/253 |
| red checks | the new placement, account, admin and harness tests fail on the old code; the vitest cases fail on the old page |
| PR #363 | ten of ten checks; main-push runs for `fec1893` all eight green (Backend Tests `35792838305`, Backend Integration `35792838351`, Backend Lint `35792838416`, Frontend Checks `35792838321`, Frontend Production Build `35792838317`, MCP Package `35792838327`, Secret Scan `35792838319`, Post-Deploy Check `35792838633`) |
| PR #364 | ten of ten checks; backend-suite took 33 minutes against the usual 11, which is the known spread (next-step #397), not the change. On main, `fe4c112`'s runs were green or still running when this receipt was written |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | migration 052: one nullable, unique column, FK users CASCADE, no kind column; up/down test in the style of 033 | met (`tests/integration/test_migration_052_personal_spaces.py`) |
| 2 | backfill: a Space per human (not service), Derek-Private designated, member projects and their children leave Default (exactly `d2d6519c` in production), drift untouched | met, verified in production |
| 3 | both account routes call one idempotent helper; tests for both routes and idempotency; no lazy creation | met (`tests/test_personal_spaces.py`, including a test that no other caller exists) |
| 4 | placement for every human caller, Default for service and no caller, `sole_space_id` removed, the five call sites untouched; tests for member, admin, owner, service and a missing row | met (`TestProjectLandsInPersonalSpace`; viewer covered too) |
| 5 | admin label and "My Space", 409 on adding members, assignment allowed; frontend test for the label and the disabled control | met (four vitest cases; production baseline) |
| 6 | parity manifest and audit exit 0; the MCP create inherits the rule, with a test | met (no operation added or removed; `TestMcpCreateInheritsPlacement`; production create via the MCP credential) |
| 7 | production: guest lands in their personal Space, Derek lands in Derek-Private, `d2d6519c` migrated, guest disabled, receipt here | met |
| 8 | decision in Derek's words before code, superseding the GUEST-1 half of #528; roadmap carries the outcome | met (#532; roadmap Sprint 58 section and change log) |

## Worth knowing

- Two accounts are named "kneelinghorse": Derek's own (owner, deniedart.com) and the legacy `@tracelab.local` admin. So the admin list shows "My Space" and "kneelinghorse's Space" side by side. That is the existing data, not a defect of this change.
- Removing a personal Space's owner from its roster is still possible, as before. Adding the owner back is allowed; anyone else gets the 409.
- A user who changes role from service to human has no personal Space, and gets Default with a logged warning until one is created.
