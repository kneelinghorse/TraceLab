# REPORT-1 — durable report citations

This receipt follows the [Sprint 60 handoff](../../../planning/sprint-60-HANDOFF.md) and [collection/report contract](../../../contracts/collection-context-and-reports.md). CMOS decision #552 records the contract; learning #262 records the cache lesson.

Reports now retain the exact numbered citation map through both writers, fresh reads, metadata updates and exports. Migration 053 adds nullable JSON/JSONB columns without inventing historical mappings. The shared Librarian validator rejects missing or fabricated citation support. Effective inputs exclude empty and truncated-away text. Cache keys include ordered identities/text, prompt and model; cached mappings are checked before reuse.

Source access is refreshed after generation. The report transaction locks its supplied source rows against edits/deletion, checks the supplied text hash and persists the map alongside effective input records. Reads filter source identities, excerpts, destinations and independently authorized original result documents. Authored report prose remains intact when support disappears. The UI separates local numbered citations, original result documents and Evidence relationships. Existing generated reports record generation provenance, not fictional human acceptance.

Compatibility: new synthesis saves with no valid support return 400 instead of writing an empty artifact. Existing legacy reports remain readable; their Markdown/text bytes are unchanged. JSON responses add fields. New Markdown/text exports append absolute source destinations using the existing FRONTEND_URL (confirmed configured to the production frontend). Existing MCP citation objects are forwarded unchanged, so no npm source or release changes are required. Citation coverage is checked per prose block/list item using the existing claim validator; it does not prove semantic entailment.

## Local evidence

- Main backend regression: **161 passed**, no skips (`report1-regressions-3.log`). Older mocks were replaced with live source identities; no-evidence persistence assertions now assert refusal. Provider singleton fixtures are isolated.
- Related ownership/automatic-report/source-policy suites: **112 passed**, no skips (`report1-related.log`). Includes source access revoked while generation runs and independently scoped original result links.
- PostgreSQL: **3 passed**, no skips (`report1-postgres-final.log`): additive upgrade/downgrade, legacy preservation, both writers, source-lock conflict/rollback, and full Alembic/model coverage.
- Frontend: **262 passed**, no skips (`report1-all-ui.log`); types, changed-file lint and production build pass.
- Built-browser: **6 passed** (`report1-browser.log`), Light/Dark at 390/820/1440, keyboard source navigation, no horizontal overflow or serious/critical axe findings. Screenshots inspected at mobile Light and desktop Dark.
- Contract-consumer follow-up: **81 passed**, no skips (`report1-contract-followup.log`), including the real route RBAC matrix and presentation-schema guard.
- Final restored-source regression: **39 passed**, no skips (`report1-final-focused.log`).
- Mutation proof: fabricated-marker substitution and bypassed source validation both turn their intended regression tests red; source files restored (`mutation-proof.json`, harness and logs).
- MCP parity audit: 103 operations / 9 tools / 50 actions, no errors. Foundational-reference validation passes.
- Isolation: report regressions prohibit socket connections, mock provider/cost collaborators, and use SQLite fixtures. Context/browser routes use isolated fixtures. PostgreSQL uses an isolated PostgreSQL 15 testcontainer. All commands set QDRANT_URL to loopback port 9; touched lifespan fixtures mock prewarming. No test requests go to production Qdrant.

The first full CI run caught two additional contract consumers: the RBAC smoke harness expected empty reports to be persisted, and the OODS schema map needed the new response fields. Both are updated. The RBAC check accepts the exact generic citation refusal while preserving its legacy content-leak checks; report regression tests require new ungrounded writes to fail. No quarantine changes were made.

## Merge and CI

[PR #389](https://github.com/kneelinghorse/TraceLab/pull/389) merged as `93d71fcf4d8e0818103970b1c3131e6e1323681b` after all eight required gates and MCP package validation passed. `ci-final.json` links the exact successful runs: backend **2,894 passed / 3 skipped / 12 existing quarantined deselections**, PostgreSQL **145 passed / 2 skipped**, production browser **58 passed**, frontend **262 passed**. The two integration skips require a live RBAC deployment and an authenticated CLI server; no quarantine entries were changed. Focused REPORT-1 suites had no skips.

## Production acceptance

Both application endpoints served `93d71fcf4d8e0818103970b1c3131e6e1323681b`; Railway reported both deployments successful and the backend logged migration `052_personal_spaces → 053_report_citations`. Database health passed. The [automatic post-deploy smoke](https://github.com/kneelinghorse/TraceLab/actions/runs/36620870584) passed all 5 tests on the serving merge. See `deploy-wait.json`, `deployed-services.json` and `deployed-migration.log`.

Published MCP **2.1.0** created exactly one named acceptance report and collection. Its three markers retained their exact chunk/document identities through create, fresh MCP/REST reads, collection synthesis replay and all exports. MCP/REST export bytes matched; SHA-256 receipts are in `deployed-mcp.json`. [Open the saved report](https://tracelab.aquex.ai/reports/cb0ae24f-b28d-4b1c-839e-9a7172d66154).

The real deployed UI opened all three exact chunk destinations in Light at 390px and Dark at 1440px. No page errors or horizontal overflow occurred; source links and the unrecorded-review label were visible. The independent Evidence panel completed its scoped read and showed no linked entries. See `deployed-browser.json` and both screenshots. Source documents were not rewritten; no other accounts or research were mutated.

`deployed_mcp.mjs` uses the already configured human credential (never logged), the established TraceLab Research acceptance project and its existing TRACE-SHARE result document. It creates one explicitly named acceptance report through published MCP 2.1.0, then verifies fresh REST/MCP reads, every source destination and all three export formats. A failed follow-up can reuse the recorded report ID without another generation. This is agent verification, not Derek's personal acceptance.

Operational carry: deployment tooling repeats the existing Railway configuration deadline (2026-12-01, next-step #451) and frontend dependency advisories. No dependency files changed and no advisory audit was performed; these remain outside REPORT-1.

For a later documentation-only final merge, compare the application/migration/frontend trees with the accepted commit and run `REPORT1_SERVING_COMMIT=<final-sha> node cmos/reports/sprint-60/REPORT-1/reverify.mjs`. It checks both serving identities, the existing report's scoped citations and all export hashes without creating or regenerating anything; record its final SHA/result in CMOS.
