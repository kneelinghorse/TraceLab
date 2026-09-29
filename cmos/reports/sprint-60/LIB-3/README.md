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

## Deployment acceptance

Pending merge and deployment. `deployed_acceptance.mjs` uses the established human credential and REPORT-1's TraceLab Research acceptance project plus one explicitly named empty LIB-3 fixture. It verifies the exact serving commit, draft-no-write, acceptance/replay, fresh state, current in-project source destinations, and guarded restore/replay. Original descriptions are restored even if a post-accept verification fails. It records hashes and identities without credentials or signed proposals. This is agent verification, not Derek's personal acceptance.
