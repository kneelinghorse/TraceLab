# WALK-2 receipt: the rewalk, unwatched (2026-09-22)

Derek walked the guest path a second time in production as the re-enabled
non-privileged account, on the build that contains LIB-2, GUEST-1 and BADGE-1.
He walked it unwatched; this receipt is reconstructed from his report in session
`PS-2026-09-22-009` and a read-only database check in `PS-2026-09-22-010`.
Nothing was fixed inline (criterion 4). Decisions #526, #530, #531.

## Setup

| item | value |
| --- | --- |
| guest account | `walk1-guest@tracelab.local`, role `member`, user `148bcf80`, re-enabled 19:2x UTC (next-step #423) and left enabled for the PERSONAL-1 backfill (next-step #428) |
| guest Space | "Walkthrough Guest" (`e0d2ba43`), the guest its only member |
| project | the WALK-1 project "RBAC for complex systems" (`d2d6519c`), reused, still in Default Workspace because it predates GUEST-1 |
| frontend / API | https://tracelab.aquex.ai at main `3f2dd9c`, https://api.tracelab.aquex.ai |

## Timeline (UTC, from the database)

| time | event |
| --- | --- |
| 20:05:27 | `POST /librarian/missions` creates mission `2dedcb41` "RBAC integration strategy for MCP tools and local services", `created_by=librarian` |
| 20:05:35 | submitted; DeepSearch starts the run (usage row `deepsearch_run`, attribution `submitter` = guest) |
| 20:08 | Derek reports in: mission in progress, one observation (below), no blockers |
| 20:09:45 | completed: DeepSeek Flash, 31 steps, 67 tool calls, 2,276,022 tokens, 249.9s; 243 ledger entries |
| 20:09:50 | all 13 mission log lines created in one batch (`logged_at` 20:05:35 to 20:09:49); the guest opens the mission page (`user_item_views` mission row) |

## What Derek said

At turn 3 the Librarian offered to sketch a solution; he pressed Draft instead.
The draft reframed the outcome from research into a deliverable, and the
pre-submit feedback said so before anything ran: "very nice touch". No blocking
findings reported.

His sentence on the gate (criterion 6): **"walk is done, close it out. its fine
for now."**

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | walked live as the re-enabled member on the deployed build with LIB-2, GUEST-1, BADGE-1 | met, on `3f2dd9c`; unwatched rather than live with the agent |
| 2 | WALK-1 findings 1, 3 and 6 do not reproduce | met on Derek's report: he reached Submit without asking what to do next and reported no loss or silent draft. These are client-side behaviours, so the database holds no evidence either way; the LIB-2 receipt's read-only live check stands as the mechanical proof |
| 3 | the new project carries the guest's Space; the badge clears after one visit, both checked in the database | **not exercised in the walk**: Derek reused the WALK-1 project (`d2d6519c`, Default Workspace), and no `user_item_views` evidence row exists for run `2dedcb41`'s group. Both were verified in production on 2026-09-22 in the GUEST-1 and BADGE-1 receipt, and PERSONAL-1 supersedes the placement rule anyway |
| 4 | new findings recorded, nothing fixed inline | met; one observation, no defect |
| 5 | Runner logs during the run, or #412 stays open with evidence | **#412 stays open**: 13 lines, every `created_at` 20:09:50, five seconds after completion, while `logged_at` spans the run |
| 6 | Derek's sentence on good working order, recorded as a decision | met; decision #531 |

## Consequence for the invite gate

Decision #526 gated invites on this walk. Decision #530, taken before the walk,
puts personal Spaces ahead of bringing people in ("good working order before
people come in"). Read together: the walk passed, and invites wait for
PERSONAL-1 to ship, not for a third walk.
