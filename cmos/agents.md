# ABOUTME: Project context for AI agents working in the TraceLab repo.
# ABOUTME: Use this alongside the root agents.md / CLAUDE.md for application code guidance.

# TraceLab — CMOS Agent Context

CMOS keeps this project's record at the **Builder** level: decisions, lessons, sprints and missions. Its tools and hooks say when to use it; `cmos-mcp ambient off` turns the hooks off here.

## Project

TraceLab is a FastAPI + PostgreSQL research platform with RAG pipelines, document ingestion,
and a React/Vite frontend. The `cmos/` directory is a planning workbench — it does not contain
application code.

**Stack**: Python 3.11+, FastAPI, PostgreSQL 15, Alembic, React/Vite (frontend), SQLite (CMOS)
**Architecture**: Hexagonal — ports (`app/ports/`) define contracts, adapters wire implementations,
composition root in `app/dependencies.py`
**CI**: GitHub Actions — nine required checks on main: backend-suite, vitest, type-check, ruff-diff, build-frontend-production, Secret Scan, backend-integration, lint and mcp-package (GitHub protection readback 2026-10-01 UTC; strictness preserved; see `.github/ci/README.md`). No mypy gate since CI-2 (decision #407).

---

## Test Commands

```bash
# Unit tests (no DB)
pytest -m unit -v

# Integration tests (requires Docker — testcontainers)
pytest -m integration -v

# Lint (CI enforces ruff-diff on changed files only)
ruff check app/ tests/
# Do NOT run `ruff format`: it is not enforced and churns pre-existing code (decision #311)

# Type checking: local diagnostic only; CI has had no mypy gate since CI-2 (decision #407)
mypy app/ --config-file pyproject.toml

# Frontend unit tests
cd frontend && npm run test:unit

# Frontend E2E
cd frontend && npx playwright test
```

---

## What to Avoid

- Do not place application code inside `cmos/` — it is a planning workbench only
- Do not bypass hexagonal boundaries: routers call services, services call ports, adapters implement ports
- Do not commit `cmos/db/cmos.sqlite` — it is gitignored

---

### Historical sprint-47 note


**sprint-47** — Sprint D: RBAC Verifiability & Live-Gap Closure
Focus: make deny-by-default RBAC enforcement OBSERVABLE and PROVABLE — a runnable live
verification harness (`scripts/rbac_verify.py`) + an admin `rbac-status` endpoint — and close the
gaps the per-id flip left open (list row-filtering, model-parity, service-role tier on
`POST /missions/{id}/logs`, auth-hardening). The full users/roles ADMIN UI is split to S48.

---

## Architecture Reference

```
app/
  ports/          # typing.Protocol interfaces — depend on these, not concrete classes
  adapters/       # thin wrappers: repositories/, external/
  dependencies.py # composition root — wires ports to adapters via FastAPI Depends()
  routers/        # thin — call services, return responses
  services/       # orchestration logic
tests/
  unit/           # @pytest.mark.unit — no DB, mock at ports
  integration/    # @pytest.mark.integration — real PostgreSQL via testcontainers
  e2e/            # full-stack
```

ADRs: `docs/adr/001-005`

Planning and architecture changes must stay aligned with the canonical
`foundational-docs/roadmap_template.md` and
`foundational-docs/tech_arch_template.md` references.

---

## Boundary

CMOS does NOT contain: application code, migrations, routers, services, tests for the app

Last updated: 2026-03-29
