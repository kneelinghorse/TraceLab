# CI enforcement baseline and promotion ratchet

This directory records the measured baseline behind CI-1. The introducing pull
request must reproduce the blocking results below; this file is evidence, not a
substitute for green GitHub checks.

## 2026-08-20 post-fix baseline

| Lane | Command | Result |
| --- | --- | --- |
| Clean collection | Fresh Python 3.11.9 virtualenv, `pip install -e '.[dev,test]'`, then `pytest --collect-only -q` | 2,202 collected, 0 errors |
| Backend suite | `pytest --ignore=tests/integration` with every node in `backend-quarantine.txt` passed as `--deselect` | 2,050 passed, 3 skipped, 49 deselected |
| PostgreSQL integration | `pytest tests/integration -q` with a PostgreSQL 15 testcontainer | 96 passed, 4 skipped |
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

Advisory baselines remain intentionally visible: frontend lint reports 12
errors and 13 warnings, full-repository Ruff 0.8.0 reports 1,893 findings, and
mypy reports 970 errors. They are not silently treated as passing gates.

## Quarantine contract

`backend-quarantine.txt` contains exactly 49 unique pytest node IDs. Every row
has a reason, tests remain collected, and the workflow fails unless pytest's own
summary reports exactly 49 deselections. A stale, duplicate, or misspelled node
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
- Full-repository Ruff first reaches zero findings without a mechanical
  repository-wide rewrite. Its advisory job then needs five consecutive
  qualifying green runs before promotion.

Until promoted, the day-one required contexts are `backend-suite`, `vitest`,
`type-check`, `ruff-diff`, `build-frontend-production`, and `Secret Scan`.
Production smoke, `backend-integration`, Playwright, ESLint, full-repository
Ruff, and mypy are not day-one required contexts.
