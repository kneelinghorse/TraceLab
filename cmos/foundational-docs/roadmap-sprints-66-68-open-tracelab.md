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

## Sprint 66 — Clear the deck (opened 2026-10-13; target close 2026-10-15)

**Goal:** every carried follow-up is done, scheduled or closed with a reason, and TraceLab's public repository is clean, licensed and ready to be read and run.

Opened when S66-DEPS started on Derek's "yes, merge" (decision #614). PR #416 merged as `7ee7c8c`.

**Order:** DEPS → EXPOSURE → SETTINGS → FRONT → DECOUPLE → TESTS → MCP. The share-out is an invite-only demo of the hosted app (decision #614), so the user-visible SETTINGS fixes run before the repository's front door. Requires edges:
- every mission requires DEPS, because nothing merges while backend CI is red;
- FRONT requires EXPOSURE to merge, so visitors aren't invited into a tree that still holds other people's data. It can be drafted in parallel;
- TESTS requires DECOUPLE and SETTINGS, because they share test files and the CI spec list.

Each mission is merged, deployed and verified on production before the next starts, and it closes the follow-ups named in it.

### S66-DEPS — Restore the backend build

**Objective:** backend CI passes again on fresh installs, and the next production image installs a pydantic that mcp 1.6.0 can import.

- `pyproject.toml` caps pydantic below 2.14 (PR #416). Reproduced in a clean venv: mcp 1.6.0 with pydantic 2.14.1 fails to import `mcp.server`, and with 2.13.5 it imports. fastapi (0.142.2 → 0.143.0) and starlette (1.7.0 → 1.8.0) also moved since the last green run. They stay floating unless CI fails on them.

**Done when:** backend-suite and backend-integration pass on PR #416; after merge, the post-deploy check is green; and `railway ssh --service TraceLab -- python3 -c "import pydantic; print(pydantic.VERSION)"` reports 2.13.x.

### S66-EXPOSURE — Know what the public repository exposes, and remove what it shouldn't

**Objective:** establish, reproducibly, whether TraceLab's public history holds any credential or third-party personal data, get every live credential in front of Derek, and remove personal data from the current tree before the share-out.

*Credentials:*

- Scan full history on every ref and the working tree with gitleaks (record the version), **always with `--redact`**, and run `scripts/check_no_credential_literals.py` on tracked files.
- `git log -p` shows binary files only as "differ", so list every binary blob in history: the WAL/SHM revisions, the backup database and any others. Extract their text with `sqlite3 .dump` where it opens, otherwise `strings`, and pipe it through `gitleaks stdin --redact`.
- Raw scanner output stays outside the repository. Receipts carry only redacted findings and their dispositions.
- Each finding is a false positive (say why), a dead or test credential, or possibly live. "Dead" is shown from the record: rotation evidence, or a known fixture. **A found credential is never used to test it.** Anything not provably dead is reported to Derek by name and location, never value. Rotation is his call.
- Cite GitHub's own secret scanning (on, push protection on, no alerts) as a second source, not a substitute.

*Personal data:*

- Inventory email addresses and names across tracked text, the extracted binary text, and screenshots of user, admin, settings, invite and auth pages. Use OCR, and send its text through the same redaction rule.
- Remove third-party personal data **from the current tree**.
  - Redact the three JSON receipts in place, keeping their structure and replacing each third-party address and display name with a stable placeholder.
  - Mask the user-list screenshots rather than delete them, because 31 `results.json` receipts reference them by path.
- The production `AUTH_USERNAME` appears in 17 tracked files (13 receipts, 2 docs, 2 tests). It is a username, not a secret, so don't redact it file by file. Instead, work out from the code and the names of Railway's variables (never their values, and never by attempting a login) whether the legacy username/password login it belongs to is still reachable in production. If it is, report that to Derek.
- **History is not rewritten** (decision #614). A live credential found in history is rotated, not purged.
- Prevent recurrence.
  - The capture script `frontend/scripts/ui-shell-smoke.mjs:70` masks only `code` elements on /settings today. It also masks email cells on admin user pages.
  - Inside the required Secret Scan job (`.github/workflows/secret-scan.yml`), a check fails when a tracked receipt contains an email address outside an allowlist of owner and example domains, proven with a fixture. A separate new check would not block merges until branch protection requires it.
- `cmos/db/cmos.sqlite.backup-20251112-162503` leaves the tree after it is scanned.

**Done when:**
- The receipt in `cmos/reports/sprint-66/S66-EXPOSURE/` records tool versions, commands, refs, blob counts and finding counts, with a disposition for each finding and no secret value or third-party address anywhere in it.
- Every credential not provably dead has been reported to Derek.
- A grep of the tree for the three third-party domains and display names returns nothing.
- An OCR re-check of every `*_admin_users.png` after masking finds no email address.
- The new CI check fails on its fixture and passes on the tree.
- The backup file is gone.

### S66-SETTINGS — Times are local everywhere, and Settings fits a phone

Closes #280 and #275.

- `frontend/src/pages/settings.tsx:380`, `:384` and `:528` parse offset-free UTC API times with `new Date()`. So API-key "Created" and "Last used" times, and invite dates, shift for anyone outside UTC.
- The same pattern appears at:
  - `components/evidence/EntryCard.tsx:9`
  - `components/librarian/CollectionSuggestions.tsx:156`
  - `components/librarian/DuplicateReview.tsx:89`
  - `components/librarian/ProjectDescription.tsx:106`
  - `components/queue/QueueCard.tsx:52` and `:116`
  - `components/queue/ExecutionProgress.tsx:8`, where durations are off by the UTC offset
  - `components/console/CorrectionStatusCard.tsx:36` and `:177`
  - `pages/admin/corrections.tsx:135`, `:258` and `:306`
  - `pages/device.tsx:240`

  Every one that parses an API time goes through `parseApiTimestamp` (`frontend/src/lib/api/timestamps.ts:2`). `pages/index.tsx:21` and `pages/admin/observability.tsx:15` already add a missing offset themselves. Switch them to `parseApiTimestamp` too, so the grep below has no exceptions.
- At 390 px, the Revoke, Copy and Delete actions and the "unused" badge wrap one character per line (`cmos/reports/sprint-51/ux-10-production-smoke/dark-390-_invites.png`). Fix the row layout and check it with a realistic long key name.

**Done when:**
- A grep for `new Date(` over `frontend/src`, recorded in the receipt, shows no API time parsed outside `parseApiTimestamp`.
- A browser test with a fixed clock in America/Chicago fails on the old Settings parsing, passes on the new, and is in the enumerated CI list.
- Captures at 390 px in both themes show whole-word labels, no horizontal overflow and no serious or critical axe findings.
- A read-only check on production confirms them.

### S66-FRONT — The repository's front door

*Requires EXPOSURE to merge. It may be drafted in parallel on a branch; the record notes the dependency but does not enforce it.*

**Objective:** a person landing on github.com/kneelinghorse/TraceLab on 2026-10-19 can tell what TraceLab is, knows how they may use it, knows how to report a vulnerability, and can run it by following the README from a fresh clone.

- **`LICENSE`** at the root: MIT (decision #613). `packages/tracelab-mcp` keeps MIT. The vendored DeepSearch compiler (`app/services/contract_compiler/`) is Derek's code and takes the same license as DeepSearch's repository. A `NOTICE` (or a README section) names every vendored component under another license, including both `@oods/tokens` and `@oods/tw-variants` (PolyForm-Noncommercial-1.0.0).
- **`README.md`** rewritten for a newcomer:
  - what TraceLab does today: the Librarian, missions run by DeepSearch, the Evidence Ledger, cited reports and the MCP;
  - the hosted app and how access works (invite codes);
  - the self-host quickstart, saying plainly that research runs need a DeepSearch worker, which is not public while DeepSearch is private. Today's step `pip install -r requirements.txt` (README.md:67) installs nothing, because that file is intentionally empty;
  - pointers into `docs/`;
  - what `cmos/` is (the project's Reasonbook record and acceptance receipts, which is why a clone is about 1 GB);
  - the license.
- **`SECURITY.md`** points at GitHub private vulnerability reporting, which gets turned on.
- **A short `CONTRIBUTING.md`:**
  - how to run the tests;
  - that CI lints with `ruff check` and does not enforce `ruff format`;
  - that a new Playwright spec must be added to the enumerated CI list.
- **GitHub metadata:** a description matching the README's first sentence, homepage `https://tracelab.aquex.ai`, and topics. `tracelab.egg-info/` leaves the tree and is ignored.
- **The quickstart is proven, not assumed.** In an empty directory, clone from GitHub and follow the README verbatim to a running UI and API with Docker, which is available on this machine. Every deviation is fixed in the README, not worked around.

**Done when:**
- `gh repo view` reports the license, description, homepage and topics.
- Private vulnerability reporting reads enabled.
- Every relative link in new and changed Markdown resolves.
- The receipt holds the fresh-clone transcript, ending in a 200 from the local UI and the API health route.
- A grep for the stale README fragments returns nothing.
- `git ls-files tracelab.egg-info` is empty.

### S66-DECOUPLE — The app stops writing into the record folder

Closes #380. It handles the application half of #487's part 3; the folder move itself is S68-RB4.

**Objective:**
- no code under `app/` reads or writes files under `cmos/`;
- running the test suite leaves the tracked tree unchanged;
- no API response changes, except the retired decision-links routes.

Verified on `bb0b270`:

- **Telemetry writers.** Nine writers default to `cmos/telemetry/events/`:
  - `app/services/cache_manager.py:74-80`
  - `app/services/evidence_auto_linking.py:157-163`
  - `app/services/correction_queue.py:89`
  - `app/services/webhook_client.py:75`
  - `app/services/pedr/delta_sync.py:605`
  - `app/services/pedr/sync_events.py:359`
  - `app/services/pedr/preflight.py:53`
  - `app/services/pedr/search_orchestrator.py:82`
  - `app/cli/pedr.py:35`

  Their defaults move to one new gitignored directory, `telemetry/runtime/`, keeping their file names. Nothing in `app/` reads these files. Their readers are scripts, such as `scripts/pedr_graph_quality_validation.py:44` and the telemetry migrate/validate scripts. They keep reading the historical files, which stay where they are as evidence. The developer CLI `app/cli/collect_performance_metrics.py:129` writes into `cmos/reports/sprint-01` and moves the same way.
- **The coverage report is a writer, not a reader.** `app/services/coverage_report.py:23-24,120-122` computes the report from the database and overwrites `cmos/reports/sprint-01/ingestion_format_coverage.json` on every GET (`app/api/v1/documents.py:573-578`) and on every successful ingestion (`app/services/document_ingestion.py:410`). Its write target moves to `telemetry/runtime/`. The test scaffolding that saves and restores that receipt moves with it: `tests/conftest.py:83` and `:193-200`, and `tests/test_document_ingestion.py:37`.
- **Tests that write tracked files** write to temporary paths instead:
  - `tests/test_semantic_edge_e2e_validation.py:530-533` and `tests/test_graph_e2e_validation.py:494-497` rewrite receipts under `cmos/reports/`;
  - other tests append to root `telemetry/events/quality-gates.jsonl` (`app/services/quality_gate_service.py:64`), `quality-automation.jsonl` (`app/services/quality_checks.py:110`) and `sprint-04-performance.jsonl` (`app/services/cost_monitor.py:33`).

  Root `telemetry/` is outside `cmos/` and is live data: `app/services/metrics_aggregator.py:245` reads `sprint-04-performance.jsonl` for the admin dashboard, so those runtime defaults do not change.
- **Retire the decision-links router** (`app/api/v1/decision_links.py`): GET `/decisions/linked`, GET `/decisions/linked/{id}` and POST `/decisions/linked/{id}/evidence`. It is admin-only and reads and writes the Reasonbook database with raw SQL. Nothing in the frontend, the MCP package or `cmos/contracts/mcp-parity-manifest.json` calls it. The deployed image has no record database (`cmos/db/cmos.sqlite` is gitignored), so in production it can only fail.
  - Remove its registration in `app/main.py`.
  - Update `tests/test_recovery_routes.py:58-125,312-336`, `tests/test_service_principal_route_boundary.py:158`, `tests/test_decision_insight_linking.py:435-588` and `docs/authentication.md:363`.
  - This supersedes the decision-links half of RECOVER-1's restore (decision #381). Its other parts stand.
- **Unchanged:**
  - historical identifiers: `cmos.mission.*` event names, the `cmos` telemetry source value, cmos-mcp contract comments and docstring references, as Reasonbook's own guidance asks;
  - every reference outside `app/` (tests, scripts, frontend, CI), which S68-RB4 updates with the folder move.
- No new environment variable or setting.

**Done when:**
- `git grep` over `app/` finds no filesystem path under `cmos/`, and the receipt lists each surviving match as a comment or identifier.
- CI's backend pytest invocation, run from a clean checkout, leaves `git status --porcelain` empty. Before the change, it modifies the files #380 names.
- Each moved writer has a test that proves its new location and fails when pointed back at `cmos/`.
- The coverage report's response is identical before and after, apart from `generated_at`.
- On production, `https://api.tracelab.aquex.ai/api/v1/decisions/linked` answers 404 to an authenticated admin request. Today it answers 401 unauthenticated.
- Required CI and the post-deploy check are green.

### S66-TESTS — Every browser spec runs, and the suite stops flaking

Closes #485, #448 and #379. *Requires DECOUPLE and SETTINGS.*

- **The nine specs no workflow runs:** `admin-password-recovery`, `password-recovery`, `mission-live-logs`, `report-citations`, `session-code-accessibility`, `token-contrast`, `console`, `evidence` and `hygiene`.
  - Run each locally against a production build (`next build` then `next start`, as CI does) before wiring it in, because any may have rotted. Fix what fails.
  - Add each survivor to the list at `.github/workflows/frontend-production-build.yml:91`, or to `production-smoke.yml` if it needs production.
  - Delete a spec only with a recorded reason.
- **#448:** two app-shell theme-bootstrap tests fail under `next dev` and pass under `next start`. `frontend/playwright.config.ts:22` starts `next dev` by default, so a plain local run fails. Make the default match CI, or make the tests pass under dev.
- **#379:** `tests/test_semantic_edge_e2e_validation.py:407` asserts an average under 5 ms and a maximum under 20 ms (lines 421-422) on a server-side timing. Convert it to best-of-rounds or a baseline-relative bound, following `tests/integration/test_aggregate_perf_budgets.py`.

**Done when:**
- The specs on disk and the enumerated lists match exactly, or each exception has a reason in the receipt.
- The PR's CI run shows each revived spec executing, with test counts.
- A plain local `npx playwright test` of the app-shell spec passes.
- Every failure found is fixed or reported as a product defect, never skipped silently.
- For #379, under induced CPU load the old assertion fails and the new one passes, and an injected slowdown in the graph layer still fails the new one.

### S66-MCP — The documented mission schema works

Closes #174 and #486.

- **#174:** the MCP (`packages/tracelab-mcp/src/index.ts:921`, `z.record(z.unknown())`) and REST (`app/schemas/mission.py:131`) accept `expected_output_schema` only as an object.
  - The vendored compiler requires `kind`, `title` and `format` on each deliverable (`app/services/contract_compiler/contract.py:898-919`).
  - The MCP's own example (`index.ts:509`) omits them, and so do the UI's examples (`frontend/src/components/missions/MissionForm.tsx:49-50`, `frontend/src/lib/schemas/apiMissionForm.ts:56`).
  - Reproduce first, through the installed MCP client against the deployed preview route, with no research dispatched. Delete any draft mission the reproduction creates.
  - Then make the documented examples, the accepted shapes and the compiler agree on both serialization surfaces. Update `cmos/contracts/mission-authoring-contract.md` in the same commit (agents.md: Mission-Authoring Boundary Contract).
- **#486:** `packages/tracelab-mcp/README.md:31` installs `@2.1.1`. Use `@latest`, like the other setup examples.
- **Publish 2.1.3** under DoD-1, using learning #295's interactive browser approval, which Derek gives. Derek's Aquex hub pins exactly 2.1.0 and won't pick up 2.1.3 unless he moves it to `@latest`.

**Done when:**
- A regression test through the MCP client (the MCP Contract Guard pattern, `TestMissionVerbContract`) fails before the fix and passes after.
- The README, tool-description and UI examples compile on the deployed preview route with zero provider execution, and no reproduction draft remains.
- Registry 2.1.3, installed fresh, passes the stdio check suite, and its tarball matches the tested pack.
- If reproduction shows no defect, #174 closes on that evidence, and 2.1.3 carries only the README fix.

**Out of Sprint 66:**
- new product features;
- UX redesign (Sprint 67);
- project sharing (deferred; Open Question 5);
- the Reasonbook folder move (Sprint 68);
- any history rewrite (decision #614);
- paid research runs;
- any work in the DeepSearch repository from TraceLab sessions.

**Alternatives considered:**

- *Move the record to Reasonbook 4.0's folder this sprint.* Deferred to Sprint 68. It renames 4,049 tracked files and must update test tooling, scripts, frontend configuration and CI references in the same change. That is a lot of churn in launch week for no user-visible gain. DECOUPLE takes the application out of the folder now, so the move touches only tooling.
- *Treat the clone size as a reason to rewrite history.* Not on its own. A rewrite changes every commit hash the record, receipts and Railway history cite. Only the personal-data question (Open Question 2) could justify one.
- *One combined open-source mission.* Split so that the exposure work runs first: it may need Derek to rotate a credential or decide about history. The README is then proven against a fresh clone as its own deliverable.

---

## Sprint 67 — The UX pass (planned shell; scoped with Derek)

Sprint 67 takes Derek's direct UX and design feedback, plus #406: DeepSearch claims stored as raw Markdown table rows show verbatim in evidence and in the Librarian's provenance display. Derek is writing a full UX doc while Sprint 66 runs, and Sprint 67 is scoped from it at the next planning session. The share-out is an invite-only demo for 5–10 people (decision #614), so the sprint ends by walking that path on production on the final build: invite code, sign-up, the Librarian, a mission and its evidence. It also covers production smoke and the public repository page.

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
| #406 | Raw Markdown table rows as claim text | Sprint 67 |
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
| Seven missions in about two days | DEPS, EXPOSURE and SETTINGS run first. Any later mission that slips moves to Sprint 68 and does not block Monday |

---

## Change Log

- **2026-10-13 UTC, Derek's answers; Sprint 66 opened.**
  - Answers: merge (PR #416 merged as `7ee7c8c`); license MIT (decision #613, correcting #612's stored approval words); history kept, current tree cleaned; messages to any project allowed; Monday is an invite-only demo for 5–10 people (decision #614).
  - S66-DEPS started and opened the sprint, and the identity was synchronised to `sprint-66-active`.
  - SETTINGS moved ahead of FRONT, because Monday is an app demo.
  - Sprint 67 will be scoped from Derek's UX doc at the next planning session.
- **2026-10-13 UTC, created at Sprint 66 planning (session PS-2026-10-13-003).** Derek: "lets open a planning session and get sprint planning underway … make sure we're in good shape for next Mondays share out … lets get these carry forward and remaining items put to bed first."
  - All 24 open follow-ups are dispositioned: 8 into Sprint 66 missions, 1 to Sprint 67, 4 done and 11 closed with reasons.
  - Sprint 66 is drafted as seven missions.
  - Planning found that backend CI is red because of an upstream pydantic release (PR #416). It also found third-party personal data and two noncommercially licensed vendored packages in the public tree.
  - An independent critic returned NEEDS-REVISION twice. The first pass had four blocking findings; the second found that `@oods/tw-variants` is noncommercial too. Both are resolved, and the third pass approved.
