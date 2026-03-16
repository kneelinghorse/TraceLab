# TraceLab Agent Playbook

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

---
Last Updated: 2026-03-16
Version: 2.0.0
Maintained by: TraceLab Platform Team
