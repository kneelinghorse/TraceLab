# LIB-1 production acceptance: one Librarian-authored mission, run unmodified

Observed 2026-09-22 UTC against the deployed TraceLab at merge commit `3118036`
(PR #349), Railway deployments `1027f7e8` (TraceLab) and `40d8312f` (frontend),
both `SUCCESS` at that commit before any call was made. The acceptance script
drove the deployed REST routes as the UI does, authenticated as Derek's admin
API key (the same principal that owns every other production mission). The
recorded run is `run-2026-09-22.json`; status polls are collapsed and no
credential material was recorded.

## The flow

| Step | Route | Result |
| --- | --- | --- |
| Turn 1 | `POST /api/v1/librarian/turns` | 200 in 20.7 s, gpt-5.1, 2,636 tokens |
| Turn 2 | `POST /api/v1/librarian/turns` | 200 in 18.4 s, 5,808 tokens |
| Draft | `POST /api/v1/librarian/drafts` | 200 in 9.4 s: `TRACE-SHARE-58`, 6 criteria of 80 to 105 characters, compiled to 7 objectives, 19 evidence slots, 1 deliverable schema, 19 acceptance checks (compiler `24e8810`, `structural_only`), no lint errors |
| Create | `POST /api/v1/librarian/missions` | 201, `created: true`, `status: draft`, `created_by: librarian`, `librarian` tag appended, project `0afcc588` (TraceLab Research) |
| Submit | `POST /api/v1/missions/dca03dd0…/submit` (existing route) | 200, `queued`, no warnings |
| Run | DeepSearch job `c00c9707` | `completed` at 02:15:52 UTC after 4 m 20 s |

Result: document `04ffc800` (`TRACE-SHARE-58_report.md`, 6,340 words, 14
chunks), report `e21193eb`, 226 sources collected, 41 verified references,
360 evidence ledger entries attached to mission `dca03dd0`. The mission ran
without any hand edit between draft and submission, which is what criterion 6
asks.

## What the run found

1. **Chat replies were truncated.** Both turns exceeded the 1,500-token reply
   cap (1,535 and 1,545 completion tokens), so the JSON never closed and the
   parser's fallback showed the raw, truncated JSON as prose and lost
   `suggested_action`. Fixed in PR #350 (finish_reason recorded, one concise
   retry, 3,000-token cap, prompt asks for replies under 350 words, salvage
   fallback that drops every citation). Learning #236.
2. **The LIB-0 compiler defect surfaced and was reported to the user.** Criterion
   5 (105 characters, "Include direct references or screenshots…") compiled as a
   deliverable schema rather than a research objective; the draft response's
   `notes` said so before creation. The run still completed because six other
   objectives carried the research.
3. **The research is usable for Sprint 58.** The report classifies twelve
   products into workspace-inheritance, project-level and hybrid grant models
   and recommends a hybrid, project-bounded model with an explicit resolution
   rule and a share modal that enumerates access sources in descending breadth,
   which is the blast-radius requirement of decision #516 stated as a mechanism.

## Not verified here

- The `/librarian` page in a browser: `GET https://tracelab.aquex.ai/librarian`
  returns 200 and the production `next build` emitted the route, but no
  screenshot baseline was captured in this run. The route is now in
  `frontend/scripts/ui-shell-smoke.mjs` for the next baseline.
- A non-admin principal in production. The criterion-7 sweep (a stranger gets
  403 on all three routes under RBAC) is covered by `tests/test_librarian_api.py`;
  no second production account was used.

## After the fix (PR #350, merge `ab38726`)

Railway redeployed both services at `ab38726` (TraceLab `6cb01be8`, frontend
`40f48c60`, both `SUCCESS`). The same first prompt was sent again to
`POST /api/v1/librarian/turns` (`turn-recheck-after-350.json`): HTTP 200, one prose
segment of 2,782 characters, 769 completion tokens under the 3,000 cap, no
withheld segment, and no brace or `"segments"` text anywhere in what the user
would see. The reply opens "You're essentially comparing two patterns" and
lists the per-project and workspace grant models as prose, which is the
intended rendering.
