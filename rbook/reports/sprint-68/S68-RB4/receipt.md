# Reasonbook folder migration — verification receipt

Status: the live record is at `rbook/db/rbook.sqlite`; the earlier offline blocker
has cleared. Recovery verification on 2026-11-05 found an already-completed move.
PR [#443](https://github.com/kneelinghorse/TraceLab/pull/443) integrates the tracked
readers and is gated on all nine required checks before merge.

The tree moves 1,890 tracked files into `rbook`. It updates Python imports,
helper database defaults, pytest and Playwright reporters, ingestion defaults, MCP
contract paths, documentation links and ignore rules. Application storage remains
separate from the project record. The historical telemetry source and event names
remain unchanged. MCP source guidance changes here; no new npm release is claimed.

## Preparation and preservation

- Reasonbook 4.9.0's docs-only preview was reviewed and its docs-only apply completed
  against the canonical project. `docs-only-applied.json` preserves the output.
- The full project preview was then reviewed; `full-preview.json` preserves it.
- The November 1 preparation restored the then-current protected operating rules.
  The operator supplied updated rules on November 5 with the current Reasonbook
  tool identifiers. This branch preserves that new protected block exactly:
  SHA-256 `7139d139ac23fb82db7f349a897db31c04275a0deb2c112a67b086cd9a2001a9`.
- A SQLite backup made through the backup API passes `integrity_check`.
  `preparation-backup.json` records its counts. These are preparatory counts, not an
  assertion that an offline move or before/after comparison has happened.
- Three pre-existing untracked planning notes remain in the canonical checkout;
  they were hashed for preservation and were not copied into this branch.
- All 1,784 tracked files under historical missions, planning, receipts,
  telemetry, research and status are exact blob renames. Session exports also
  retain their original contents. `retained-legacy-paths.json` lists every retained
  former path by file and line, with its reason.

## Preparation validation (November 1)

- Initial focused backend run: 161 passed, no skips.
- Broader post-lint run: 169 passed; ten failures exactly match the pre-existing
  Sprint 3/4 telemetry-envelope quarantine. The quarantine remains unchanged.
- Frontend: 460 unit tests passed; TypeScript check passed.
- MCP: 160 unit tests passed. A clean tarball installation passed 73 stdio checks,
  including the old-tool migration response, with 73 HTTP requests and 74 links.
  The new migration-response check first failed against the previous entrypoint.
- Telemetry regression first failed with the old path detector, then passed with
  the renamed folder while retaining the historical source/event labels.
- Legacy Python helpers: 14 tests passed against a schema-generated disposable
  database. The live record was not used as a test fixture.
- Markdown ingestion TypeScript build passed.
- Both MCP parity audits and the foundational-reference validator passed.
- The existing Ruff gate includes renamed Python files. Required lint fixes were
  confined to touched files; no formatter, quarantine change or CI exemption was
  introduced. The exact changed-file Ruff check passes.

The final backend run passed 169 tests with the ten existing matching quarantine
entries deselected; none were skipped. Sixteen built-browser tests passed,
including all 20 route-migration assertions, and the moved reporter wrote its
telemetry artifact. Remote results are recorded in the PR checks; the required gate is unchanged.

## Recovered cutover verification (November 5)

The official pre-migrate snapshot was already present, with filesystem timestamp
2026-11-03T16:25:44Z. The old folder is absent and no migration journal or pending
marker remains. This session did not perform or witness that earlier apply and
cannot independently attest its process preflight. The snapshot contains 248
completed sessions and zero active sessions. No process was stopped in this work.

Before any resume writes, the snapshot and live database both passed SQLite
`integrity_check`. Every row in all seven core record tables matched, not just the
counts: 653 decisions, 327 learnings, 11 constraints, 452 missions, 69 sprints,
495 next steps and 248 sessions. `recovered-cutover.json` retains counts and hashes.
Subsequent mission/decision updates are normal new writes, after this comparison.

Reasonbook 4.12.0's current official dry-run reports no move, changes or blockers;
`recovered-preview.json` preserves its output. Its current guide permits compatible
Reasonbook 4+ runtimes for an unshared record, with exclusive database locking at
cutover; the November 1 machine-wide 4.9.0 blocker is no longer the current rule.
No guard was bypassed and there was no reason to repeat an already-completed move.

Health and local registration checks resolve the new database. Dashboard ownership,
slug and project ID are retained, and the owned-project API confirms its Local
Database Path points to `rbook/db/rbook.sqlite`. Inbox count is 51, matching the
November 1 receipt; sent count is currently 45 and is user-scoped. Messages are
remote dashboard records, not rows moved with SQLite. No contemporaneous pre-move
sent-total receipt is available, so exact before/after sent-count equality is not
claimed. Both message lists remain accessible; the latest sent migration notice
from November 1 is acknowledged.

## Resume validation and CI repair

The initial remote backend gate reported 3 failed, 3,226 passed, 4 skipped and
12 deselected. The other eight required checks passed. All three failures were
reproduced locally: updating the attribution link in each of the six vendored
compiler modules made its local manifest checksum stale. Only local source hashes
were refreshed; the upstream revision, upstream hashes and fixture bytes remain
unchanged. The vendor contract records this adaptation.

The repaired compiler, preview and mission API suites pass: 117 tests, no skips or
deselections. Canonical contract parity retains ID `8ca1ebfaa604dc7e` and SHA-256
`163e7af36080b8440afe55f501b023cb2e3aba84e1b8644298fc0784167b5cb6`.
The foundational-reference validator passes. Required remote CI on the final PR
head remains the merge gate; the PR's checks and the mission completion record
provide its final outcome, including pre-existing skips and quarantine counts.
