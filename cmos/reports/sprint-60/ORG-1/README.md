# ORG-1 — Reviewed themed collections

Implementation follows decisions #555/#556 and the [reviewed-collections contract](../../../contracts/librarian-collections.md). CMOS is authoritative for mission state. Guiding templates: [roadmap](../../../foundational-docs/roadmap_template.md) and [architecture](../../../foundational-docs/tech_arch_template.md).

The Librarian proposes bounded groups of actual saved excerpts from one selected project. A person edits the name/purpose, removes members, dismisses groups and accepts each chosen collection independently. Signed proposals bind caller, source hashes, order and the visible destination Space. Existing collection operations create the artifact with durable provenance; partial retries reuse it, and completed retries do not undo subsequent manual removals. Migration 055 adds nullable provenance and reviewed positions while preserving legacy ordering.

## Local verification

- 30 focused backend cases pass after restoring all three intentional mutations. They cover no-write previews, human ownership, edited ordered subsets, independent acceptance, partial retry, concurrent-safe identity, forged/foreign/stale inputs, completion revalidation, revoked provenance and no resurrection after deletion.
- 190 related backend cases passed before the three additional access/finalization cases. Local PostgreSQL: 104 marked integration cases passed, 47 marker-deselected, no skips; the two new migration/concurrency cases also passed independently. The unfiltered PostgreSQL suite remains a required CI gate.
- All 283 frontend tests, production build, TypeScript and changed-file lint passed. Twelve built-browser cases passed across Light/Dark and 390/820/1440 widths, including existing collection context. The six new cases check keyboard focus/source links, edits/dismissal persistence, explicit acceptance, exact partial-retry payload, no automatic generation, overflow and serious/critical accessibility violations.
- The parity inventory has 112 operations and no errors. Foundational references and changed Python lint pass. Existing warnings are retained in the logs; no formatting sweep was applied.
- Initial focused tests failed against missing routes. Deliberately removing caller binding, project filtering or the in-transaction attachment recheck fails the corresponding intent assertion; [mutation evidence](mutation-proof.json) records restoration. Source bodies, credentials and signed proposals are excluded from committed test output.

A clean-checkout run of the full backend CI invocation found one missing OODS presentation mapping for the new `librarian_generated` API flag: 2,960 passed, 3 existing skips and 12 quarantine exclusions, one failure. The mapping was added following the existing consumer-only convention; all 18 OODS contract tests then passed. The slow original CI run was canceled after this concrete local failure was found. Its log showed continued progress through 57%, rather than a proven deadlock. Fresh CI on the corrected revision is required.

## Deployed acceptance

Pending merge and exact-build deployment. Do not mark ORG-1 complete from local tests alone.

[`deployed_acceptance.mjs`](deployed_acceptance.mjs) is resumable. With `ORG1_SERVING_COMMIT` set to the exact 40-character serving commit, `prepare` adds three controlled chunk-bearing interview fixtures to the existing DUP-1 acceptance project and requests one real model proposal. `browser` restores that real proposal for Light/390 and Dark/1440 review, edits its first group, deselects a member, dismisses the others, opens each exact source, and explicitly accepts the same signed group in both contexts. `verify` checks fresh collection/provenance/export/source reads and the published MCP collection getter. `read-only` repeats final checks without upload, generation or acceptance. The private proposal is stored outside the repository and never printed.

The fixture is explicitly synthetic. Its longer notes address the existing ingestion minimum of 500 estimated tokens: the six DUP-1 text fixtures have no saved chunks and are therefore not claimed as organisation inputs. The acceptance receipt must distinguish agent verification from Derek's personal acceptance.
