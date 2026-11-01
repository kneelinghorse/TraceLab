# LIB-3 — reviewed project descriptions

The [description contract](../../../contracts/librarian-descriptions.md) implements decision #553 and the [Sprint 60 handoff](../../../planning/sprint-60-HANDOFF.md). CMOS owns closure status; deployment acceptance is required before completing the mission.

The Librarian now drafts a description for the selected project, with editable review, current text, input-coverage disclosure and source links. Empty projects use an explicitly labeled planning brief. Generating, dismissing or reopening drafts changes no research artifact. Proposals are signed and bound to their caller, project, reviewed text, source hashes and baseline revision. Acceptance rechecks authorization and source liveness, saves provenance and applies the reviewed value once. Restore refuses to overwrite any later description edit, including an edit that returned to the same text. Manual writes use SQL revision arithmetic so they serialize with acceptance.

Migration 054 adds a default-zero description revision and nullable JSON provenance. Legacy descriptions remain intact. The latest receipt supports one-level undo; it does not claim to be a complete change-history log. Citation validation proves source identities and paragraph coverage, not semantic entailment. The four human-review API operations remain REST-only by design. No package source, provider configuration or environment variables changed.

## Local verification

- Core Librarian/backend regressions: 58 passed, no skips (`lib3-regressions.log`).
- Related project, document access, report citations and Q&A: 89 passed, no skips (`lib3-related.log`).
- PostgreSQL migration/legacy preservation and concurrent acceptance/manual-edit protection: 2 passed, no skips (`lib3-postgres.log`).
- Frontend full run: 267 passed, no skips; subsequent late-response isolation test brings the focused Librarian suites to 25 passing (`lib3-all-ui.log`, `lib3-ui-final.log`).
- Built-browser: six passing scenarios, Light/Dark at 390/820/1440; keyboard review/accept, persistence without generation, explicit accept/restore, no overflow or serious/critical axe findings (`lib3-browser-final.log`). A caught focus race was corrected to a post-render effect before the passing run.
- Final description/expiry/whitespace, PostgreSQL and full migration/model-coverage pass: 19 passed, no skips (`lib3-final-backend.log`). The final six description component tests also pass.
- Production frontend build, changed-file Ruff/ESLint, foundational-reference validation and MCP parity audit pass. Parity reports 107 operations, nine tools and 50 actions; all four new operations are classified.
- Description history remains within the selected project even if a source is later moved elsewhere; the final 17-test description suite passes (`lib3-history-scope.log`). The six viewport/theme cases are now included in the required production-build CI job. The committed frontend was rebuilt and rechecked (`lib3-build-reviewed.log`, `lib3-browser-reviewed.log`).
- Both mutation tests fail when their guard is bypassed: changed-source acceptance and cross-user proposal replay. Source restoration is recorded in `mutation-proof.json`.
- New description tests forbid socket connections and use scripted models. Existing Q&A/report tests use their model seams. All commands pin Qdrant to loopback port 9; PostgreSQL uses an isolated PostgreSQL 15 testcontainer. Browser routes use fixture responses. Test telemetry generated in the historical sprint-04 log is discarded; this receipt preserves this mission's results.

Initial harness failures were corrected: required user display names were missing, and parallel pytest processes shared the root SQLite reset fixture. Database suites subsequently ran sequentially. No production service was contacted by those tests. Existing browser-data age and Python deprecation warnings remain disclosed in the logs.

The full CI backend suite caught the evidence auto-linking fixture's handwritten projects table missing the two new columns. Its DDL now matches the model; all seven auto-linking tests pass (`lib3-fixture-compatibility.log`). No quarantine or skip list was changed.

## Merge and CI

[PR #391](https://github.com/kneelinghorse/TraceLab/pull/391) merged as `4d64190ff1fb126fe0b1a9b3b41b3d8febae1c47` after all eight required gates and MCP package validation passed. `ci-final.json` links the successful runs: backend **2,911 passed / 3 skipped / 12 existing quarantined deselections**, PostgreSQL **147 passed / 2 skipped**, frontend **268 passed**, production browser **64 passed**. The integration skips require a live RBAC deployment and authenticated CLI server. No skip or quarantine list changed; focused LIB-3 suites had no skips.

## Deployment acceptance

Both production endpoints served `4d64190ff1fb126fe0b1a9b3b41b3d8febae1c47`, and Railway logged migration `053_report_citations → 054_description_provenance`. The [automatic post-deploy smoke](https://github.com/kneelinghorse/TraceLab/actions/runs/36632588275) also passed. See `deploy-wait.json`, `deployed-services.json` and `deployed-migration.log`.

`deployed_acceptance.mjs` uses the established human credential and REPORT-1's TraceLab Research acceptance project plus the explicitly named empty **LIB-3 acceptance — planned onboarding study** fixture. Two real calls to the configured `gpt-5.1` model recorded 256 and 5,451 total tokens respectively. The populated input used seven chunks within the 24,000-character budget, from 352 eligible of 360 readable chunks, and disclosed limited coverage. These seven chunks are from one document; the result does not claim complete project coverage.

Both drafts left saved descriptions unchanged. Explicit acceptance persisted the reviewed value and provenance; replay and fresh reads matched. All seven citation destinations resolved within the selected project. Guarded restore and its replay returned each exact original description, including the populated project's null value. `deployed-acceptance.json` records hashes, revisions, source identities and metering without credentials or signed proposals. The named empty fixture and minimal acceptance history remain; original descriptions are restored.

The real deployed browser then verified both projects in Light at 390px and Dark at 1440px. All seven exact chunk destinations opened by keyboard in each theme (14 openings), restored status and prior draft history remained visible, and the restore action was unavailable after completion. No page errors, horizontal overflow or write requests were observed. See `deployed-browser.json` and four screenshots. API responses were not mocked. This is agent verification, not Derek's personal acceptance.

For a documentation-only final merge, compare application/migration/frontend trees with the accepted commit and run `LIB3_SERVING_COMMIT=<final-sha> node cmos/reports/sprint-60/LIB-3/reverify.mjs`. It checks both serving identities and the two restored descriptions, receipt identities and revisions without writes or model calls. Record that final SHA/result in CMOS. Railway's existing configuration deadline remains next-step #451; no deployment configuration or dependency changes are included here.
