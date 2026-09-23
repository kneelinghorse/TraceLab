# PERSONAL-2 receipt: creating inside a shared Space (2026-09-23)

A member of a shared Space can now create a project in it. Before this, every project landed in the creator's personal Space, so colleagues in the shared Space never saw it. Derek's scope: "fine, we're doing both either way, it just means two session vs 1" (decision #531). The design was recorded before code as decision #533. PR #366 was squash-merged as `2bcc766`. Session `PS-2026-09-22-012`, the second build session after PERSONAL-1 shipped.

## What changed

| change | where |
| --- | --- |
| `GET /api/v1/spaces`: the Spaces the caller may create in. Members and viewers get the Spaces they belong to; owner and admin get every Space. The caller's own personal Space comes first, then shared Spaces, then (owner and admin only) other people's personal Spaces. Returns `SpaceResponse`, so `personal_owner_id` marks a personal Space. Service principals are refused | `app/api/v1/spaces.py` (`member_router`), `app/main.py` |
| `POST /projects` takes an optional `workspace_id`, checked by `authorize_space_placement()`. Owner and admin may name any existing Space (404 when missing); everyone else must be a member (403 whether or not the Space exists). Not gated by `rbac_enabled`. Absent still means the personal Space; `owner_id` is still only the caller | `app/core/authorization.py`, `app/api/v1/projects.py`, `app/schemas/project.py`, `app/services/project_query_service.py` |
| One `SpacePicker` for the project create form and the Librarian's inline create. It renders only for a caller with more than one Space, defaults to "My Space" (which sends no `workspace_id`), and says that everyone in a shared Space can see its projects | `frontend/src/components/SpacePicker.tsx`, `pages/projects/new.tsx`, `pages/librarian.tsx`, `lib/api/spaces.ts`, `lib/api/projects.ts` |
| MCP `tracelab_project.create` takes the same optional `workspace_id` (advertised schema and Zod schema). `list` and `create` output now carry `workspace_id` (`get` already did). The Python MCP server has no project tool, so the TS package is the only MCP surface | `packages/tracelab-mcp/src/index.ts`, `api-client.ts`, `README.md`, `CHANGELOG.md` |
| Parity: new row `spacesApi.list`, rest-only-by-design (an agent names a Space it reads from `tracelab_project`). OODS contract: `ProjectCreate.workspace_id` mapped | `cmos/contracts/mcp-parity-manifest.json`, `cmos/contracts/oods-object-model.json` |

The project hub is unchanged (Derek: "thats fine for now"). T44.4's rule that a body `workspace_id` is ignored became: it is validated. Its test now expects 404 and no project. The MCP package is not published by this mission; the change sits in `[Unreleased]` for the next release.

## Production

Deploys of `2bcc766`: TraceLab `01f88c99-ec57-4969-b945-22f29ac7a809` and frontend `32098a1d-8246-45b7-97d6-1e97e40436b2`, both SUCCESS. `/api/v1/health` reported healthy at `2bcc766d1212db302f1d15da42cd9c4c44df47b9`. Full outputs are in `production-checks.txt`.

The shape was chosen to touch as little as possible. The shared Space is the existing Walkthrough Guest Space (`e0d2ba43`), whose only member is the guest. The guest (`148bcf80`) was re-enabled for the check, and the Test member account (`cb8b2d57`) was added as a second member for its duration.

- **Through the real picker, as the guest, in a browser.** `/projects/new` showed the picker with exactly "My Space" and "Walkthrough Guest", defaulting to My Space (`guest-new-project-picker.png`). Choosing Walkthrough Guest and creating "PERSONAL-2 verification (picker)" opened project `2cd73b8d` with no page errors (`guest-created-project.png`).
- **API checks:**

```
guest  GET /spaces                -> [Walkthrough Guest's Space (personal), Walkthrough Guest (shared)]
guest  GET /projects/2cd73b8d     -> workspace_id e0d2ba43 (Walkthrough Guest)
Test   GET /spaces                -> [Test's Space (personal), Walkthrough Guest (shared)]
Test   GET /projects              -> lists 2cd73b8d
guest  POST /projects {workspace_id: Test's personal Space} -> 403 "You are not a member of this Space."
```

- **Cleanup:** `2cd73b8d` was soft-deleted, Test was removed from Walkthrough Guest (the roster is the guest alone again), and the guest was disabled, which rejects every token it held. The scratch file holding the guest's token was deleted.
- **Baselines, read-only, as Derek.** As owner he sees every Space, so the picker renders. `/projects/new` and `/librarian`, Light and Dark at 1440 and 390: 8 checks, status 200, no overflow, 0 axe violations, 0 page errors. The 390px captures were looked at, not just the summaries (learning #242). See `baseline-projects-new/` and `baseline-librarian/`.

## Gates

| gate | result |
| --- | --- |
| red checks | 8 backend tests fail on the old backend; 5 frontend tests fail on the old pages |
| CI's backend-suite invocation, locally | first run: 2 failed, 2815 passed. It caught the missing OODS contract mapping for `ProjectCreate.workspace_id` (learning #210's rule) and a PERSONAL-1 static test that asserted `workspace_id` never appears in the npm handler. Both fixed in `9d220ae`; CI backend-suite then passed |
| ruff 0.8.0; Secret Scan; tsc, eslint, OODS token gate | clean |
| vitest; MCP unit tests; tarball check | 258/258; 148/148; pass |
| `mcp_parity_audit.mjs`, `mcp_argument_parity.mjs` and their self-tests; harness route inventory (learning #240) | exit 0; 4 passed |
| PR #366 | ten of ten checks. backend-integration passed on its second attempt: `test_graph_layer_depth2_performance_under_200ms` measured 268 ms, of which a garbage-collection pause took 255 ms while SQL took under 4 ms |
| main-push runs for `2bcc766` | seven green; Backend Integration failed on attempts 1 and 2 with the same garbage-collection flake (225 ms and 231 ms, gen-2 pauses of 210 and 215 ms, SQL under 4 ms). PR #367 (`9f1b11b`) fixed the gate at its root by timing the graph layer with collection off, as timeit does. All eight main-push runs for `9f1b11b` are green (Backend Integration `35802628080`, Backend Tests `35802628096`, Backend Lint `35802628108`, Frontend Checks `35802628092`, Frontend Production Build `35802628069`, MCP Package `35802628083`, Secret Scan `35802628062`, Post-Deploy Check `35802628791`) |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | non-admin route lists the caller's Spaces, personal first; owner and admin get every Space; RBAC scope respected; classified in the parity manifest, audit exit 0 | met (`GET /spaces`; `TestListMySpaces`; manifest row) |
| 2 | optional `workspace_id`: 403 for a non-member, 404 for owner and admin naming a missing Space, absent means personal; a test proves a non-member cannot place a project and `owner_id` is never taken from the body | met (`TestCreateInASpace`) |
| 3 | picker only with more than one Space, defaulting to "My Space"; nothing changes with one Space; vitest covers both states | met (5 cases across the create form and the Librarian) |
| 4 | nothing new on the project hub; the picker is the only member-facing Space UI | met |
| 5 | the MCP create passes `workspace_id` through the same validation, with a test through the MCP client | met (MCP vitest drives the handler to the POST body; an X-API-Key create is held to membership; the Python MCP server has no project tool) |
| 6 | production: a project created with the picker lands in the shared Space and is listed for a second member; receipt here; roadmap change log | met |
