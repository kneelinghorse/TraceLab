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
- Final restored-source regression: **39 passed**, no skips (`report1-final-focused.log`).
- Mutation proof: fabricated-marker substitution and bypassed source validation both turn their intended regression tests red; source files restored (`mutation-proof.json`, harness and logs).
- MCP parity audit: 103 operations / 9 tools / 50 actions, no errors. Foundational-reference validation passes.
- Isolation: report regressions prohibit socket connections, mock provider/cost collaborators, and use SQLite fixtures. Context/browser routes use isolated fixtures. PostgreSQL uses an isolated PostgreSQL 15 testcontainer. All commands set QDRANT_URL to loopback port 9; touched lifespan fixtures mock prewarming. No test requests go to production Qdrant.

The first full CI run caught two additional contract consumers: the RBAC smoke harness expected empty reports to be persisted, and the OODS schema map needed the new response fields. Both are updated. The RBAC check accepts the exact generic citation refusal while preserving its legacy content-leak checks; report regression tests require new ungrounded writes to fail. No quarantine changes were made.

Production acceptance is required before CMOS completion. `deployed_mcp.mjs` uses the already configured human credential (never logged), the established TraceLab Research acceptance project and its existing TRACE-SHARE result document. It creates one explicitly named acceptance report through published MCP 2.1.0, then verifies fresh REST/MCP reads, every source destination and all three export formats. A failed follow-up can reuse the recorded report ID without another generation. This is agent verification, not Derek's personal acceptance.
