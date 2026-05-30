# TraceLab Agent Playbook

## Hard Operating Rules

**Foundational — preserve this block when customizing the rest of this file.**

**These rules are not optional.**

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work.

### Rule 1 — Think Before Coding

State assumptions explicitly. Ask rather than guess.
Push back when a simpler approach exists. Stop when confused.

### Rule 2 — Simplicity First

Minimum code that solves the problem. Nothing speculative.
No abstractions for single-use code.

### Rule 3 — Surgical Changes

Touch only what you must. Don't improve adjacent code.
Match existing style. Don't refactor what isn't broken.

### Rule 4 — Goal-Driven Execution

Define success criteria. Loop until verified.
Strong success criteria let Claude loop independently.

### Rule 5 — Capture decisions and learnings

Non-trivial choices belong in CMOS. Decisions to `cmos_decisions`, cross-cutting patterns to `cmos_learnings`.
If future-you needs to know why, capture it now.

### Rule 6 — Commit at coherent boundaries

Commit at mission close, sprint close, or day boundary. Per-mission commits only when a sprint surfaces a real bisection need.

### Rule 7 — Surface conflicts, don't average them

If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.

### Rule 8 — Read before you write

Before adding code, read exports, immediate callers, shared utilities.
If unsure why existing code is structured a certain way, ask.

### Rule 9 — Tests verify intent, not just behavior

Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

### Rule 10 — Checkpoint after every significant step

Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.

### Rule 11 — Match the codebase's conventions, even if you disagree

Conformance > taste inside the codebase.
If you think a convention is harmful, surface it. Don't fork silently.

### Rule 12 — Fail loud

"Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped.
Flag uncertainty before stating a fact, statistic, date, or technical detail — never fill gaps with plausible-sounding information.

### Rule 13 — No filler openings

Start with the answer. No "Great question!", "Of course!", "Certainly!", or warmup acknowledgments.

### Rule 14 — Match response length to task

Simple questions get short answers. Complex tasks get full responses.
Don't pad with restatements or closing sentences that repeat what was just said.

---

## Definition-of-Done Checklists

Work-type-specific gates. A mission of the matching type is NOT done until its box is checked. Each rule exists because it was learned the hard way — the incident is named so the gate isn't dropped as ceremony.

### DoD-1 — Published-artifact smoke test (MCP / npm / any installable package)

Before declaring a package mission done, install the *published* artifact in a clean environment and run it end-to-end — not just the local source. Source that passes tests can still crash on a fresh install.
- _Why:_ `@aquex/tracelab-mcp` v1.0.0 shipped a `__dirname` (CJS global) reference that crashed on every fresh ESM install; local runs never hit it. Caught only post-release, forcing the v1.0.1 hotfix.
- _Check:_ `npm pack` → install the tarball in a throwaway dir → run the actual entrypoint/verb once. Grep `src/` for CJS globals (`__dirname`, `__filename`, `require(`) in ESM packages.

### DoD-2 — Env-var deploy verification (any feature reading a new server env var)

Any feature that reads a new environment variable is NOT done until that var is confirmed set in the *deploy* environment AND the live flow is exercised there. A correct dev default silently masks a missing prod value.
- _Why:_ Device-code login (T42.4) shipped without `FRONTEND_URL` set on Railway, so production told users to open `http://localhost:3000/device` — an unusable URL. The dev default was correct; prod just needed the override. Silent because no one ran the full prod login flow.
- _Check:_ Confirm the var is present in the target deploy config (Railway/compose) and run the real flow against the deployed service — not just a local TestClient.

---

## Project Overview
- TraceLab ships a FastAPI + PostgreSQL research platform with RAG pipelines plus the CMOS Mission Protocol workspace under `cmos/` for backlog, telemetry, and agent orchestration.
- The canonical runtime artifacts live at repository root (`app/`, `docs/`, `db/`, `scripts/`, `tests/`, etc.); treat `cmos/` as an internal planning workbench per `cmos/agents.md`.
- CMOS Sprint 8 agentic features are enabled: `agents.md` must load before missions, and the SQLite runtime at `cmos/db/cmos.sqlite` is authoritative for missions, contexts, and sessions.
- All deliverables must preserve parity between PostgreSQL (core app) and SQLite (Mission Protocol) environments; keep file mirrors as read-friendly exports only.

## Build & Development Commands
### Core FastAPI Service
```bash
# Install Python deps (uses pyproject.toml via editable install)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,test]"

# Run locally
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Database migrations
alembic upgrade head

# Compose workflow
docker-compose up -d
docker-compose exec app alembic upgrade head
```

### Dev Container (Recommended)
```bash
# Open in VS Code with Dev Containers extension — auto-builds from .devcontainer/
# Or manually:
docker compose -f docker-compose.dev.yml -f .devcontainer/docker-compose.devcontainer.yml up
```

### Quality Tooling
```bash
# Lint + format
ruff check app/ tests/
ruff format app/ tests/

# Type checking
mypy app/ --config-file pyproject.toml

# Pre-commit hooks (install once)
pre-commit install
```

### Frontend Dependency Management
- After adding or updating frontend dependencies, always run `npm install` inside `frontend/` and commit the updated `package-lock.json` alongside any `package.json` changes.
- Railway (Nixpacks) runs `npm ci` during its install phase, which requires the lock file to be in sync. A stale lock file will fail the build before `buildCommand` even runs.

### MCP Package (`packages/tracelab-mcp/`)
- `packages/*/dist/` is gitignored — build outputs are never committed. A pre-commit hook (`scripts/check_no_mcp_dist.sh`) rejects accidentally-staged dist files.
- After editing `packages/tracelab-mcp/src/`, rebuild before testing locally: `cd packages/tracelab-mcp && npm run build`. The `bin` entry (`dist/index.js`) won't exist on a fresh clone until you build.
- `npm publish` automatically runs `prepublishOnly` → `npm run build`, so the published tarball is always built from current src — no manual step needed at publish time.
- If the MCP appears stale in Claude Desktop, run `npm run build` and restart the client; do not re-add `dist/` to git.
- **MCP tool surface (T41.7 — sprint-41):** 7 action-clustered tools, not the prior ~24 flat ones. Each cluster takes an `action` param plus action-specific keys: `tracelab_search` (knowledge), `tracelab_project` (list/create/update/stats), `tracelab_collection` (list/get/export/create/add/synthesize), `tracelab_report` (create/list/get/export), `tracelab_document` (upload/get_content), `tracelab_mission` (create/list/get/update — CRUD), `tracelab_mission_execution` (submit/status/preview — DS lifecycle). Legacy tool-name calls return a friendly migration error pointing at the new cluster+action. Mapping table and migration error live in `packages/tracelab-mcp/src/index.ts::LEGACY_TO_CLUSTER`.

### Testing
```bash
# Unit tests (no database required)
pytest -m unit -v

# Integration tests (requires Docker for testcontainers)
pytest -m integration -v

# All tests
pytest -v

# Frontend unit tests
cd frontend && npm run test:unit

# Frontend E2E
cd frontend && npx playwright test
```

### Mission Protocol / CMOS Operations
```bash
# Check CMOS database health (recommended before/after missions)
./cmos/cli.py validate health

# View current mission status
./cmos/cli.py db show current

# Seed SQLite from planning workspace (if needed)
python cmos/scripts/seed_sqlite.py --data-root <planning-workspace>

# Run integration guardrails + telemetry updates
node cmos/context/integration_test_runner.js --output telemetry/events/testing-summary.json

# Package starter bundle
./scripts/package_starter.sh
```

## Coding Standards & Style
- **Python**: follow PEP 8 with type hints, pytest fixtures, and lint via `ruff`; keep FastAPI routers thin and push logic into `app/services`.
- **Linting**: `ruff check` enforces E/F/W/I/UP/B/SIM/S rules. Config in `pyproject.toml`.
- **Type checking**: `mypy` with strict mode on `app/core/` and `app/ports/`.
- **TypeScript/Node utilities** (under `cmos/` or tooling scripts): use ES2020 modules, strict TS configs, and JSDoc for exported helpers.
- Keep mission documentation single-sourced: updates to `docs/`, `foundational-docs/`, or `cmos/docs/` must reference the guiding template rather than duplicating content.
- Reference `cmos/docs/AI-coding-assistant-workflows.md` for orchestration expectations and align commit notes with backlog mission IDs.

## Security & Quality Guardrails
- Enforce OWASP controls listed in `cmos/docs/AI-coding-assistant-workflows.md` (no secrets in logs, parameterized DB access, TLS-only external calls).
- Before concluding any mission that touches runtime code, execute `python cmos/scripts/validate_foundational_refs.py` for documentation links and rerun relevant pytest suites (`pytest tests/` or targeted folders).
- Use the tiered validation checklist from `cmos/docs/cmos_Playbook.md`: session events logged, backlog status updated, parity verified, telemetry reviewed.
- Record blockers or deviations inside `cmos/context/MASTER_CONTEXT.json` via the SQLite client (`context/db_client.py`) rather than hand-editing JSON mirrors.

## MCP Contract Guard (sprint-41 codification)

**Any MCP surface change requires a regression test that hits the deployed
verb via the MCP client, not just the server route directly.**

Origin: T40.0 PUT/PATCH 405 incident (sprint-40). Tests with
`client.put` against the FastAPI server passed locally, but DeepSearch's
paid smoke caught the verb mismatch in production because the actual MCP
client was sending PATCH while the route was registered as PUT. Pattern
to mirror: `TestMissionVerbContract` in `tests/test_missions_api.py`.

Apply this rule when changing:
- MCP tool input schema (Python `MISSION_TOOLS` or TS `inputSchema`)
- MCP tool handler dispatch (`handle_*` in `app/mcp_server/tools/` or
  `handle*` in `packages/tracelab-mcp/src/index.ts`)
- The HTTP verb the MCP client uses to talk to FastAPI
- The MCP-emitted response shape (`_serialize_mission`,
  `handleGetMission`, etc.) — see T41.2 incident where the Python
  serializer was fixed but the parallel TS serializer kept stripping
  the same 12 fields.

For the parallel-serializers gap specifically, see the **two MCP
serialization surfaces** note in
[cmos/contracts/mission-authoring-contract.md](cmos/contracts/mission-authoring-contract.md).

## Mission-Authoring Boundary Contract

When changing any mission-authoring field (anything that flows from
`create_mission` / `update_mission` through the contract compiler to
the DeepSearch worker), update
[cmos/contracts/mission-authoring-contract.md](cmos/contracts/mission-authoring-contract.md)
in the same commit. That doc is the single source of truth for the
MCP param ↔ Pydantic field ↔ DB column ↔ REST response field ↔ DS
worker SELECT mapping. Origin: DeepSearch ask in message
`3cf143ee` (T41.3 deliverable).

Related: [cmos/contracts/deepsearch-compiler-vendor.md](cmos/contracts/deepsearch-compiler-vendor.md)
documents the resync ritual for the vendored DS contract compiler at
`app/services/contract_compiler/`.

## Architecture Patterns

### Hexagonal Architecture (Ports & Adapters)
- **Ports** (`app/ports/`): `typing.Protocol` interfaces defining contracts for repositories and external services. New code should depend on ports, not concrete implementations.
- **Adapters** (`app/adapters/`): Thin wrappers delegating to existing services. Repository adapters in `app/adapters/repositories/`, external service adapters in `app/adapters/external/`.
- **Composition root** (`app/dependencies.py`): Factory functions wiring ports to adapters via `FastAPI Depends()`. Override in tests with `app.dependency_overrides`.
- See `docs/adr/001-005` for architecture decision records.

### Dependency Injection Pattern
```python
# In a router:
from app.dependencies import get_document_repository
from app.ports.repositories import DocumentRepository

@router.get("/documents/{doc_id}")
def get_doc(doc_id: UUID, repo: DocumentRepository = Depends(get_document_repository), db: Session = Depends(get_db)):
    return repo.get_document(db, doc_id)
```

### Test Organization
- `tests/unit/` — Mock-based, no DB. Mark with `@pytest.mark.unit`.
- `tests/integration/` — Real PostgreSQL via testcontainers. Mark with `@pytest.mark.integration`.
- `tests/e2e/` — Full-stack browser/API tests.
- TDD workflow: write failing test → confirm fail → minimal code → confirm pass → refactor.

### Core Service Layer
- **Core service**: FastAPI app backed by PostgreSQL 15, Alembic migrations, and ingestion pipelines under `app/services` plus document processing scripts in `scripts/`.
- **Mission orchestration**: SQLite database (`cmos/db/cmos.sqlite`) drives mission backlog, contexts, and telemetry; helpers in `cmos/context/` (mission runtime, SQLite client, integration runner) must be used for reads/writes.
- **RAG assets**: Generated corpora and embeddings live under `data/` and `artifacts/`; keep synthetic data generation reproducible via the scripts in `scripts/`.
- **Packaging**: Starter releases are built from root directories only; the `cmos/` tree provides planning, reports, telemetry timelines, and should never house production app code.

## AI Agent Specific Instructions
1. **Pre-flight**
   - Load this `agents.md`, then `cmos/agents.md` to understand workspace restrictions.
   - Run `./cmos/cli.py validate health` to verify database is accessible; check `./cmos/cli.py db show current` for active missions.
   - Use CMOS MCP tools or CLI for all mission operations—the SQLite database is the single source of truth (flat files like `backlog.yaml` are read-only exports).

2. **Execution**
   - Use `context.db_client.SQLiteClient` or existing automation scripts for all context/session updates (`project_context`, `master_context`, `session_events`).
   - Append mission events via the runtime helper so updates land in both SQLite and `cmos/SESSIONS.jsonl`; include `summary` + `next_hint` per `cmos/docs/AI-coding-assistant-workflows.md`.
   - Keep edits scoped to the active mission; if work exceeds scope, create or split missions through the backlog tooling rather than ad-hoc commits.

3. **Validation & Closure**
   - Execute relevant test suites (`pytest`, targeted `npm run test:*`, integration runner) and record outcomes in telemetry (`telemetry/events/testing-summary.json` or mission-specific files).
   - Run `./cmos/cli.py validate health` to confirm database integrity; update mission status via MCP tools or CLI.
   - Contexts are updated automatically by session completion; no manual JSON file editing required.

4. **Restricted Areas**
   - Do not place application code, generated packages, or new dependencies inside `cmos/`; use the root starter layout. Treat `cmos/` as read-mostly research/history per its local guardrails.
   - Never bypass the SQLite helpers with ad-hoc SQL; if manual inspection is required, prefer `sqlite3 db/cmos.sqlite` read-only queries or the DB Browser workflow in `cmos/docs/sqlite-db-browser-guide.md`.

## Reference Guides
- `README.md` – core TraceLab architecture and developer workflow.
- `cmos/docs/Agentic_Migration_Playbook.md` – agent memory layer expectations.
- `cmos/docs/AI-coding-assistant-workflows.md` & `cmos/docs/cmos_Playbook.md` – orchestration, validation, and telemetry policies.
- `cmos/docs/integration-testing-guide.md`, `cmos/docs/packaging-guide.md`, `cmos/docs/sqlite-*` – test, packaging, and database procedures.
- `foundational-docs/roadmap_template.md` – canonical backlog + milestone template used for every sprint.
- `foundational-docs/tech_arch_template.md` – authoritative technical architecture template for Mission Protocol deliverables.
- `cmos/contracts/mission-authoring-contract.md` – single source of truth for the MCP param ↔ DB column ↔ REST ↔ DS worker mapping (T41.3).
- `cmos/contracts/deepsearch-compiler-vendor.md` – resync ritual for the vendored DeepSearch contract compiler at `app/services/contract_compiler/` (T41.1).

---
Last Updated: 2026-04-27
Version: 2.1.0
Maintained by: TraceLab Platform Team
