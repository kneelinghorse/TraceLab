# LIB-4 acceptance — reviewed cited Reports

The Librarian shows a bounded, explicit source selection within one project, produces a cited preview, and saves that exact preview once with human acceptance. No second model call occurs on save. Existing Report views, exports and MCP retrieval retain their roles.

Contract: [reviewed reports](../../../contracts/librarian-reports.md), decision #557; guiding [Sprint 60 handoff](../../../planning/sprint-60-HANDOFF.md). No migration, dependency, environment variable or MCP package change.

## Local verification

- [186 related backend tests](backend-related.log) passed, including 27 new focused cases for no-write preview, exact save/export equality, source selection/budgets, wrong caller/project, expiration, stale cited and uncited inputs, role changes during generation, atomic failure/retry and no resurrection after deletion. Initial missing-route failures are retained in [initial-red.log](initial-red.log).
- [PostgreSQL concurrent acceptance](postgres-concurrency.log) passed: two requests returned one Report, one receipt and exact citation identities/order. The unfiltered PostgreSQL suite is also a required CI gate.
- [291 frontend tests](frontend-unit.log), [types](frontend-types.log), [changed-file lint](frontend-lint.log) and [production build](production-build.log) passed. The first full frontend run found an existing DUP-1 assertion checking focus before its effect settled; it now awaits the same focus outcome. No product focus behavior changed.
- [12 built-browser cases](built-browser.log) passed for the new review workflow and existing saved report citations, Light/Dark at 390/820/1440. Coverage includes keyboard/source links, input-change regeneration, persisted exact-save retry, no automatic model calls, no unrelated writes, overflow and serious/critical axe findings. [Light preview](built-report-light-390.png), [Dark preview](built-report-dark-1440.png).
- [Three intentional faults](mutation-proof.json) were caught and restored: removing caller binding, skipping the uncited-input recheck, and persisting altered prose. [Parity](mcp-parity.json) passes for 115 UI operations; the existing collection-list consumer inventory includes the new panel. Foundational references, Python lint and credential scanning passed. Existing warnings and any CI skips are disclosed rather than suppressed.

## Deployed acceptance

Pending merged-build deployment and real configured-model acceptance. This mission is not complete from local tests alone.

[deployed_acceptance.mjs](deployed_acceptance.mjs) requires the exact 40-character `LIB4_SERVING_COMMIT` and checks both serving versions. `prepare` requests one real draft from ORG-1 collection `cf1dd7ec-25f1-4141-9210-4a805e311137`, confirms no Report/source writes, and stores its signed proposal privately outside the repository. Inspect the returned preview before `browser`, which restores that real proposal, tests the edit guard and navigation, explicitly accepts it in both themes, and follows every preview/saved-report citation by keyboard. `verify` checks fresh REST, Markdown/JSON/text exports and the published MCP getter. `read-only` repeats those checks without generation or acceptance.

The synthetic sources and original collection are retained. Owner-role agent acceptance is separate from Derek's personal acceptance; WALK-3 still requires the agreed non-privileged end-to-end walkthrough. The final receipt-commit serving check remains the CMOS closure gate.
