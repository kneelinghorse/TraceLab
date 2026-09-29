# DUP-1 — explicit document duplicate review

The [comparison contract](../../../contracts/librarian-duplicates.md) implements decision #554 and the [Sprint 60 handoff](../../../planning/sprint-60-HANDOFF.md). CMOS owns mission status. The merged application build passed local, CI and deployed acceptance.

The Librarian compares one selected project's live readable extracted text only when asked. Exact normalized text and conservative probable overlap are distinct. Stable source identities, excerpts, method and coverage are visible; fresh comparison rechecks access, project membership and content identity. Keep-both/dismiss affect only the caller's browser review. There is no merge, delete, reparent, archive, graph/collection write, model call, background scan or new index.

The bounded method examines at most 100 documents of at most 20,000 characters and returns at most 20 pairs. Exact comparison uses complete non-empty Unicode/case/whitespace-normalized text. Probable comparison requires 80% five-word-phrase overlap, similar lengths, 40 shared phrases and substantial support across two distinct paragraphs in each document. Single-passage/short texts are exact-only; paraphrases may be missed. A numeric score measures lexical overlap, not a probability. Empty/overlong inputs, scan limits and candidate truncation remain explicit. No migration, dependency, new environment variable or MCP package changes were needed.

## Local verification

- Backend duplicate, description, Librarian mission/Q&A and provenance regressions: **81 passed**, no skips (`dup1-regressions.log`). New tests prohibit outbound socket connections; existing Librarian cases use scripted model seams. Root fixtures force isolated SQLite; every invocation pins Qdrant to loopback port 9. Python suites ran sequentially.
- Calibration and scope tests include exact/edited positives, identical-title/different-content and related-topic negatives, a dominant shared disclaimer, short Unicode text, empty and overlong matching prefixes, scan/result limits, deleted/reparented/changed sources, lost member access, forged comparison IDs and unknown write fields. SQL listeners verify no INSERT/UPDATE/DELETE occurs during scan/replay/compare.
- Mutation proofs: bypassing the paragraph-distribution guard admits the dominant disclaimer; bypassing the selected-project query filter exposes a foreign row before preparation. Each intended test fails; `mutation-proof.json` records source restoration. The disclaimer fixture was strengthened above the overlap threshold so the paragraph guard is what makes the regression pass.
- Frontend full run: **275 passed**, no skips (`dup1-all-ui.log`). Seven new review tests cover explicit scan, persistence, local dismissal/keep-both, fresh comparison/focus, failed comparisons/scans, and account/project/late-response isolation. A sibling React key collision with the description panel was found and fixed using distinct panel key prefixes.
- Built browser: **12 passed** across description and duplicate workflows, Light/Dark at 390/820/1440 (`dup1-browser.log`). Final duplicate-only screenshot check: **6 passed** (`dup1-browser-final.log`). Keyboard focus, reload without scanning, fresh comparison, keep-both persistence, no corpus requests, no horizontal overflow or serious/critical axe violations. Mobile Light and desktop Dark captures inspected.
- Production build, TypeScript, changed-file ESLint/Ruff, foundational-reference validation and parity audit pass. Parity: **109 operations / 9 tools / 50 actions**, including two REST-only-by-design review operations. The six new viewport/theme cases are included in the required production-build CI job.

The initial red test run failed because the new service did not yet exist, before implementation. Existing browser-data age, Python deprecation and test timeout warnings remain in logs. Synthetic test telemetry appended to the historical sprint-04 file was discarded after inspection; this directory retains mission-specific results.

## CI

[PR #393](https://github.com/kneelinghorse/TraceLab/pull/393), merged as `edc0a0b4ea1a8049dbb4ffb74e6af590f554333f`, passed every required check. Backend: **2,931 passed, 3 existing skips, 12 existing quarantined deselections**. PostgreSQL integration: **147 passed, 2 existing skips**. Frontend: **275 passed**; production browser: **70 passed**. `ci-final.json` records the checked head and job URLs.

## Deployed acceptance

Both production services served **`edc0a0b4ea1a8049dbb4ffb74e6af590f554333f`** before fixture setup and verification. Railway backend deployment `073e8f41-a165-4117-b653-07c0e24570f6` and frontend `da5b6975-6bd4-4fd5-afdb-8101d3fb38e6` succeeded; [post-deploy wait and smoke](https://github.com/kneelinghorse/TraceLab/actions/runs/36639376583) passed. No migration or environment-variable change was required. See `deploy-wait.json` and `deployed-services.json`.

`deployed_acceptance.mjs` created project **`0d6c5b1d-72eb-4390-a40b-c48c88cdb302`**, “Sprint 60 Librarian acceptance — onboarding feedback,” and six named synthetic documents through existing upload/processing operations. IDs are in `deployed-progress.json` for reuse by ORG-1, LIB-4 and WALK-3. Fixture ingestion is separate from duplicate analysis.

The read-only review examined all six documents and returned exactly **one exact pair and two probable-overlap pairs**. The distinct same-title document and shared-disclaimer notes produced no false positives. Every candidate refreshed successfully, current text and source links matched, repeated scans retained the same candidates, and before/after document/content/graph/collection/project snapshots were identical. `deployed-acceptance.json` records the coverage, evidence, identities and matching hashes. Duplicate review made **zero model calls**.

`deployed_browser.mjs` exercised real responses in **Light at 390px and Dark at 1440px**, opened all **12 source destinations by keyboard**, checked fresh comparison and reload without rescan, and preserved keep-both/dismiss choices. Both cases recorded **zero corpus write requests, page errors or horizontal overflow**. Screenshots were inspected; details are in `deployed-browser.json`. Credentials and proposal tokens are absent from the receipt. This is agent verification, not Derek's personal acceptance.

`reverify.mjs` checks both exact serving identities, repeats fresh comparison against the same candidates and proves no research change. It can be rerun on the final receipt commit or later sprint builds without recreating fixtures or invoking a model. CMOS completion records the final serving commit after this receipt is merged.
