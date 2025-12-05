# CMOS Starter

CMOS (Context + Mission Orchestration System) is a lightweight starter kit for teams that want to run Mission Protocol projects with high confidence. It provides a ready-to-ship repository structure, batteries-included automation, and security guardrails so human developers and AI agents can collaborate through mission-driven workflows.

---

## What's New in v2.1

**🎯 Mission Memory System**
- Full mission specs stored in database (objective, context, successCriteria, deliverables, domainFields)
- Query missions with `./cmos/cli.py mission show <id>` - no file exports needed
- `mission_details` view for easy inspection in your DB app

**📜 Strategic Decision Timeline**
- `strategic_decisions` table indexes decisions from MASTER_CONTEXT for powerful querying
- Search decisions: `./cmos/cli.py decisions search "PostgreSQL"`
- List by domain: `./cmos/cli.py decisions list --domain ai-studio`
- Hybrid approach: JSON blob stays simple for agents, SQL queries for analysis

**📸 Context Snapshot System**
- Historical timeline of MASTER_CONTEXT changes at strategic milestones
- Take snapshots: `./cmos/cli.py context snapshot master --source "Sprint 03 completed"`
- View history: `./cmos/cli.py context history master`
- View any past state: `./cmos/cli.py context view <snapshot-id>`

**📊 Sprint Retrospectives**
- `sprint_summary` view aggregates missions, decisions, completion rates per sprint
- Query: `SELECT * FROM sprint_summary WHERE sprint_id='sprint-03'`

---

## What You Get

- **Mission Protocol alignment** – Build/Research mission templates, domain packs, and worker manifests wired for RSIP, delegation, and boomerang orchestration patterns.
- **Agent-ready guidance** – A comprehensive `agents.md` contract plus empty context files that teams can populate with their own history.
- **Guardrails & validation** – Security, quality, and integration harnesses (JavaScript + Python) that enforce OWASP guidance and regression testing.
- **SQLite canonical store** – Schema, seed script, and health validation commands. SQLite is the canonical source of truth; export file mirrors on-demand.
- **Queryable project memory** – Strategic decisions, mission specs, and context snapshots fully searchable via SQL or CLI.
- **Packaging workflow** – Automation to produce distributable starter archives without leaking local tooling artefacts.

---

## Prerequisites

- **Node.js** 20.x (tooling, tests, optional automation)
- **Python** 3.11+ (SQLite utilities and validation scripts)
- **npm** (for running the provided scripts and test suites)

Optional:
- SQLite client (CLI or GUI) if you plan to inspect `cmos/db/cmos.sqlite`
- Git (recommended for version control)

---

## Quick Start

### For New Projects

**Complete setup guide**: See `cmos/docs/getting-started.md`

**Quick version**:
```bash
# 1. Install dependencies
pip install PyYAML

# 2. Initialize database
python cmos/scripts/seed_sqlite.py

# 3. Create your project agents.md
cp cmos/templates/agents.md ./agents.md
# Edit with your project details

# 4. Create foundational docs
cp cmos/foundational-docs/roadmap_template.md <docs-dir>/roadmap.md
cp cmos/foundational-docs/tech_arch_template.md <docs-dir>/technical_architecture.md
# Complete both documents

# 5. Create your first backlog
# Use the CLI to add missions (auto-syncs backlog.yaml)
./cmos/cli.py mission add B1.1 "Bootstrap runtime" --sprint "Sprint 01" --description "Set up mission database"
# or edit cmos/missions/backlog.yaml manually and seed again later

# 6. Start building!
# See cmos/docs/build-session-prompt.md
```

### For Existing Users

```bash
# View current work
./cmos/cli.py db show current

# Start a build session
# See cmos/docs/build-session-prompt.md

# Export backlog after work
./cmos/cli.py db export backlog
```

---

## Working With Mission Protocol

The starter is designed to plug directly into Mission Protocol v2 workflows.

- **Mission templates**: Use the YAML files under `cmos/missions/templates/` as starting points for Build, Research, and Planning missions. Each template includes orchestration configuration and structured prompting scaffolds.
- **Mission execution**: Use `./cmos/cli.py mission [status|start|complete|block|add|update|depends]` to manage the mission queue and backlog data. The CLI keeps `cmos/missions/backlog.yaml`, `cmos/SESSIONS.jsonl`, and the SQLite mirror in sync automatically.
- **Research exports**: After completing a research mission, run `./cmos/cli.py research export <mission-id>` to generate `cmos/research/<mission-id>.md`. Only commit the exported Markdown; the database remains the source of truth.
- **Worker delegation**: Additional workers live in `cmos/workers/`. Update `cmos/workers/manifest.yaml` to register new delegates and reference them within mission templates.
- **Advanced orchestration**: The starter ships with RSIP, delegation, and boomerang patterns wired into mission templates. Adjust `cmos/runtime/` assets to tweak checkpoints or iteration policies.

When integrating with a Mission Protocol server, point it at this repository’s root. The starter already conforms to the required directory structure and schema expectations.

### Backlog Management CLI

Use mission commands to edit backlog data without hand-editing YAML. Each command persists to SQLite first and automatically regenerates `cmos/missions/backlog.yaml` so files mirror the database.

```bash
# Add a mission with metadata
./cmos/cli.py mission add B3.8 "Document research flow" --sprint "Sprint 03" \
  --description "Capture research export workflow" \
  --success "Export command documented" --deliverable "Guide published"

# Update status and notes
./cmos/cli.py mission update B3.8 --status "Current" --notes "Ready for research delegate"

# Record dependency (Blocks by default)
./cmos/cli.py mission depends B3.3 B3.8 --type "Blocks"
```

---

## Optional SQLite Runtime
 
SQLite is the canonical source of truth. Generate file mirrors on-demand when you need human-friendly views.

- **Generate a database**  
  ```bash
  python cmos/scripts/seed_sqlite.py
  ```
  This applies `cmos/db/schema.sql`, creates `cmos/db/cmos.sqlite`, and imports:
  - Mission YAML files from `missions/sprint-XX/` folders (full specs)
  - Contexts from `PROJECT_CONTEXT.json` and `MASTER_CONTEXT.json`
  - Strategic decisions extracted from MASTER_CONTEXT
  - Session history from `SESSIONS.jsonl`
  - Backlog data from `missions/backlog.yaml`

- **Validate database health**  
  ```bash
  ./cmos/cli.py validate health
  ```
  Confirms that mission runtime can reach the SQLite database and log telemetry.

- **Environment variables**  
  ```
  NODE_ENV=development
  DEBUG=true
  DB_PATH=cmos/db/cmos.sqlite
  ```
  Adjust `DB_PATH` if you embed the starter into another deployment layout.

---

## Repository Tour

- `agents.md` – Canonical instructions for AI collaborators (read this first).
- `context/` – Master context template and validation utilities (`integration_test_runner.js`, `security_validation.js`, `quality_assurance.js`, SQLite helpers).
- `missions/` – Mission templates plus an empty `backlog.yaml` scaffold.
- `research/` – Markdown artifacts exported from completed research missions via the CLI.
- `templates/` – Mission Protocol domain packs ready for import.
- `workers/` – Worker definitions and manifest used by delegation patterns.
- `runtime/` – Assets for boomerang checkpoints and orchestration state.
- `scripts/` – Automation (`seed_sqlite.py`, legacy helpers, `package_starter.sh`, etc.).
- `telemetry/` – Event schemas and sample JSONL streams for monitoring.
- `tests/` – Guardrail fixtures for integration, security, quality, performance, and backward compatibility.
- `foundational-docs/` – Roadmap and technical architecture templates to clone into your own documentation.
- `db/` – SQLite schema and generated database artefacts.

---

## Automation & Tooling

### Unified CLI (`cmos/cli.py`)

The CLI provides comprehensive commands for mission lifecycle, context management, and project memory queries:

**Mission Commands:**
- `mission status` - Show active missions queue
- `mission show <id>` - Display full mission specification
- `mission start/complete/block <id>` - Lifecycle operations
- `mission add/update/depends` - Backlog management

**Context & Memory Commands:**
- `context snapshot master` - Take strategic snapshot
- `context history master` - View snapshot timeline
- `decisions list/search/by-sprint` - Query strategic decisions

**Database Commands:**
- `db show backlog/current` - View mission state
- `db export backlog/contexts/missions` - Generate file exports

**Validation Commands:**
- `validate health` - Database connectivity check
- `validate docs` - Documentation reference validation

### Scripts

| Script | Description |
| ------ | ----------- |
| `cmos/scripts/seed_sqlite.py` | Imports mission YAMLs, backlog, and contexts into database. Auto-scans `sprint-XX/` folders. |
| `cmos/scripts/migrate_sprint_yaml_to_db.py` | Migrates mission YAML files from sprint folders into database when agents write to files instead of DB. |
| `cmos/scripts/migrate_cmos_memory.py` | Migrates data from legacy CMOS systems (flat files or old databases). |
| `cmos/scripts/validate_foundational_refs.py` | Ensures documentation references target `foundational-docs/`. |
| `cmos/scripts/package_starter.sh` | Produces distributable `cmos-starter-<UTC>.tar.gz` bundle. |
| `cmos/scripts/reset_starter.sh` | Resets CMOS to clean state for distribution. |
| `cmos/scripts/mission_runtime.py` | Legacy mission lifecycle helper (still available for automation). |
| `cmos/scripts/db_tools.py` | Legacy database utilities (automation helpers for exports). |

---

## Testing & Guardrails

- **JavaScript test suites** – Run via Node directly (no npm install required):
  - Integration runner:
    ```bash
    node cmos/context/integration_test_runner.js --manifest cmos/tests/integration/test_manifest.json
    ```
  - Show help:
    ```bash
    node cmos/context/integration_test_runner.js --help
    ```
- **Security validation** – `context/security_validation.js` scans mission outputs and fixtures against OWASP-aligned rules.
- **Quality assurance** – `context/quality_assurance.js` reviews generated code for common pitfalls.
- **Integration harness** – `context/integration_test_runner.js` orchestrates the full guardrail suite.
- **Telemetry** – Append-only logs under `telemetry/events/` capture mission runtime results and database health checks (`telemetry/events/database-health.jsonl`).

Keep coverage above 80% and run guardrails whenever missions modify runtime assets, orchestration scripts, or security-sensitive templates.

---

## Packaging & Distribution

Create a distributable archive with:

```bash
./cmos/scripts/package_starter.sh
```

The script normalises from cmos root, strips transient artefacts, and produces a tarball in `cmos/dist/`. Share the archive with downstream teams or automation pipelines to bootstrap new Mission Protocol projects quickly.

---

## Documentation

**Complete workflow**: See `cmos/docs/user-manual.md` for the full process from installation to ongoing operations.

**Quick guides**:
- **Getting Started**: `cmos/docs/getting-started.md` - Day 0 setup
- **Operations**: `cmos/docs/operations-guide.md` - Daily operations reference
- **Build Sessions**: `cmos/docs/build-session-prompt.md` - Mission execution loops
- **agents.md Guide**: `cmos/docs/agents-md-guide.md` - Writing effective AI instructions
- **Migration**: `cmos/docs/legacy-migration-guide.md` - Import from legacy CMOS
- **Schema**: `cmos/docs/sqlite-schema-reference.md` - Database queries and structure

**Critical concept**: CMOS is project management. Your application code lives in project root, NOT in cmos/.

---

## Key Principles

1. **Database First** - `cmos/db/cmos.sqlite` is single source of truth, export files on-demand
2. **Queryable Memory** - Mission specs, strategic decisions, and context history fully searchable
3. **Minimal Backlog** - Keep `backlog.yaml` small (current work only), DB has full history
4. **Strategic Snapshots** - Capture MASTER_CONTEXT at milestones, maintain decision timeline
5. **Two agents.md Files** - One for your code (`project-root/agents.md`), one for CMOS operations (`cmos/agents.md`)
6. **Clear Boundaries** - Never write application code in cmos/
7. **Export When Needed** - Generate file views via `./cmos/cli.py db export [backlog|contexts|missions]`

---

For questions or improvements, update the starter locally and regenerate the archive with `./cmos/scripts/package_starter.sh`.
