# Reasonbook folder migration — preparation receipt

Status: prepared; the live record has **not** moved. The migration mission remains
open until the official offline cutover, count comparison, registration follow-up
and required CI finish. This branch must not merge before that cutover.

The proposed tree moves 1,890 tracked files into `rbook`. It updates Python imports,
helper database defaults, pytest and Playwright reporters, ingestion defaults, MCP
contract paths, documentation links and ignore rules. Application storage remains
separate from the project record. The historical telemetry source and event names
remain unchanged. MCP source guidance changes here; no new npm release is claimed.

## Preparation and preservation

- Reasonbook 4.9.0's docs-only preview was reviewed and its docs-only apply completed
  against the canonical project. `docs-only-applied.json` preserves the output.
- The full project preview was then reviewed; `full-preview.json` preserves it.
- The migrator changed two tool identifiers inside the protected root operating
  rules. That block was restored byte-for-byte; the current tool names are explained
  above it. Its SHA-256 is
  `ff5c9074c85866256ff9f51b5fee7594535b298a6379ae3dd3970853a17c3a9d`.
- A SQLite backup made through the backup API passes `integrity_check`.
  `preparation-backup.json` records its counts. These are preparatory counts, not an
  assertion that an offline move or before/after comparison has happened.
- Three pre-existing untracked planning notes remain in the canonical checkout;
  they were hashed for preservation and were not copied into this branch.
- All 1,784 tracked files under historical missions, planning, receipts,
  telemetry, research and status are exact blob renames. Session exports also
  retain their original contents. `retained-legacy-paths.json` lists every retained
  former path by file and line, with its reason.

## Validation

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
telemetry artifact. Required remote CI is still pending.

## Offline cutover still required

The packaged 4.9.0 migration guard finds a live Reasonbook runtime. Client-version
inspection passes, but runtime inspection refuses the move. This includes idle
servers in other Claude and Codex sessions; an empty active-session list alone is
insufficient. No process was stopped, no guard bypassed, and full apply was not run.

When all record runtimes are offline, capture fresh counts for decisions,
learnings, constraints, missions, sprints, next steps and sessions; record the
dashboard inbox/sent totals separately because messages are not stored in this
SQLite database. Run the official migration, verify its pre-migrate snapshot and
integrity check, compare counts before any new record writes, and verify the
existing project registration. Preserve the private planning notes and protected
rules while bringing the canonical checkout onto the tested branch. Then finish
CI, merge, and notify Reasonbook of the result.
