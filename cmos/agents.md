# ABOUTME: CMOS v2 context for AI agents working in the TraceLab repo.
# ABOUTME: Use this alongside the root agents.md / CLAUDE.md for application code guidance.

# TraceLab — CMOS Agent Context

## Project

TraceLab is a FastAPI + PostgreSQL research platform with RAG pipelines, document ingestion,
and a React/Vite frontend. The `cmos/` directory is a planning workbench — it does not contain
application code.

**Stack**: Python 3.11+, FastAPI, PostgreSQL 15, Alembic, React/Vite (frontend), SQLite (CMOS)
**Architecture**: Hexagonal — ports (`app/ports/`) define contracts, adapters wire implementations,
composition root in `app/dependencies.py`
**CI**: GitHub Actions — ruff, mypy, pytest, frontend vitest run in parallel gates

---

## Test Commands

```bash
# Unit tests (no DB)
pytest -m unit -v

# Integration tests (requires Docker — testcontainers)
pytest -m integration -v

# Lint + format
ruff check app/ tests/
ruff format app/ tests/

# Type checking
mypy app/ --config-file pyproject.toml

# Frontend unit tests
cd frontend && npm run test:unit

# Frontend E2E
cd frontend && npx playwright test
```

---

## What to Avoid

- Do not place application code inside `cmos/` — it is a planning workbench only
- Do not use the v1 Python CLI (`./cmos/cli.py`) or `cmos/context/mission_runtime.py` — use MCP tools below
- Do not edit `cmos/db/cmos.sqlite` directly — use MCP tools
- Do not edit `cmos/context/master_context.json` or `project_context.json` by hand
- Do not bypass hexagonal boundaries: routers call services, services call ports, adapters implement ports
- Do not commit `cmos/db/cmos.sqlite` — it is gitignored

---

## CMOS v2 Operations (MCP Tools)

This instance uses **cmos-mcp v2** (SQLite schema 2.0). All mission and session operations go
through MCP tools — not the Python CLI from the old v1 setup.

**Project root**: `/home/birch/Code/TraceLab`

### Key tools

```
cmos_project action=list                          # list registered instances
cmos_mission_list projectRoot=<root>              # list missions (filter by status/sprint)
cmos_mission_show missionId=<id> projectRoot=...  # show a single mission
cmos_mission_start missionId=<id> projectRoot=... # Queued → In Progress
cmos_mission_complete missionId=<id> notes=...    # In Progress → Completed
cmos_mission_block missionId=<id> reason=...      # → Blocked
cmos_session_start type=<build|research|...>      # open a session
cmos_session_capture content=... type=...         # log a decision/finding
cmos_session_complete summary=...                 # close the session
cmos_sprint_list projectRoot=...                  # list sprints
cmos_context_view projectRoot=...                 # current project context
cmos_context_snapshot projectRoot=...             # take a context snapshot
```

### Current sprint

**sprint-tl-01** — Stabilize and Bootstrap
Focus: migrate from v1 CMOS to v2, establish clean test baseline, surface active work in the
instance network.

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

---

## Boundary

CMOS manages: missions, sprints, sessions, context snapshots
CMOS does NOT contain: application code, migrations, routers, services, tests for the app

Last updated: 2026-03-29
