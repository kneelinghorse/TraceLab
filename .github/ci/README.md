# CI enforcement baseline and promotion ratchet

This directory records the measured baseline behind CI-1. The introducing pull
request must reproduce the blocking results below; this file is evidence, not a
substitute for green GitHub checks.

## 2026-08-21 post-PEDR-1C baseline

| Lane | Command | Result |
| --- | --- | --- |
| Clean collection | Fresh Python 3.11.9 virtualenv, `pip install -e '.[dev,test]'`, then `pytest --collect-only -q` | 2,304 collected, 0 errors |
| Backend suite | `pytest --ignore=tests/integration` with every node in `backend-quarantine.txt` passed as `--deselect` | 2,142 passed, 3 skipped, 49 deselected |
| PostgreSQL integration | `pytest tests/integration -v` with a PostgreSQL 15 testcontainer | 106 passed, 4 skipped |
| Frontend unit | `npm run test:unit -- --run` | 66 passed |
| Frontend types | `npm run type-check` | Passed |
| Frontend production build | `npm run build` | Passed |
| Changed-file Ruff | Ruff 0.8.0 against every changed Python file | Passed |
| Secret scan | `python scripts/check_no_credential_literals.py --tracked` | Passed |

The three backend skips are declared integration-with-external-services cases:
one auto-ingest case requires an embedding service and Qdrant, and two PEDR
orchestrator cases require OpenAI and Qdrant.

The four PostgreSQL-lane skips are also explicit: one live RBAC matrix needs
`RBAC_VERIFY_BASE_URL`, one CLI flow needs a running authenticated server, and
two RAG pipeline cases retain an OpenAI/httpx compatibility skip.

At that historical baseline, frontend lint reported 12
errors and 13 warnings, full-repository Ruff 0.8.0 reported 1,893 findings, and
mypy reported 970 errors. These were not passing gates. UX-5 subsequently made
frontend lint blocking; CI-2's current disposition for Ruff/mypy is below.

## Quarantine contract

`backend-quarantine.txt` contains exactly 12 unique pytest node IDs. Every row
has a reason, tests remain collected, and the workflow fails unless pytest's own
summary reports exactly 12 deselections. A stale, duplicate, or misspelled node
therefore breaks the gate instead of quietly shrinking coverage.

## Promotion ratchet

Repository maintainers own this ratchet. A streak counts successful `push` runs
on `main` from the original attempt; manual reruns do not manufacture a streak.
A failure resets the streak to zero. A concurrency cancellation neither counts
nor resets it.

- `backend-integration` becomes required after five consecutive qualifying green
  runs. Promote it with a dedicated branch-protection change and verify the
  required context through a GitHub API readback.
- Playwright first lands as an advisory follow-up. It becomes required only
  after its deterministic job records five consecutive qualifying green runs.
- ESLint first reaches zero errors and zero warnings in its separate
  deploy-verified cleanup mission. Its advisory job then needs five consecutive
  qualifying green runs before promotion.
- Any future full-repository Ruff or Python type-checking lane must first have
  a scoped remediation plan and reach a green baseline without a mechanical
  repository-wide rewrite. It then needs five consecutive qualifying green
  runs before promotion; CI-2 removes the existing never-green advisory jobs.

Until promoted, the day-one required contexts are `backend-suite`, `vitest`,
`type-check`, `ruff-diff`, `build-frontend-production`, and `Secret Scan`.
Production smoke, `backend-integration`, Playwright, ESLint, full-repository
Ruff, and mypy are not day-one required contexts.

## CI-2 lint-lane disposition (2026-09-13)

Measured on `d51ed2c` with Python 3.11.9. These findings remain diagnostic debt;
removing the jobs does not fix them or claim repository-wide lint/type safety.

| Lane | Current command and version | Findings | Disposition |
| --- | --- | --- | --- |
| `ruff-full` | Ruff 0.8.0, `ruff check .` | 1,635 findings in 139 files | **Drop** the advisory job. Changed-file Ruff remains required and checks each touched Python file in full. A blanket cleanup would exceed this mission and risk another formatting-loss incident; a large grandfathered baseline would add maintenance without establishing a clean repository. |
| `mypy` | mypy 2.3.1, `mypy app/ --config-file pyproject.toml` | 1,043 errors in 124 files, 237 files checked | **Drop** the advisory job. It has no passing baseline and no working promotion path. Type remediation needs its own scoped mission; `pyproject.toml` retains the configuration and dev dependency for local diagnostics. There is no replacement Python type-checking CI gate. |

`Backend Lint` now contains only `ruff-diff`, with no `continue-on-error`. Its
pinned Ruff version, changed-file selection, and per-commit logic-deletion guard
are unchanged. Do not run `ruff format` for this work. No application code or
test quarantine is changed.

The retained lane is already required in `main` branch protection. Its five
consecutive original-attempt `push` runs on `main` were verified green:
`34761469702`, `34762305255`, `34764003123`, `34764874442`, `34768817913`.
The same runs show the retired jobs failing; their overall workflow success
was due to advisory handling and is not presented as all-jobs-green evidence.
The CI-2 receipt records the first post-change run and branch-protection readback.
No new lane is introduced or promoted, so the five-run promotion requirement
does not apply to the removed jobs. Future lanes still follow the ratchet above.

## RECOVER-1 restoration (2026-09-12)

Re-enabled 24 nodes: ingestion edge materialization (7), semantic edge inventory
(2), mission-event endpoints (6), event smoke flows (3), and evidence linking (6).
The evidence fixtures now include the current owner/Space columns; the mission
status smoke uses the current PATCH verb. Restored behavior has additional
regression coverage for partial search diagnostics, disabled layers, caching,
canonical YAML/update dispatch, telemetry failures, and route RBAC.

## RECOVER-2 restoration (2026-09-12)

Re-enabled ten nodes: eight telemetry/correction assertions, DeepSearch ingest
persistence, and the twelve-query graph acceptance case. DeepSearch now injects
only external embedding/vector providers; real linking, quality gates, and the
canonical mission writes remain under test. Nine actual telemetry writers have
additional envelope/payload and failing-sink coverage. The twelve remaining
quarantine reasons record reproduced failures rather than claiming the recovered
contracts were intentionally retired.

The required `ruff-diff` job also checks every commit in the change range with
`scripts/check_format_only_changes.py`. Formatting-only/style claims with net
non-whitespace deletions in `app/` fail when the Python AST changes (non-Python
files are conservatively flagged). Identical Python ASTs permit line wrapping
and comment cleanup. Rename detection is disabled so deleting or renaming a
module cannot bypass the check. A deliberate behavioral change must be described
as such in the commit message. This guard flags d592c92 and tests intermediate
commits even when a later commit restores their deletions.
