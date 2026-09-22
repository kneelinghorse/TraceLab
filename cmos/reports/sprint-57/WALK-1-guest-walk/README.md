# WALK-1 receipt: the guest path, walked live (2026-09-22)

Derek walked `/librarian` in production as a fresh, non-privileged account while
the agent watched the database and request log. Session `PS-2026-09-22-005`.
Nothing was fixed during the walk (criterion 4). Decisions #524 and #525,
learning #238.

## Setup

| item | value |
| --- | --- |
| guest account | `walk1-guest@tracelab.local`, role `member`, user `148bcf80`, created 14:23:05 UTC via `POST /admin/users`, disabled 15:27 UTC after the walk |
| guest Space | "Walkthrough Guest" (`e0d2ba43`), the guest its only member |
| starting view | `GET /projects` 0 rows, `GET /missions` 0 rows (a member with no Space membership sees only what it owns) |
| frontend / API | https://tracelab.aquex.ai at main `4f2b232`, https://api.tracelab.aquex.ai |

## Timeline (UTC, from the Railway HTTP log and the database)

| time | event |
| --- | --- |
| 14:27:01 | guest creates project "RBAC for complex systems" (`d2d6519c`) inline on /librarian; `workspace_id` = Default Workspace |
| 14:28:36, 14:34:37, 14:37:23, 14:39:10 | four `POST /librarian/turns`, all 200 (14.0s, 13.7s, 8.5s, 9.0s), model gpt-5.1 |
| 14:39:36 | `POST /librarian/drafts` 200 in 9474ms (request `QMWvKbJuQka4anqdHn5Ytg`), usage row `librarian_draft` 864 output tokens. Derek: "nothing really happened" |
| ~14:41 | Derek navigates to /missions and back; transcript gone |
| 14:48:07, 14:50:36 | redo: two turns (17.2s, 13.5s) |
| 14:51:05 | `POST /librarian/drafts` 200 in 7996ms; Derek scrolls: "yes, it shows" |
| 14:51:20 | `POST /librarian/missions` 201; mission `76c97203` "Designing Tenant-Aware Shared RBAC with Centralized JWT Auth", status draft, `created_by=librarian`, tag `librarian` |
| 14:52:05 | `POST /missions/76c97203/submit` 200; usage row `deepsearch_run` queued, attribution `submitter` = guest. First mission in production not run by Derek |
| 14:52:09 | DeepSearch starts the run |
| 14:57:24 | completed: DeepSeek Flash, 23 steps, 67 tool calls, 1,319,068 tokens, 315.4s; 296 ledger entries, evidence outbox delivered; usage row filled |
| 14:57:29 | all 12 mission log lines created in one batch (logged_at 14:52:09 to 14:57:28) |

## Findings, in the order they were seen

1. **Transcript lost on navigation.** Derek: "i navigated to missions, nothing running, i went back to librarian and the entire conversation was gone. no history or any sign it ever existed." Four paid turns and a draft, none survive. The transcript is component state only (decision #519 made the server stateless; nothing keeps it on the client). To LIB-2.
2. **A guest's new project lands in Default Workspace, not the guest's Space.** `default_workspace_id()` in `app/services/ownership.py` assigns the seeded default to every new project. The guest still sees it through ownership and nobody is a Default member today, so nothing leaked, but it is not the guest model Derek described, and it answers criterion 5: a project has one `workspace_id`, so a seeded reference corpus cannot be shared across guest Spaces without duplication or a shared Space. Next-step for SHARE-1 scoping.
3. **A successful draft was rendered offscreen and silently.** The draft panel is placed below a 60vh transcript box with no scroll, toast or focus; the only signal is the button reading "Drafting…" for nine seconds. Derek read success as failure and left, which triggered finding 1. Confirmed on the redo. To LIB-2.
4. **When to draft is unclear.** Derek: "After two turns, it was still asking me qualifying questions, the first time it went 4 rounds and then i think it said we have enough. Either is fine ... but its not a clear CTA." The model's `suggested_action` renders as a line of text under the buttons. To LIB-2; the colour-meter idea is a nice-to-have by Derek's own words.
5. **The transcript box is tight.** Derek: "when the agent returns a longish answer, its a bit hard to see/follow because we're in a smallish box." To LIB-2, approach open (take over the page, expand on first reply, or user-expandable).
6. **The two-step flow is not explained.** Derek: "not sure if a user will know they need to submit first to create the draft mission and then submit again to deepsearch to run the research." Derek keeps the two steps deliberately ("a draft ... can be run at anytime"); orientation and a dismissable step indicator go to LIB-2.
7. **The Evidence badge needs every entry viewed to clear.** Derek: "the report gathered nearly 300 pieces of evidence and it is 29 pages to review all of them." The nav badge is the activity "new" count per type; `PUT /activity/viewed` marks items as they are rendered, so one run adds 296 and clearing means paging through all of them. Next-step.
8. **"DeepSeek translates evidence into Chinese" is not what happens.** Of 296 entries, 2 are in non-Latin script and both are pages natively in Japanese and Chinese; across all 7,272 production entries, 90 (1.2%) are. The search step picks foreign-language sources; no translation occurs. Next-step, low priority.

Also confirmed during the walk (not a Librarian finding): DeepSearch posts mission logs only as one batch after completion, which is why the Runner logs panel stayed empty for the whole run. Message `1621f451` sent to DeepSearch with the request-log evidence and the ask to flush during the run (next-step #412; learning #238).

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | authored and watched to completion with Derek present, from a fresh Space, the guest's view | met; the fresh Space existed but the project landed in Default (finding 2) |
| 2 | every defect recorded with evidence at the moment seen | met; eight findings, each with request-log or database evidence, Derek's words verbatim |
| 3 | run by a non-privileged principal | met; role `member`, no Space membership beyond its own |
| 4 | findings become missions or next-steps; nothing fixed inline | met; LIB-2 in sprint-58 carries 1, 3, 4, 5, 6; next-steps carry 2, 7, 8 and the DeepSearch flush |
| 5 | the cross-space question answered concretely | met; finding 2 |

Derek's verdict: "definitely some UX improvements needed but overall, very impressed so far." and "Overall, this was a really great first version."
