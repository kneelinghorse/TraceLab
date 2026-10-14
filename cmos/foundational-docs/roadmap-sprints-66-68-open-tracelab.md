# TraceLab — Roadmap: Open TraceLab (Sprints 66–68)

**Status:** Living document. Authoritative for INTENT; the Reasonbook record (formerly CMOS) is authoritative for STATUS.
**Opened:** 2026-10-13, at Sprint 66 planning (session PS-2026-10-13-003).
**Predecessor:** [roadmap-sprints-57-60-the-librarian.md](roadmap-sprints-57-60-the-librarian.md), which carried Sprints 57–65 and is now closed to new sprint sections.
**Guiding template:** [roadmap_template.md](roadmap_template.md).

Revisit this document at every sprint open and close. At close, rewrite the closing sprint's section as outcome. At open, re-plan the opening sprint's section from the record's missions. Append a dated line to the Change Log either way.

---

## Why this arc

> "TraceLab is set to be shared next week and one of the things i've always wanted to do was not only make our tracelab repo open but also the deepsearch engine with it. we've made a lot of changes lately with the librarian and it works pretty well. but we have a lot of UX stuff to work out still." — Derek, 2026-10-12

> "lets get these carry forward and remaining items put to bed first." — Derek, 2026-10-13

The Librarian arc was accepted in Sprint 60, and Sprints 61–65 made the system dependable: account recovery, live run logs, guided mission creation, authored scope and a repaired Ledger contract. This arc takes TraceLab from a system Derek runs to one other people can see, use and read, starting with the share-out on **Monday 2026-10-19**.

Three things must be true that day:

1. **Nothing old is left hanging.** Every carried follow-up is done, scheduled or closed with a reason (Sprint 66).
2. **The public repository can be read, used and trusted.** It is already public. It lacks a license and a front page that describes today's product. It holds other people's personal data that should not be there, and nobody has checked its history for a live credential (Sprint 66).
3. **The rough edges people hit first are gone.** That is Derek's UX and design feedback (Sprint 67).

---

## Where we are (2026-10-13, verified)

| Fact | Value | Why it matters |
| --- | --- | --- |
| Production | Both services serve `bb0b270` (PR #414); Production Smoke green on it at 2026-10-13 14:38 UTC | Nothing is mid-deploy |
| Backend CI | Red on every fresh run since pydantic 2.14.1 (published 2026-10-11): mcp 1.6.0 imports a pydantic internal that 2.14 removed. The last green main run (`bb0b270`, 2026-10-02) had pydantic 2.13.5 | Nothing can merge until pydantic is capped (PR #416). Production is unaffected until its next image build, because `app/main.py` does not import `app.mcp_server` |
| Sprints and missions | No sprint open, nothing queued; Sprint 65 closed 2026-10-02 | Clean start |
| Open follow-ups | 24 (21 carried, 3 pending) | All dispositioned below |
| GitHub | TraceLab **public**, no license, no topics or homepage, private vulnerability reporting off; GitHub secret scanning and push protection on, with no alerts. DeepSearch.alpha **private**, no license | "Open" here means *licensed, clean and presentable*, not *visible* |
| Personal data in the public tree | Three people's email addresses, with names and roles, in `cmos/reports/sprint-55/rbac-1-users-before.json`, `-after.json` (eight accounts each, plus the production `AUTH_USERNAME`) and `cmos/reports/sprint-62/S62-DEPLOY/broad-ui-smoke.json`; 54 screenshots of the admin Users page show every account's email and role | Published without those people's say; also in history |
| Binary record data in history | 16 revisions of `cmos/db/cmos.sqlite-wal`, 10 of `cmos.sqlite-shm` (committed 2025-12-10 to 2026-03-02) and `cmos/db/cmos.sqlite.backup-20251112-162503` | A text scan of `git log -p` cannot see inside them |
| Third-party licenses in the tree | Both vendored Forge/OODS packages the frontend depends on, `@oods/tokens` and `@oods/tw-variants` (`frontend/vendor/oods-*-0.1.0.tgz`, `frontend/package.json:20-21`), are PolyForm-Noncommercial-1.0.0 | TraceLab's own license cannot cover them (Open Question 1) |
| Repo weight | About 600 MB on GitHub; `cmos/` is 4,049 tracked files, and its 2,453 receipt screenshots are about 970 MB of the roughly 1 GB tree | A clone is about 1 GB, shallow or not |
| Front page | `README.md` opens with stale fragments ("…workflows.+ mcp", "## Tech Stack -dn") and predates the Librarian, DeepSearch runs, the Evidence Ledger and the MCP; `tracelab.egg-info/` is committed | First thing a visitor sees |
| Sign-up | A single-use invite code that an admin generates (`app/api/v1/auth.py:128-182`) | Derek decides who gets in |
| App runtime coupling to `cmos/` | Nine telemetry writers default to `cmos/telemetry/events/`; the coverage report rewrites a Sprint 1 receipt on every request and ingestion; the admin-only decision-links router reads and writes the record database | Tests dirty tracked files (#380); an open-source app should not write into its planning record |
| Browser specs | 22 under `frontend/tests/e2e/`; CI enumerates 13; 9 never run | Several accepted features have no running gate (#485) |
| MCP | `@aquex/tracelab-mcp` 2.1.2 on npm; its README's global-install line still pins 2.1.1 | Fix promised to Aquex at the next publish (#486) |
| Reasonbook clients | Claude Code and Codex both run the Reasonbook 4.0.1 plugin | The 4.0 folder move waits only on TraceLab's own references (Sprint 68) |

---

## Sprint 66 — Clear the deck (opened and finished 2026-10-13 UTC, eight of eight; closed 2026-10-13)

**Goal:** every carried follow-up is done, scheduled or closed with a reason, and TraceLab's public repository is clean, licensed and ready to be read and run.

**Outcome:** met, two days ahead of the 2026-10-15 target. All eight missions merged one at a time, each deployed and verified on production before the next started. The sprint opened on Derek's "yes, merge" (decision #614). Derek added S66-SECURITY mid-sprint, after FRONT's clean install surfaced dependency advisories (decision #618). Final state: `main` and both Railway services serve `7204961` (PR #423). All eight main workflows and Production Smoke are green on it. Backend: 3,179 passed, 4 existing skips, 12 documented deselections. PostgreSQL integration: 171 passed, 3 skips. Frontend: 385 unit tests. Browser: 145 cases, no skips or retries.

| Mission | PR / merge | Accepted outcome |
| --- | --- | --- |
| **S66-DEPS** — Restore the backend build | #416, `7ee7c8c` | pydantic is capped below 2.14, so mcp 1.6.0 imports again. The deployed container reports pydantic 2.13.5. fastapi and starlette stay floating (learning #302). |
| **S66-EXPOSURE** — What the public repository exposes | #417, `dffbf7d` | gitleaks (always `--redact`) covered every ref, the working tree and the text of all 1,799 binary blobs in history. All 175 findings are dispositioned, and none is a credential that is not provably dead: the historical keys were invalidated per learning #121. The legacy password login behind `AUTH_USERNAME` is unreachable in production, decided from code and variable names only. Third-party personal data is gone from the current tree. Decision #615 widened the scope to fixtures, personal-space labels and smoke diagnostics. 58 screenshots are masked (54 Users and 4 Spaces) and OCR-clean. The smoke harness now masks email cells, and the required Secret Scan job has a fixture-proven email guard. The stray record backup is removed, and history is kept (decision #614). |
| **S66-SETTINGS** — Local times, phone-width Settings | #418, `67c7dee` | Every API time in `frontend/src` goes through `parseApiTimestamp`. A fixed-clock America/Chicago browser test fails on the old build, passes on the new and runs in CI. Settings rows hold whole-word labels at 390 px in both themes. Read-only production check: 13 timestamps, no overflow, no serious or critical axe findings. |
| **S66-FRONT** — The repository's front door | #419, `b58345b` | MIT `LICENSE` (decision #613), a `NOTICE` naming the PolyForm-Noncommercial OODS packages, a rewritten `README.md`, `SECURITY.md` and `CONTRIBUTING.md`. GitHub shows MIT, the description, the homepage and topics, and private vulnerability reporting is on. `tracelab.egg-info/` is gone. A fresh GitHub clone followed the README to UI and API 200s. The first attempt silently reused an existing local database; that was disclosed, and the proof was rerun in an isolated Compose project (decision #617, learning #306). |
| **S66-SECURITY** — Frontend dependency findings | #420, `381a3aa` | Next 16.3.8, sharp 0.35.5, Vitest 4.1.11 and Vite 7.3.7 (decision #619). The full audit fell from 37 affected packages to 10, and production-only from 15 to 8. Every critical finding is removed. The remaining entries trace to two build-only advisories, `braces` and selector-parser 6.x under Tailwind 3; they are dispositioned, not suppressed, and carried to Sprint 68. Build tools are declared for the production-only install (decision #620, learning #307). Production serves Next 16.3.8. |
| **S66-DECOUPLE** — The app stops writing into the record folder | #421, `e04d3df` | Eleven output defaults moved to the gitignored `telemetry/runtime/`. The admin dashboard's live telemetry is unchanged (decision #621). The decision-links router is retired (decision #609), and production answers 404 to an authenticated owner. The CI backend run now leaves `git status` empty; before, it changed six tracked files. The 39 surviving `cmos` references in `app/` are documented comments or identifiers. |
| **S66-TESTS** — Every browser spec runs | #422, `87d2313` | All 23 spec files are covered by the CI workflows. The nine revived specs add 48 cases. Their first run exposed a real queued native-dialog close race, now fixed with a regression test (learning #309). A plain local Playwright run now builds and starts production, as CI does. The graph timing gate keeps the best of three warmed rounds, with response caching disabled (decision #622, learning #308). |
| **S66-MCP** — The documented mission schema works | #423, `7204961` | Registry 2.1.2's own example reproduced a 422 on the deployed preview route. The corrected README, tool and UI examples compile there, with no research run, and every draft is deleted. The public boundary stays a single object (decision #623, learning #310), and the README installs `@latest`. Derek approved the publish of `@aquex/tracelab-mcp` 2.1.3. The registry tarball is byte-identical to the tested pack, and a fresh install passes all 70 stdio checks ([receipt](../reports/sprint-66/S66-MCP/registry-verification.json)). |

**Follow-ups:** eight carried rows were closed by this sprint's missions: #174, #275, #280, #379, #380, #448, #485 and #486. Three stay open, all scheduled:
- #406 (raw Markdown table rows shown as claim text) is in Sprint 67;
- #489 (scope Sprint 67 from Derek's UX doc) is the next planning session;
- #490 (the two residual build-tool advisories) is in Sprint 68.

**What went wrong, and was caught:**
- FRONT's first quickstart proof migrated an existing local database instead of starting fresh. It was disclosed and repeated in isolation.
- SECURITY's first CI build failed because a local production-only build had silently auto-installed TypeScript. CI's refusal was correct.
- MCP's publish waited on Derek's npm browser sign-in. It is the one step an agent cannot take.

Receipts: `cmos/reports/sprint-66/`. The mission completion records hold the run IDs and live-check details.

**Out of Sprint 66, as planned:** new product features, UX redesign (Sprint 67), project sharing (Open Question 5), the Reasonbook folder move (Sprint 68), any history rewrite, paid research runs, and any work in the DeepSearch repository.

---

## Sprint 67 — The UX pass (opened 2026-10-14 UTC; target close 2026-10-15)

**Goal:** an invited person on Monday finds TraceLab calm, dense and obvious:
- no counts they can't clear;
- a finished mission opens on its results;
- the Librarian starts as a conversation;
- Reports holds documents, not copies;
- claims read as sentences.

**Source:**
- Derek's UX feedback, 2026-10-13;
- the carried follow-up #406;
- the share-out walk named at Sprint 66 planning.

Derek's answers at planning:
- a dot on Missions only;
- "new" lasts 3 days;
- the Librarian is conversation-first, with its tools in a chooser;
- Reports is cleaned up now, not after the share-out: "WE HAVE A WEEK TO CLEAN THAT SHIT UP, STOP DEFERRING."

The email part of his notification ask already exists. Settings → Notifications switches mission emails on and off (`frontend/src/pages/settings.tsx:177-219`, `users.email_notifications_enabled`, default on). Only a text-message channel is left out, and it needs a provider and phone numbers.

**Order:** DENSITY → REPORTS → BADGES → MISSION → QUALITY → LIBRARIAN → CLAIMS → WALK. QUALITY was added at planning from DeepSearch's request and follows MISSION, because both change the Results tab. Each mission is merged, deployed and verified on production before the next starts, as in Sprint 66.
- **DENSITY first.** It adds the shared page header and container that later pages use, so later screenshots show the final spacing.
- **REPORTS before BADGES.** Both change `app/adapters/repositories/sqlalchemy_activity_repo.py` and the MCP. BADGES adds seen-state to a Reports list that REPORTS has already cleaned. BADGES carries the sprint's single MCP publish, 2.2.0, which includes REPORTS' changes.

**Rules for every mission:**
- A new browser spec is added to the enumerated list at `.github/workflows/frontend-production-build.yml:91`.
- A test that pins old behaviour is updated in the same PR, with the reason in the PR description; it is never skipped.
- UI evidence means captures at 1440 and 390 px in light and dark, with no horizontal overflow and no serious or critical axe findings.
- The production check after deploy is read-only, through the existing X-API-Key method.
- No new environment variable or setting.
- Any change to an API response that the MCP or the OODS object model exposes names its guard:
  - `cmos/contracts/oods-object-model.json`, checked by `tests/unit/test_oods_object_contract.py`;
  - the MCP Contract Guard, a test through the MCP client;
  - `cmos/contracts/mcp-parity-manifest.json` with `node scripts/mcp_parity_audit.mjs`.

### S67-DENSITY — Tighter, data-platform spacing

> "we just have a lot of space … we could kind of condense it, get a little tighter, a little more enterprise-y … the report and the missions … are actually, I think, maybe a good guide."

**Today:**
- No shared page container exists; every page writes its own.
- Home uses `max-w-7xl space-y-7 px-4 py-8 lg:py-10` with a `text-3xl` h1.
- Missions, Evidence and Reports use `space-y-6 py-8` with `text-3xl`.
- The Librarian stacks up to seven `p-5` panels.
- The mission and report detail pages are already dense: one card, `p-6` sections and a `text-2xl` title.

**Change:**
- **Shared header and container.** Add one `PageHeader` component (h1 at `text-2xl`, with an optional description and actions on one row) and one page container (`mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4`). Use both on:
  - Home and the Librarian;
  - the Projects list and project detail;
  - the Missions list, Evidence and the Reports list;
  - the Collections list and collection detail.
- **Reference pages unchanged.** The mission and report detail pages keep their layout and are the reference.
- **Spacing at call sites.** Panel padding goes from `p-5` to `p-4` and list rows to `py-3`, changed where each panel or row is written. **The `.panel` class itself is not changed.** It is plain CSS after `@tailwind utilities` (`frontend/src/styles/globals.css:3,25`), so padding added there would override every call site.
- **Unchanged:** body text size, small text at no less than 14 px, and the contrast tokens.

**Done when:**
- At 1440×900, on every listed page, the first content row's top is at least 40 px higher than it was. The receipt records the before and after pixel positions.
- Home shows at least 3 more Recent activity rows above the fold than before, on the same fixture.
- Every listed page has captures in both themes at 1440 and 390, with no overflow and no serious or critical axe findings.
- Existing visual and accessibility specs pass. They are updated only where spacing is the intended difference.

### S67-REPORTS — Reports holds documents, not a copy of every mission

> "reports, you kind of expect it to be a written report of some kind … what's a collection versus a report? … If they're agent tools and they are helpful, let's keep them."

**Today:** production holds 512 reports (read-only count, 2026-10-13).

| Kind | Count | Where they come from |
| --- | --- | --- |
| Automatic copies of mission results | 451 | One per completed mission, titled "Research: *mission title*" (`app/services/auto_report.py:310`). 448 are still linked from their mission's `result_report_id` |
| Written from collections or excerpts | 47 | A person or agent, through the report API (`app/services/report_service.py`, `app/api/v1/synthesize.py`) |
| Agent evidence briefs | 12 | Promoted from an Evidence Ledger session (`app/services/evidence_ledger.py:1305`, type `evidence-ledger`) |
| Librarian reports | 2 | `app/services/librarian_reports.py:195`, provenance origin `librarian` |

510 of the 512 are drafts.

How the copies show up:
- **Reports list:** each row shows the raw type ("markdown"), the excerpt count and "0 tokens", and the filter is draft/final.
- **Report detail page:**
  - shows "Type: markdown" and "Tokens: 0";
  - for copies, labels the machine marker "Auto-generated from mission … [tracelab-auto-report:v2]" as "Custom Prompt";
  - puts Evidence citations above the report's own content;
  - lists sources as `collection 3f2a…`.
- **Project page:** the reports list shows `report_type` as each row's summary (`frontend/src/components/projects/ProjectResources.tsx:39-40`), and the project's Reports stat counts every report (`app/services/project_query_service.py:253`, `pages/projects/[id].tsx:273`).
- **Home:** the copies fill "Recent reports" and Recent activity (`app/adapters/repositories/sqlalchemy_home_repo.py:136-157`; `_reports` in the activity repository).
- **Evidence detail:** "Open report" leads to the copy (`pages/evidence/[id].tsx:30`, via `app/services/evidence_browser.py`).

Why the copies stay: the mission page renders results from `mission.result_markdown`, not from the copy, but the copy is still read by:
- the evidence graph (`app/services/pedr/edge_materialization.py`, `relational.py`);
- report citations;
- the evidence browser;
- the MCP.

**So copies are kept and moved out of view, never deleted.**

**Decisions made at plan time:**
- **Reports means written documents.**
  - The default view lists reports written by a person, an agent or the Librarian.
  - Agent evidence briefs and mission results each get their own filter.
  - A mission result links to its mission's Results tab with an explicit `?tab=results`, because REPORTS ships before MISSION.
  - The roughly 3 copies with no `result_report_id` are labelled "Mission results" with no link.
  - Mission completions already appear in Home's Recent activity as missions. The copy leaves Home's Recent activity and "Recent reports" (`sqlalchemy_home_repo.py`, the activity `_reports`). That changes MCP `tracelab_home` output, which the 2.2.0 tool description states.
- **The origin is stored, not guessed at read time.**
  - A new column, `reports.origin`, holds `mission | written | librarian | agent_brief`, with a server default of `written`.
  - Each creation path sets it explicitly, and a test per path asserts that it does:

    | Creation path | Origin |
    | --- | --- |
    | `auto_report` | mission |
    | report API and synthesis | written |
    | Librarian | librarian |
    | ledger promote | agent_brief |

  - A migration backfills existing rows using the rules behind the count above, applied in this order:
    1. Linked from `missions.result_report_id`, or the prompt starts with "Auto-generated from mission " → mission.
    2. `report_type = 'evidence-ledger'` → agent_brief.
    3. `generation_provenance` origin `librarian` → librarian.
    4. Everything else → written.
  - The revision id is 32 characters or fewer, and the migration is applied to real PostgreSQL, not only SQLite.
  - Every `Report(` constructor is covered: the four paths above, plus test builders, which take the default.
- **REST list.** It gains an optional, repeatable `origin` filter. The default stays "all", so existing agent callers are unaffected. The UI asks for the origins it wants.
- **Plain-language labels**, each with a link where one exists:
  - "Results of mission *title*";
  - "Written from collection *name*" or "Written from *n* excerpts";
  - "Written by the Librarian from *project*";
  - "Evidence brief from an agent's research session".
- **Reports list page:**
  - A source filter replaces draft/final: Reports (the default), Evidence briefs, Mission results. The project filter stays.
  - Rows show the label, the project and the date. They drop the type, the excerpt count and the token count.
  - A Final badge shows only on final reports.
- **Project page.** `ProjectResources` uses the same default origins and labels. The project's Reports stat counts the same default set.
- **Report detail page:**
  - The header holds the title, the origin line with its link, the project and the date, then Final, Export and Delete.
  - The report's content comes first; Evidence citations, source citations and source records follow.
  - Source records show the collection or document name as a link. Names are looked up on the server through `accessible_filter`. A source the user can't read shows as "Source unavailable", so nothing leaks. This is a nested schema change to `ReportSourceSchema`, and the OODS object model is updated with it.
  - The prompt shows as "Instructions" only on written and Librarian reports, never the auto-report marker.
  - The raw type, chunk and token fields are removed.
- **Evidence detail.** "Open report" for a mission result goes to the mission's Results tab.
- **MCP.**
  - `tracelab_report` `list` and `get` return `origin`, and `list` accepts an optional `origin` filter.
  - It gets a regression test through the MCP client.
  - The parity manifest classifies the new filter, and the parity audit exits 0.
  - The publish happens at the end of S67-BADGES.

**Done when:**
- The report count is the same before and after the migration: nothing is deleted.
- Production's origin counts match the count above, allowing for reports created since. The receipt records both.
- Neither the default Reports view nor the project page lists a mission copy. "Mission results" lists them, linked to `?tab=results`.
- For each origin, a browser test asserts that no report page shows "Tokens: 0", a raw type, the auto-report marker or a UUID stub.
- Each creation path has a test proving it sets `origin` explicitly.
- An MCP-client test proves `origin` is returned and filterable.

### S67-BADGES — Recency and seen-state, not counts

> "it's just an annoying badge at this point that says 99 plus forever … It's almost like a link … have we seen it? Have we not seen it?"

**Today:**
- An item stays "new" until the user opens it. There is no time window (`sqlalchemy_activity_repo.py` `summary()` :115-123, `_missions` :41-47, `_evidence` :57-79).
- The sidebar shows those counts for Missions, Evidence and Reports (`Navigation.tsx:72-83`, `NewBadge.tsx`).
- Viewed state lives in `user_item_views` (migration 049).
- `ActivityItem` carries only `new` (:77, :100, :104). On Home, an unviewed old item therefore looks the same as a viewed one.

**Decisions made at plan time:**
- **What "new" means.** An item is new when it is unviewed and happened within the last 3 days. The 3 days is a constant in the activity repository, not configuration. Older unviewed items are "unseen" rather than new. Viewed items read as seen, like a visited link.
- **The sidebar shows no counts.** `NewBadge` is deleted.
  - Missions shows a small dot when a mission **completed** in the last 3 days and hasn't been opened since. Its accessible name is "Missions, new results".
  - The dot is keyed on `completed_at`, which no later write moves. Blocked, cancelled and validation-failed missions still appear as new in Recent activity, but they don't raise the dot: their only timestamp is `updated_at`, and any later write would bring the dot back.
  - Evidence and Reports show no marker.
- **The summary API.**
  - `by_type` counts new items (unviewed, within 3 days).
  - An added `completed_missions_new` drives the dot.
  - The MCP `tracelab_home` tool description says so in 2.2.0 (`packages/tracelab-mcp/src/index.ts:727`, `api-client.ts:573`).
- **Seen-state comes from a separate read.** `MissionResponse` and `ReportListItem` stay unchanged, so the OODS model, the mission-authoring contract and both MCP serializers are untouched.
  - A new endpoint, `POST /activity/state`, takes `{items: [{type, id}]}` for missions and reports.
  - It returns `{type, id, viewed, new}`, checking that the caller can read each item.
  - The Missions and Reports lists call it for the page they show.
  - Each row:

    | State | Title | Marker |
    | --- | --- | --- |
    | unseen | semibold | none |
    | unseen and new | semibold | small dot |
    | seen | regular weight, secondary colour | none |

  - Evidence has no per-row state; its seen-state is per group.
- **Home.**
  - `ActivityItem` gains `viewed`, and Recent activity rows use the same three styles. This is additive to MCP `tracelab_home`.
  - The "New" pill and the "N new since you last looked" line use the 3-day window.
  - When no mission is in progress, Active missions is not rendered, and Recent activity spans the full width. The definition of an active run stays in-progress only.
- **MCP 2.2.0** ships at the end of this mission, carrying REPORTS' `origin` and this mission's activity changes. It is published under DoD-1 with Derek's browser approval.

**Tests that pin the old behaviour:**
- `tests/test_activity_api.py`, including `test_items_stay_new_until_viewed…` (:90);
- `tests/integration/test_home_postgres.py:25` (`new_total == 143`);
- `tests/integration/test_aggregate_perf_budgets.py:96`: the 75 ms budget for `activity_summary` still holds. Filter evidence groups by time in SQL.
- `AppShell.test.tsx:70`, `__tests__/home.test.tsx` and `__tests__/missions.test.tsx:82`;
- `tests/e2e/app-shell.spec.ts:48-62`;
- the specs that stub `/activity/summary`.

**Done when:**
- A fixed-clock backend test proves that an unviewed mission completed 4 days ago is neither counted nor dotted, one completed 1 day ago is both, and viewing it clears it. The test fails on the old repository.
- A browser test proves:
  - no numeric badge appears anywhere in the sidebar;
  - the Missions dot appears and clears;
  - Home and the Missions and Reports lists render seen, unseen and new rows differently;
  - Active missions is absent when nothing is running.
- Registry 2.2.0, installed fresh, passes the stdio suite, and its tarball is byte-identical to the tested pack.
- Production shows no number in the sidebar.

### S67-MISSION — A mission page that follows the mission's state

> "when I click on a mission, I want to see the results … right now I have to scroll down to the middle of the page … If I click the run button, that's an action button. It's not going to run it."

**Today:**
- The tabs are "Run", "Results" and "Evidence". The page always opens on "Run" unless `?tab=` is set (`frontend/src/pages/missions/[id].tsx:46-58, 345-353`).
- Tab clicks use `router.replace` (:57), so they add no browser history.
- On the Results tab, three things render above the results:
  - the back bar;
  - the header card, with all its actions;
  - `ScopeOutcomePanel` (:354), which appears on every tab for finished missions.

**Decisions made at plan time:**
- **The default tab follows the status.**
  - A completed mission opens on Results. Every other status opens on the first tab.
  - An explicit `?tab=` still wins.
  - Each status's default tab has a clean URL.
  - Tab clicks use `router.push`, so back and forward move between tabs.
- **The first tab is named for the state.** Its content doesn't change: objective, criteria, research plan, run activity and execution.

  | Status | First tab |
  | --- | --- |
  | draft | Plan |
  | queued, in_progress | Progress |
  | completed, blocked, cancelled, validation_failed | Details |

- **Results first.**
  - On the Results tab, the results begin directly under a compacted header.
  - `ScopeOutcomePanel` moves into Details. When the scope outcome is not clean, Results shows a one-line notice linking to it.
- **Draft and running states.**
  - A draft's header says "Ready to run", and Submit to DeepSearch is its primary button.
  - A running mission keeps its live run activity as the default view.
  - If a mission completes while its page is open, the page does not jump. A "Results ready" link appears in the header and opens Results.
- **Links stay valid.** Existing links to `/missions/{id}`, from NOTIFY emails, Home, the Librarian and the MCP, land on the status default. That is the intended change.

**Tests that pin the old behaviour:**
- `__tests__/missions.test.tsx:47`, the `it.each` over all seven statuses;
- `tests/e2e/mission-protocol.spec.ts:94`, covering `?tab=results`, the Run and Results labels, and the clean URL;
- `tests/e2e/authored-scope.spec.ts:62, 74`.

**Done when:**
- For a completed mission at 1440×900, the first line of its results is above the fold. A browser test asserts its bounding box.
- For each of the seven statuses, a test asserts the default tab and the first tab's label.
- A browser test proves back and forward restore the selected tab.
- A test proves the "Results ready" link appears on a live completion.
- On production, a real completed mission opens on its results.

### S67-QUALITY — Results say how far to trust them, and failures say why

**Source:** DeepSearch's request of 2026-10-13 (message `9706116c`), added to Sprint 67 at planning. DeepSearch's own run, S96, has been live since 2026-10-08. Every mission now carries quality and failure details that TraceLab receives but doesn't show. DeepSearch says no migration, API change or citation-schema change is needed.

**Where the data lives today:**
- **Quality:** `execution_metadata.quality_record`. An identical copy sits at `result_protocol.report_metadata.forensic.quality_record`. It is schema version 5, with `verification`, `evidence_dependencies`, `citation_surface` and `claim_assessment`.
- **Failures:**
  - `execution_metadata.synthesis_telemetry.provider_attempts[].failure.rejection`;
  - `.request_shape`;
  - `generation_recovery_result`.
- **What reads it:** only `components/missions/AuthoredScope.tsx:62`, which reads `delivery_quality` for the scope panel's warning. `ExecutionTimeline.tsx` reads the older forensic metrics.

**Change:**
1. **Quality line.** The Results tab shows one quality line under the header:
   - `delivery_quality` "clean" reads "No detected material issue", with a separate note: "Sampled verification; report-wide accuracy unknown".
   - `usable_with_warning`, `degraded` and `failed` are named plainly.
   - Legacy runs without the fields read "Quality not assessed for this run".
   - The page never shows an accuracy percentage built from source or sample counts.
2. **Actionable reasons** show as plain sentences under that line. Examples: `critique_unassessed_claims_N`, `missing_cited_sources_N`, `cited_without_readable_body_N`. Operational retrieval counts and bibliography accounting go in an expandable "Raw quality data" section on the Details tab.
3. **Failed runs** show:
   - the rejection subtype: `context_limit`, `unsupported_parameter`, `unsupported_value`, `content_rejection`, `invalid_json`, `invalid_message_structure` or `unknown`;
   - its `subtype_source`;
   - whether the request shape was available.

   They distinguish `provider_failed`, a second provider failure during the one retained-memory finalization, from `unknown_finish`, a response with no proven finish reason. Existing `error_message` sanitisation is unchanged.
4. **Unknown reason strings and subtypes** render generically and never drop the report or hide the raw data.

**Decisions made at plan time:**
- **Build from TraceLab's own data.** DeepSearch's contract (`docs/s96_quality_and_diagnostics_contract.md`) and fixtures (`tests/fixtures/s96_consumer_contract.json`) live in its repository. Reading another repository needs Derek's permission (constraint c:10). So the build uses two sources:
  - the field list in DeepSearch's message;
  - the real production mission S96-MEMORY-ACCEPT-02, which carries `critique_unassessed_claims_3` and is read through TraceLab's own API.

  It writes four TraceLab test fixtures mirroring DeepSearch's four cases: a supported sample, a missing cited body, legacy uncertainty, and a failed retained-memory request. If a field's exact shape can't be established that way, ask Derek for read access to those two files.
- **Check the API passes the fields through.** First, confirm that `MissionResponse` and the frontend types really carry these fields. If any are dropped, adding them is a contract change under the MCP and OODS guards.

**Done when:**
- Unit tests render all four fixture cases, plus an unknown-reason case and an unknown-subtype case.
- No rendered state shows a percentage.
- On production, S96-MEMORY-ACCEPT-02 shows its quality line and its unassessed-claims reason.
- DeepSearch's message gets a reply with the result.

### S67-LIBRARIAN — Conversation first, tools in a chooser

> "all of these are possible use cases, but kind of laying them all out like this is just kind of overwhelming … each of these should be a sort of route or path unto themselves … maybe it's a dropdown menu."

**Today**, `/librarian?project=X` (`frontend/src/pages/librarian.tsx`) stacks these, top to bottom:
1. the header and intro;
2. the three-step strip, the only dismissible help;
3. the project panel, with a select, an inline new-project form and SpacePicker;
4. four full tool cards, all at once: Describe, Review duplicates, Organise, Report from (:545-550);
5. the conversation, with mode radios.

The composer starts far down the page.

**Decisions made at plan time:**
- **Conversation first.**
  - With a project chosen, the page opens on the transcript and composer.
  - A compact scope line sits under the header: "About: *project* ▾" changes it, and "New project" is an action.
  - With no project, which is the sidebar's `/librarian`, the page shows the same conversation with "No project chosen ▾", and the tool chooser stays hidden until a project is chosen.
  - The three-step strip is removed from the Librarian, and the intro becomes one sentence. The stored dismissal setting stays, because it also hides the draft notice on the mission page.
  - The Talk, Ask the documents and List chunks modes become a compact segmented control beside the composer.
- **"More with this project" is one chooser** holding the four tools, each with a one-line plain description:

  | Tool | Description |
  | --- | --- |
  | Describe this project | Draft or update its description; you review every change |
  | Find duplicates | Review documents that look like copies |
  | Suggest collections | Group documents into collections |
  | Write a report | A cited report from this project's documents |

  - Choosing one opens only that panel, in place of the conversation, with a "Back to conversation" control.
  - The choice is in the URL (`?tool=describe|duplicates|collections|report`), linkable, and the browser's back button works.
  - The transcript and each panel's stored review state survive a trip into a tool and back.
- **Entry points.**
  - The project page's "Ask the Librarian" opens the conversation.
  - "Review description and its drafting history" (`pages/projects/[id].tsx:211`) opens `?tool=describe`.
  - `/librarian?q=` and `?saved=`, from the command palette (`CommandPalette.tsx:91, 94`), saved searches (`saved-searches.tsx:46`) and the `/search` redirect, still land in list mode.
  - Plan a mission (`?intent=mission`) is unchanged, as Derek asked.

**Tests that pin the old layout:**
- `src/__tests__/librarian.test.tsx`, including the steps test at :249;
- the four `librarian-*.test.tsx` files;
- `tests/e2e/librarian-{description,duplicates,collections,reports}.spec.ts`, which open `/librarian?project=project`. They move to `?tool=`;
- `tests/e2e/search-command.spec.ts`.

**Done when:**
- With a project chosen, the composer is visible without scrolling at 1440×900 and at 390.
- No tool panel renders until one is chosen, and only one renders at a time.
- From a project page, each tool takes "Ask the Librarian" plus one chooser choice. Each tool also opens directly from its `?tool=` URL, and the four tool specs pass that way.
- A test proves the transcript survives a round trip into a tool and back.
- `?q=`, `?saved=` and Plan a mission behave as before.

### S67-CLAIMS — Claims read as sentences (closes #406)

**Today:**
- DeepSearch evidence stores the exact cited span as the claim (`app/services/evidence_ledger.py:474`), so a citation inside a Markdown table stores a raw row such as `| … | … |`.
- Nothing cleans it before display. It shows verbatim in:
  - evidence cards (`components/evidence/EntryCard.tsx:12`);
  - the mission Evidence panel (`EvidencePanel.tsx:17`);
  - the evidence detail heading (`pages/evidence/[id].tsx:30`);
  - graph node titles (`sqlalchemy_graph_neighborhood_repo.py:133, 138`);
  - command-palette results (`sqlalchemy_navigation_search_repo.py:29`);
  - evidence-brief reports (`_render_markdown`, `evidence_ledger.py:692`), where a pipe row also turns the claim line into a table.

**Decisions made at plan time:**
- **The stored claim stays exact.** The exact-span check (`evidence_ledger.py:228`), the idempotency keys (:387, :605) and search all depend on it, and exactness is the provenance.
- **Display cleans it**, with one function per side: `displayClaim()` in `frontend/src/lib/api/evidence.ts` and `display_claim()` in `app/services/`.
  - Each table row has its leading and trailing pipes stripped, and its separator cells (`---`) dropped.
  - The remaining cells are trimmed and joined with " · ".
  - A multi-row claim's rows are cleaned the same way and joined with "; ".
  - Text that isn't a table row passes through unchanged.
- **Every surface above uses it.** The REST and MCP `claim` field stays raw, so agents keep the exact span. Nothing is asked of DeepSearch.

**Done when:**
- Unit tests on both sides cover at least ten real table-row claims pulled read-only from production as fixtures, including at least one multi-row claim. They also cover non-table claims that must pass through unchanged.
- In the rendered HTML of an evidence brief built from a table-row claim, the claim produces no `<table>`, and the claim line reads "a · b".
- On production, the evidence card for a known table-row claim reads as a sentence.

### S67-WALK — The share-out path, on production

**Steps.** On the final Sprint 67 production build, walk the invited-member path end to end:
1. An admin generates an invite code.
2. A dedicated temporary test account signs up with it. Its credentials stay private, outside the repository, as in WALK-3 (decision #559).
3. Home's empty state, then a new project.
4. The Librarian conversation drafts a mission.
5. The mission is submitted and runs on DeepSearch. Derek approved paid runs as needed (decision #628).
6. It opens on its Results.
7. Its Evidence and its Reports entry under "Mission results".
8. The mission-complete email arrives.
9. The new member cannot see anyone else's projects.

Production smoke and the public repository page (README, license, security policy) are checked too.

**Fixes and cleanup:**
- Every defect found is fixed in this sprint, or put in front of Derek by name before the share-out.
- Afterward, the test account is disabled and its invite revoked.

**Done when:** the receipt holds:
- the walk's captures at 1440 and 390, in both themes;
- the run's identity and duration;
- a disposition for every defect found.

**Out of Sprint 67:**
- text-message notifications (the email switch already exists);
- changes to Plan a mission;
- project sharing;
- the Reasonbook folder move (Sprint 68);
- any change in the DeepSearch repository.

**Critic pass (2026-10-13):** an independent critic returned NEEDS-REVISION with five blocking findings, all fixed above:
1. contract guards for the seen-state change;
2. the project page's report list and its Reports stat;
3. Home's unseen state and a check that passed without any change;
4. the project page's description link;
5. a back/forward check that `router.replace` made impossible.

Its minor findings are folded in too: the default view, Home's MCP output, evidence links, source-name access, the origin default, the dot timestamp, `.panel` padding, the CI list wording, multi-row claims, one MCP publish, live completion, and the Librarian's no-project state.

## Monday 2026-10-19 — the share-out

## Sprint 68 — After the share-out (planned shell)

- **S68-RB4: move the record to Reasonbook 4.0's folder** (messages `960040b8` and `9c5b4fc2`).
  - Follow Reasonbook's migration guide: run `migrate --docs-only`, then preview `migrate --project`, then apply `migrate --apply` only while no other session holds the record. Never stop another session's process.
  - The same change updates every reference outside `app/`:
    - `tests/conftest.py:71`, which loads `cmos/scripts/pytest_telemetry_plugin.py`;
    - `tests/test_content_hash_dedup.py:22,84` and `tests/test_decision_insight_linking.py:24`, which import `cmos.context`;
    - `tests/unit/test_oods_object_contract.py:14,71` and `tests/unit/test_validate_foundational_refs.py:45-85`;
    - `scripts/evaluate_sprint_03.py:24`, which the Sprint 3 tests use;
    - `frontend/playwright.config.ts:9`, the reporter;
    - `frontend/src/lib/route-migrations.test.ts:9`;
    - `scripts/mcp_parity_audit.mjs:184`;
    - `scripts/rag_baseline_benchmark.py:94-112`, which `tests/unit/test_benchmark_corpus.py` reads;
    - the agent rules.

    This list is a starting point. The mission is done when `git grep cmos/` finds only historical text kept on purpose.
  - Record counts must match before and after, and CI must stay green.
- What people hit at the share-out.
- Recheck the two build-tool advisories carried from S66-SECURITY: `braces` GHSA-vfj7-8cjw-p6xm has no published patch as of 2026-10-13; selector-parser GHSA-rj75-hqrm-r3gf is fixed in 7.1.6, outside Tailwind 3/typography's declared 6.x ranges. Prefer upstream compatible fixes; otherwise scope a deliberate toolchain migration with OODS compatibility and theme/browser verification. Revisit sooner if a feature would parse user-controlled CSS or glob patterns. The security receipt preserves the nonzero audit counts and dependency paths.
- DeepSearch's opening, if it is not done by Monday. That work is owned by DeepSearch, as are the quality follow-ups named at the Sprint 64 and 65 closes.

---

## Carry-forward dispositions (Sprint 66 planning, 2026-10-13)

| Row | What it was | Disposition |
| --- | --- | --- |
| #174 | Documented `expected_output_schema` example cannot satisfy the compiler | S66-MCP |
| #275 | Settings labels wrap per character at 390 px | S66-SETTINGS |
| #280 | Settings times shift outside UTC | S66-SETTINGS |
| #290 | 38 of 67 active decisions carry no sprint tag, so age-based review skips them | Closed: record hygiene with no reader waiting on it |
| #307 | Argument-level MCP parity check | Done: `scripts/mcp_argument_parity.mjs` (MCP-4, PR #333) runs in the required mcp-package lane (`.github/workflows/mcp-package.yml:30-32`) |
| #375 | Tighten the aggregate performance budgets | Closed: deliberately loose budgets that pass; no regression to answer |
| #376 | Member-scoped aggregates not budgeted | Closed: a fixture refinement with no observed problem behind it |
| #378 | Performance table printed only on failure | Closed with #375 |
| #379 | Absolute timing thresholds fail under load | S66-TESTS |
| #380 | Test suite dirties tracked files | S66-DECOUPLE |
| #400 | Scope project-level sharing (SHARE-1) | Closed: sharing is deferred by Derek (decisions #526, #538); see Open Question 5 |
| #403 | Put the per-project grants question to Derek | Closed: it is Open Question 5 |
| #406 | Raw Markdown table rows as claim text | Sprint 67 (S67-CLAIMS) |
| #407 | Start sharing from report TRACE-SHARE-58 | Closed: pointer kept in Open Question 5 |
| #415 | Price table for a usage policy | Closed: usage records keep tokens and model; prices apply only when a policy is wanted |
| #422 | 1.2% of evidence comes from foreign-language sources | Closed: not a defect, and no filter was asked for |
| #431 | Child rows' Space column drifts from their project's | Closed: authorization resolves every child through its project (`app/core/authorization.py:78-83`) and ignores the child column; no resync |
| #448 | Theme-bootstrap tests fail under `next dev` | S66-TESTS |
| #452 | Master-context size watch | Done: 57 KB of 100 KB, below the 75% warning |
| #454 | Aquex hub pinned MCP 1.1.1 | Done: the hub launches 2.1.0 (checked 2026-10-13) |
| #477 | Older Aquex app connector's SSE 404 | Closed: it belongs to Aquex's connector; TraceLab's MCP paths work |
| #485 | Nine Playwright specs never run in CI | S66-TESTS |
| #486 | MCP README install pin | S66-MCP |
| #487 | Sprint-planning start state | Done by this planning session: parts 1 and 2 here, part 3 handed to S66-DECOUPLE and S68-RB4 |

---

## Open Questions for Derek

Add to this list rather than resolving items silently. Questions 1–4 were answered on 2026-10-13.

1. **Which license?** *Answered: MIT* (decision #613). Derek: "good with MIT unless you feel AGPL is better? i don't have a strong opinion open to your recommendation". The recommendation stayed MIT. DeepSearch and the compiler TraceLab vendors from it take the same license. Both vendored Forge packages, `@oods/tokens` and `@oods/tw-variants`, keep PolyForm Noncommercial unless Derek relicenses them.
2. **Other people's personal data in history.** *Answered: clean the current tree and leave history* (decision #614). Derek was open to the recommendation. The data is three people's emails, names and roles, plus admin-users screenshots: low sensitivity, but not Derek's. A purge would change every commit hash the record cites, needs GitHub Support, and cannot reach the 1,350 clones already made in the 14 days to 2026-10-13. The repository has 0 forks.
3. **Cross-project messages.** *Answered:* "yes you can message as needed to any project" (decision #614; it replaces constraint c:7's ban on messages, while working in another repository still needs permission). DeepSearch was asked to prepare its repository for opening (message `51ad080b`), and Reasonbook's rename request `960040b8` was accepted with this plan.
4. **Who comes in on Monday, and how?** *Answered:* an invite-only demo. Derek will send 5–10 invite codes to people he wants to see the app and how it works. Sign-up stays as it is (decision #614).
5. **Carried from the predecessor document (deferred):** should project grants be genuinely per-project, or sugar over Space membership? Revisit when Derek wants sharing. Start from report TRACE-SHARE-58 (document `04ffc800-85cf-4a49-bcec-a856644796a8`), which recommends a hybrid project-bounded model.

---

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| The scan finds a live credential days before the share-out | EXPOSURE runs right after DEPS. Rotation is Derek's call, and receipts name the credential without its value |
| A receipt or scan log republishes what it found | `--redact` everywhere; raw output stays outside the repository; receipts hold redacted findings only |
| A revived browser spec finds a real regression | It is fixed or reported as a defect, never deleted to make CI green (decision #498: a gate that never runs is not evidence) |
| Moving a telemetry writer silently changes an admin view | Only writers under `cmos/` move. The admin-dashboard data in root `telemetry/` is untouched, and no `app/` code reads the moved files |
| Upstream releases break the build again | Learning #302: compare the last green run's installed versions with the failing run's; if it recurs, adopt a constraints file |
| The 2.1.3 publish waits on Derek | Last in order; the README fix is low-stakes, and #174 stands on its own evidence before publication |
| Eight missions in about two days after the approved security addition | DEPS, EXPOSURE and SETTINGS run first. Any later mission that slips moves to Sprint 68; unresolved actionable security findings are surfaced before the share-out |

---

## Change Log

- **2026-10-14 UTC, Sprint 67 opened for a fresh build session.** Derek approved the scope (decision #627) and paid DeepSearch runs as needed (decision #628): "yes, we can run as many paid deepseek runs as needed, all approved." The identity was synchronised to `sprint-67-active`. S67-DENSITY reads In Progress from planning: a promotion to Current started it instead (learning #311). Its notes record that no build work has begun. Build in roadmap order. The record's work queue lists missions alphabetically. S67-QUALITY was added from DeepSearch's request for the mission page to show its quality and failure details (message `9706116c`).

- **2026-10-13 UTC, Sprint 67 planned from Derek's UX feedback.** Seven missions, in order: DENSITY, REPORTS, BADGES, MISSION, LIBRARIAN, CLAIMS and WALK. Derek's answers: a dot on Missions only; "new" lasts 3 days; the Librarian is conversation-first, with tools in a chooser; Reports is cleaned up now. His last answer overrode a proposed deferral ("STOP DEFERRING"). A read-only production count found 451 of 512 reports are automatic copies of mission results. An independent critic returned NEEDS-REVISION with five blocking findings, all fixed before the plan was recorded.

- **2026-10-13 UTC, Sprint 66 closed (eight of eight).** The section above is rewritten as outcome. Every mission is merged, deployed and verified on production; `main` and both services serve `7204961` with all main workflows and Production Smoke green. Eight carried follow-ups closed; #406 and #489 go to Sprint 67, #490 to Sprint 68. Two post-merge proofs that lived only in temporary files are now committed receipts: the MCP 2.1.3 registry verification and the S66-SECURITY live production check. Sprint 67 is scoped next from Derek's UX feedback.

- **2026-10-13 UTC, runtime storage isolation validated locally.** The identical CI backend run previously changed six tracked files; after S66-DECOUPLE it leaves the checkout clean, with no new skips or quarantines. Coverage HTTP payloads are unchanged apart from generation time. S66-SECURITY is also merged as `381a3aa`, verified live at Next 16.3.8/sharp 0.35.5, with every main workflow and all five production smoke checks green.

- **2026-10-13 UTC, frontend security update validated locally.** Selected patched runtime and test-tooling versions; all existing local gates pass. Decision #619 records the two remaining build-only advisory dispositions and a bounded Sprint 68 follow-up. The npm audit remains nonzero; no findings are suppressed.
- **2026-10-13 UTC, clean-install security findings added to Sprint 66.** Derek approved S66-SECURITY immediately after FRONT and before DECOUPLE, TESTS and MCP (decision #618). The clean install found 37 frontend dependency advisories, including critical Next.js and test-tooling findings. Version applicability was checked against maintainer advisories; exploitability on TraceLab was not established. FRONT's quickstart now explicitly isolates Compose containers and volumes, following an initial attempt that reused and migrated an existing local database (decision #617). The second clone passed from empty volumes through UI login and API health.
- **2026-10-13 UTC, Derek's answers; Sprint 66 opened.**
  - Answers: merge (PR #416 merged as `7ee7c8c`); license MIT (decision #613, correcting #612's stored approval words); history kept, current tree cleaned; messages to any project allowed; Monday is an invite-only demo for 5–10 people (decision #614).
  - S66-DEPS started and opened the sprint, and the identity was synchronised to `sprint-66-active`.
  - **S66-DEPS completed.** All 8 main runs on `7ee7c8c` passed: Backend Tests 3,160 passed / 4 skipped / 12 standing deselections, and the Post-Deploy Check, smoke included. Both Railway services serve `7ee7c8c`, and the live container reports pydantic 2.13.5. [Receipt](../reports/sprint-66/S66-DEPS/validation.json).
  - SETTINGS moved ahead of FRONT, because Monday is an app demo.
  - Sprint 67 will be scoped from Derek's UX doc at the next planning session.
- **2026-10-13 UTC, created at Sprint 66 planning (session PS-2026-10-13-003).** Derek: "lets open a planning session and get sprint planning underway … make sure we're in good shape for next Mondays share out … lets get these carry forward and remaining items put to bed first."
  - All 24 open follow-ups are dispositioned: 8 into Sprint 66 missions, 1 to Sprint 67, 4 done and 11 closed with reasons.
  - Sprint 66 is drafted as seven missions.
  - Planning found that backend CI is red because of an upstream pydantic release (PR #416). It also found third-party personal data and two noncommercially licensed vendored packages in the public tree.
  - An independent critic returned NEEDS-REVISION twice. The first pass had four blocking findings; the second found that `@oods/tw-variants` is noncommercial too. Both are resolved, and the third pass approved.
