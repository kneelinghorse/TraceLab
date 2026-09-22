# LIB-2 receipt: Librarian orientation and persistence (2026-09-22)

The five Librarian findings from the live guest walk (WALK-1), fixed as Derek
decided them (decisions #525, #527) and nothing beyond. Session
`PS-2026-09-22-006`. PR #358, squash-merged as `ff0dc98`.

## What changed

| WALK-1 finding | change | where |
| --- | --- | --- |
| 1 transcript lost on navigation | conversation, project and draft persist per user in `localStorage` and are restored on return; "Start over" clears; server unchanged (#519) | `frontend/src/lib/librarian/storage.ts`, `pages/librarian.tsx` |
| 3 draft rendered offscreen in silence | a draft the user asked for is scrolled into view, focused, announced by a toast; the panel footer names the next step | `pages/librarian.tsx` (`DraftPanel`) |
| 6 two-step flow unexplained | `LibrarianSteps` strip on /librarian; orienting notice on a draft mission reached with `?from=librarian`; one "Don't show this again" preference hides both | `components/librarian/LibrarianSteps.tsx`, `pages/missions/[id].tsx` |
| 4 draft CTA faint | Draft becomes the primary button when `suggested_action` is `draft_mission`; Send becomes secondary | `pages/librarian.tsx` |
| 5 transcript box tight | once a conversation exists the column widens to `max-w-6xl`, the transcript cap rises from 60vh to 75vh with a 50vh floor, and an Expand toggle lifts it | `pages/librarian.tsx` |

Untouched by Derek's choice: the two-step create-then-submit ("a draft ... can
be run at anytime"). Not built: the colour meter (his "nice to have").

## Verification

| gate | result |
| --- | --- |
| tsc, eslint (changed files, max-warnings 0), OODS token gate | clean |
| vitest, whole suite | 247/247; new assertions: persistence across unmount and Start over, focus and announcement after Draft, primary CTA, `?from=librarian` handoff, strip dismissal remembered, mission-page notice shown from the Librarian and never when opened directly |
| CI on PR #358 | all ten checks pass |
| Railway | TraceLab and frontend SUCCESS at `ff0dc98`; `/api/v1/health` healthy, commit `ff0dc98` |
| production baseline | `/librarian` Light and Dark at 1440 and 390: 4 checks, 0 failures, 0 overflow, 0 axe violations, 0 page errors (`summary.json`, `results.json`, four PNGs here). Closes next-step #409 |
| live check of the deployed bundle (read-only Playwright, no model call) | a stored conversation renders on load, the step strip, Start over and Expand controls are present, Draft carries `data-suggested="true"` after a suggestion, dismissing the strip survives a reload, the conversation survives a reload, no page errors, health commit `ff0dc98` |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | transcript, project and draft survive navigation and reload; a test proves the WALK-1 loss cannot recur | met (unit test + live check) |
| 2 | draft scrolled into view and focused, button copy states what comes next, two-step kept | met |
| 3 | mission page orientation notice from the Librarian, dismissable and remembered | met |
| 4 | Draft is the prominent action on `suggested_action`; no meter | met |
| 5 | more transcript room once a conversation starts, usable at 390px, choice recorded (decision #527: expand on first reply plus a user toggle) | met; 390px baseline has no overflow |
| 6 | screenshot baseline under `cmos/reports/sprint-58/` | met, this folder |
| 7 | a second live guest walk or first-time-user feedback confirms findings 1, 3 and 6 no longer reproduce | **not yet**: that is WALK-2's first two criteria, by design; LIB-2 is accepted when Derek's rewalk passes |
