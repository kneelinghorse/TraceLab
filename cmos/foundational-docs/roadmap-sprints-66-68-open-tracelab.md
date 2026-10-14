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

## Sprint 67 — The UX pass (opened and closed 2026-10-14 UTC, eight of eight)

**Outcome:** all eight missions shipped in the planned order before the October 19 share-out. Each mission passed its local checks, required PR checks, normal squash merge, both Railway deployments, production smoke and live acceptance before the next mission started. No new environment variable or setting was introduced. The final walkthrough fixes shipped in PR #436 (`b3d09ea`); the sprint record and receipt corrections are in a separate closeout PR.

The accepted experience is denser, Reports defaults to written documents, recency uses seen-state, completed missions open on Results, quality warnings remain visible, the Librarian starts with conversation, and evidence labels are readable without rewriting citations. The final acceptance run also delivered its completion email and proved member isolation.

**Final measured checks:** 3,212 backend tests passed, with four existing external-service skips and 12 documented quarantines; 172 PostgreSQL integration tests passed, with three existing opt-in/environment skips; 451 frontend unit tests and 218 browser cases passed. Frontend types, lint, token contrast, production build, foundational references and the MCP parity audit passed. The MCP remains nine tools / 50 actions, covering 119 classified UI operations. Historical per-mission counts in the receipts describe those earlier commits; the closeout receipt identifies the final measured runs.

### S67-DENSITY — Tighter, data-platform spacing

Shipped in [PR #427](https://github.com/kneelinghorse/TraceLab/pull/427), merge `71c95cc`. Nine pages share the page header and container. Body text stays 16 px, small text is at least 14 px within the shared container, and contrast tokens and the global panel class are preserved. On the fixed 1440×900 fixture, the first content row moved up 56–136 px across all nine pages; Home showed five complete activity rows instead of two. Desktop/phone, light/dark captures and production checks passed. [Receipt](../reports/sprint-67/S67-DENSITY/release-receipt.json).

### S67-REPORTS — Reports holds documents, not a copy of every mission

Shipped in [PR #428](https://github.com/kneelinghorse/TraceLab/pull/428), merge `9ffdfe5`. Every report has a stored origin: written, librarian, agent brief or mission. The default list, Home and project report views omit mission copies and agent briefs; both remain available through explicit filters. At acceptance, all 512 rows were retained: 47 written, two Librarian, 12 briefs and 451 mission copies; the default list contained 49 documents. Source labels respect current read access and mission copies link to mission Results. PostgreSQL migration, UI and actual installed MCP checks passed. [Receipt](../reports/sprint-67/S67-REPORTS/release-receipt.json).

### S67-BADGES — Recency and seen-state, not counts

Shipped in [PR #429](https://github.com/kneelinghorse/TraceLab/pull/429), merge `5a7a69f`. The sidebar shows a Missions dot for unseen completions within three days. Lists use recent/unseen states and reading clears the applicable watermark. The separate activity-state read exposes only readable IDs, including retained mission-copy reports, without mutating seen-state. Existing mission/report response contracts remain intact.

`@aquex/tracelab-mcp` **2.2.0** was published after Derek's npm browser approval. An empty-directory, empty-cache registry install passed 71 stdio checks, generated 73 links and made 72 checked HTTP requests; the downloaded tarball was byte-identical to the tested tarball. [Release receipt](../reports/sprint-67/S67-BADGES/release-receipt.json) and [registry proof](../reports/sprint-67/S67-BADGES/registry-verification.json).

### S67-MISSION — A mission page that follows the mission's state

Shipped in [PR #430](https://github.com/kneelinghorse/TraceLab/pull/430), merge `70fe74e`. Drafts open on Plan, queued/running missions on Progress, and completed missions on Results; other statuses open on Details. Explicit tab links, browser history, keyboard navigation and live completion preserve the person's selection. The final implementation reconciles browser navigation from the current URL so a late shallow-route completion cannot undo a newer selection. Production Results began at 607 px on desktop and 893 px on phone in the recorded fixture. [Receipt](../reports/sprint-67/S67-MISSION/release-receipt.json).

### S67-QUALITY — Results say how far to trust them, and failures say why

Shipped in [PR #431](https://github.com/kneelinghorse/TraceLab/pull/431), merge `6a82386`. Results display delivery, verification and scope warnings without inventing accuracy; Details preserves raw quality and failure objects, and actionable failure notices remain visible. The schema/version guards and recovery details use DeepSearch's consumer contract, read with Derek's explicit permission, and TraceLab's real deployed payload. The requested consumer reply was sent after verification. The final walkthrough exercised a degraded result and correctly exposed one contradicted sampled claim, two unassessed claims and unknown report-wide accuracy. [Receipt](../reports/sprint-67/S67-QUALITY/release-receipt.json).

### S67-LIBRARIAN — Conversation first, tools in a chooser

Shipped in [PR #432](https://github.com/kneelinghorse/TraceLab/pull/432), merge `63b71e2`. Project tools live in a chooser, one at a time, while the conversation stays available and retained review state survives switching tools. General project controls/examples are collapsed; the focused mission-planning flow is preserved. Keyboard/history checks, 56 local captures and 28 production captures passed. In the accepted live view, the composer ended at 457 px on desktop and 533 px on phone. [Receipt](../reports/sprint-67/S67-LIBRARIAN/release-receipt.json).

### S67-CLAIMS — Claims read as sentences (closed the carried claim-formatting follow-up)

Shipped through [PR #433](https://github.com/kneelinghorse/TraceLab/pull/433), [#434](https://github.com/kneelinghorse/TraceLab/pull/434) and [#435](https://github.com/kneelinghorse/TraceLab/pull/435); final merge `707b08b`. UI labels, graph nodes and navigation titles clean complete/partial Markdown table rows and join consecutive rows while preserving surrounding prose. Stored claims, snippets, raw REST/MCP fields and SQL matching/order remain exact.

The first deployment exposed Railway's frontend-only build root: a shared fixture outside that subtree could not resolve. The fixture moved unchanged into `frontend/tests/fixtures/`, and an isolated frontend-only build plus full gates passed. A verification follow-up corrected the harness's document page-size limit and an existing asynchronous focus assertion. Sixteen final live captures and 13 checks through installed published MCP 2.2.0 passed, including 11 byte-exact raw claims. The carried claim-formatting follow-up is completed. [Final acceptance](../reports/sprint-67/S67-CLAIMS/production-final/completion.json).

### S67-WALK — The share-out path, on production

A temporary invited **member**, using real browser authentication, signed up, saw empty Home, created a project, conversed with the Librarian, reviewed and saved its draft, and submitted one approved paid DeepSearch run. Mission `S67-KBD-FOCUS` (`a9526db2-ece6-4655-9d17-6991b12c49c7`) completed in **204.749 seconds**, with 113 visible evidence entries and a mission-result report. Results opened by default, the Evidence tab worked, and the report's Mission results entry returned to Results. The completion email was received at 08:58:16 UTC with the correct mission link and title. The member listed only its own project; foreign-project and admin access returned 403.

The walkthrough found and fixed two defects in [PR #436](https://github.com/kneelinghorse/TraceLab/pull/436): signup's obsolete Mission Protocol wording, and a member Settings button for admin-only invite creation. The existing server policy was correct; Settings now uses the live role context and the public README explains admin invite creation. Both fixes were checked on the deployed merge in light/dark at 1440/390 px. The public repository, README, MIT license and security policy were rendered successfully.

Cleanup disabled the temporary account and verified denial for both its existing token and a fresh login. Signup had already consumed the single-use invite; a reuse attempt was rejected. The used invite's audit row is retained because the revoke API intentionally deletes only unused codes. This satisfies the cleanup's access-removal intent without deleting audit history (decision #638). [Walk receipt](../reports/sprint-67/S67-WALK/release-receipt.json).

**Carry-forward:** the existing Sprint 68 build-tool advisory maintenance and one cosmetic Reports count-label follow-up remain open. The final capture says “1 mission results”; this was explicitly disclosed to Derek and does not affect filtering, navigation or access. The Reasonbook folder migration and share-out feedback remain in Sprint 68. Text messages, project sharing and DeepSearch repository changes stayed outside Sprint 67. DeepSearch was read only with permission; its repository was not changed.

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

- **2026-10-14 UTC, Sprint 67 closeout released.** The closeout PR #437 merged as `e921de2`. Both Railway services serve it, and all eight main workflows and two later Production Smoke runs are green on it. Its [release receipt](../reports/sprint-67/closeout/release-receipt.json) was committed after the squash-merge, so it never reached main (learning #303). It lands unchanged in a follow-up PR.

- **2026-10-14 UTC, Sprint 67 closed (eight of eight).** All missions merged, deployed and verified in order; final WALK merge `b3d09ea` serves on both Railway services with Post-Deploy Check green. The real invited-member run, received email, isolation and disabled-account/consumed-invite checks passed. MCP 2.2.0 was published and verified from an empty registry install after Derek’s approval. Final measured gates: 3,212 backend / 172 PostgreSQL / 451 frontend unit / 218 browser passes, with existing backend/PG skips and quarantines explicit. Claims fixture references are corrected at close; the claim-formatting carry-forward is completed. Two named follow-ups remain for Sprint 68: build-tool maintenance and the disclosed cosmetic single-result count wording.

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
