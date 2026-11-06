# MCP-5 receipt: @aquex/tracelab-mcp 2.0.0 (2026-09-23)

Derek: "i do want the mcp updated" (decision #535). He published it himself with his npm login and one-time code; everything before and after that was the agent's. Session `PS-2026-09-23-001`.

## What 2.0.0 is

2.0.0 is a major release because 1.2.0 callers lose tools and parameters.

- **Removed (ACT-1, decision #459):** `tracelab_home.attention`, `inbox_summary`, `inbox_list`, `tracelab_mission.views`, and the `view` and `reason` parameters of `tracelab_mission.list`.
- **Added:**
  - `tracelab_home.activity` and `activity_summary` (ACT-1);
  - an optional `workspace_id` on `tracelab_project.create`, and `workspace_id` on `list` and `create` output (PERSONAL-2, decision #533).

The surface is 9 tools and 49 actions. The README, `docs/mcp-tools.md` and `AGENTS.md` had said 51 since ACT-1 and now match the parity audit.

## Release

| step | result |
| --- | --- |
| release PR #370: version 2.0.0 in `package.json` and the lockfile; CHANGELOG `[2.0.0] — 2026-09-23`; docs | merged as `a5c882b`, ten of ten checks green |
| local gates | build; MCP unit tests 148/148; installed-tarball check at 2.0.0; both parity audits exit 0; Secret Scan |
| tag | `tracelab-mcp-v2.0.0` (annotated) on `a5c882b` |
| clean worktree of the tag: `npm ci`, build, `npm publish --dry-run` | 24 files, 72.3 kB, shasum `591313b74f7795f1ce1ba4c006e75163987fa14e`; the only `__dirname` in `dist` is the ESM-safe definition from the 1.0.1 fix (decision #192) |
| publish, by Derek | `npm view`: version 2.0.0, `latest` 2.0.0, published 2026-09-23T02:28:51Z, shasum `591313b7…` and 24 files, identical to the dry run |

## The published package, end to end (DoD-1)

`npx-smoke.mjs` is adapted from Sprint 52's MCP-3 smoke, whose 1.2.0 assertions (51 actions, `inbox_summary`) no longer hold.

- **How it ran:** it started `npx -y @aquex/tracelab-mcp@2.0.0` from an empty directory with a minimal environment and connected a real stdio MCP client. It used Derek's existing API key, passed only to the child process and never written to the receipt. Every call was read-only.
- **Results (`mcp-5-production-smoke.json`): 15 of 15 passed.**
  - The server reports 2.0.0, with 9 tools and 49 actions.
  - `tracelab_home` offers `activity` and `activity_summary` and no longer offers `attention` or the inbox actions; `tracelab_mission` has no `views`.
  - `tracelab_project` advertises `workspace_id`, and its `list` output carries it.
  - The tool set matches the parity manifest.
  - One read-only action per tool succeeded against production.
  - All 27 generated canonical links resolve with HTTP 200.

The same script had already passed 15 of 15 against a locally packed tarball before the publish, so the script itself was proven first.

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | 2.0.0 in `package.json` and the lockfile; CHANGELOG dated; docs state the true action count; audits and package tests pass | met (PR #370) |
| 2 | merged with green CI, tagged, clean-worktree dry run | met |
| 3 | Derek publishes with his one-time code | met, 02:28:51Z |
| 4 | the published artifact installed fresh and run end to end; `npm view` matches the dry run | met, 15/15; shasum identical |

## Next

The one Librarian capability agents lack, corpus Q&A with resolving citations, joins the Sprint 59 Q&A work as MCP-6 (decision #536, Derek: "yes, lets add it to s59"), for a minor release after this one.
