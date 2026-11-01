# Getting Started with CMOS

**Day 0 Setup**: From fresh CMOS installation to ready-to-build project.

---

## What is CMOS?

**CMOS** (Context + Mission Orchestration System) is a project management layer for AI-assisted development. It provides:

- 📊 **SQLite-backed mission tracking** - History, sprints, dependencies
- 📝 **Context management** - PROJECT_CONTEXT, MASTER_CONTEXT with snapshots
- 🎯 **Mission-based workflow** - Research → Plan → Build → Ship
- 🔄 **Session management** - Capture planning, onboarding, reviews, and build sessions
- ✅ **Validation guardrails** - Keep code and management in sync

**Critical Principle**: CMOS is **project management**, NOT your application code. Keep them separate!

---

## Installation

### Option 1: Extract Starter Archive
```bash
# Extract CMOS starter into your project
tar -xzf cmos-starter-TIMESTAMP.tar.gz
mv cmos-starter/ yourproject/rbook/
```

### Option 2: Clone from Repository
```bash
# Clone CMOS into your project
git clone <cmos-repo-url> yourproject/rbook/
```

**Result**: You now have a `rbook/` subdirectory for project management.

---

## Setup Process (5 Steps)

### Step 1: Install Dependencies

```bash
# From project root
cd yourproject

# Python dependencies (required)
pip install PyYAML

# Node scripts (optional, for testing)
# No npm install required; run Node tools directly when needed
# Example:
node rbook/context/integration_test_runner.js --help
```

**Verify**:
```bash
python --version  # Should be 3.11+
python -c "import yaml"  # Should not error
```

---

### Step 2: Initialize Database

Create the SQLite database:

```bash
# From project root
python rbook/scripts/seed_sqlite.py
```

**What this does**:
- Applies the schema to create `rbook/db/rbook.sqlite`
- Imports mirrors if present (contexts, backlog, sessions, telemetry, prompt mappings)
- Ready for your first mission

**Verify**:
```bash
ls -lh rbook/db/rbook.sqlite
# Should show newly created database file
```

---

### Step 3: Set Up Project Boundaries

Create `.gitignore` at project root to exclude CMOS runtime data:

```bash
# Add to .gitignore (or create new file)
cat >> .gitignore << 'EOF'

# CMOS Runtime Data (exclude from version control)
rbook/db/rbook.sqlite
rbook/SESSIONS.jsonl
rbook/dist/
rbook/telemetry/events/*.jsonl
rbook/runtime/boomerang/
rbook/**/__pycache__/
EOF
```

**What to version control**:
- ✅ `rbook/agents.md` - CMOS operational guidance
- ✅ `rbook/missions/backlog.yaml` - Current sprint plan (minimal)
- ✅ `rbook/PROJECT_CONTEXT.json` - Project metadata (zero out secrets)
- ✅ `rbook/scripts/` - All scripts
- ✅ `rbook/docs/` - All documentation

**What to exclude**:
- ❌ `rbook/db/rbook.sqlite` - Runtime database (regenerate from files)
- ❌ `rbook/SESSIONS.jsonl` - Session logs (personal)
- ❌ `rbook/dist/` - Build artifacts
- ❌ `rbook/telemetry/` - Runtime metrics

---

### Step 4: Create Project-Specific agents.md Files

**CRITICAL**: You need TWO separate agents.md files!

#### 4a. Create Project Root agents.md (YOUR APPLICATION)

```bash
# Copy template to project root
cp rbook/templates/agents.md ./agents.md

# Edit it with YOUR project details
nano agents.md  # or your preferred editor
```

**Customize with**:
- Your project name, tech stack, framework
- Your build commands (npm start, pytest, etc.)
- Your coding standards and style guides
- Your test requirements
- Your deployment process

**Example**:
```markdown
# AI Agent Configuration

## Project Overview
**Project Name**: TraceLab UX Research API
**Project Type**: Web API
**Primary Language**: Python
**Framework**: FastAPI + PostgreSQL + Qdrant

## Build & Development Commands
npm start  # Start dev server
pytest tests/  # Run tests
```

**This file guides agents when working on YOUR APPLICATION CODE**.

#### 4b. Review rbook/agents.md (CMOS OPERATIONS)

`rbook/agents.md` already exists for CMOS operations. It tells agents:
- How to work with missions and sprints
- How to use the database
- CMOS-specific rules

**Don't edit this for YOUR project code** - it's for CMOS management only!

**Critical Boundary**:
- 📁 **project-root/agents.md** → Instructions for `src/`, `tests/`, YOUR CODE
- 📁 **rbook/agents.md** → Instructions for missions, contexts, CMOS operations

---

### Step 5: Create Foundational Documents

Copy templates and customize for YOUR project:

```bash
# Copy templates to project root
cp rbook/foundational-docs/roadmap_template.md ./docs/roadmap.md
cp rbook/foundational-docs/tech_arch_template.md ./docs/technical_architecture.md

# Create docs directory if needed
mkdir -p docs
```

**Customize each**:

**docs/roadmap.md**:
- Your project vision and goals
- Sprint breakdown (what you'll build when)
- Success metrics and milestones

**docs/technical_architecture.md**:
- System design and components
- Tech stack decisions and rationale
- API design, data models, infrastructure
- Security and performance considerations

**These documents guide your entire build process**.

---

## Project Structure After Setup

```
yourproject/                      # Project root
├── README.md                     # About YOUR PROJECT
├── agents.md                     # AI instructions for YOUR CODE
├── .gitignore                    # Excludes CMOS runtime data
│
├── src/                          # YOUR APPLICATION CODE
├── tests/                        # YOUR APPLICATION TESTS
├── docs/
│   ├── roadmap.md                # YOUR PROJECT ROADMAP
│   └── technical_architecture.md # YOUR TECHNICAL DESIGN
│
└── rbook/                         # PROJECT MANAGEMENT (separate!)
    ├── agents.md                 # AI instructions for CMOS operations
    ├── db/rbook.sqlite            # Mission tracking database
    ├── missions/backlog.yaml     # Current sprints/missions
    ├── PROJECT_CONTEXT.json      # Project metadata
    ├── context/MASTER_CONTEXT.json  # Project history
    ├── SESSIONS.jsonl            # Session logs
    ├── research/                 # Exported research reports (Markdown)
    ├── scripts/                  # CMOS automation
    └── docs/                     # CMOS documentation
```

**Golden Rule**: 
- ✅ Write YOUR CODE in project root
- ✅ Manage YOUR WORK in rbook/
- ❌ NEVER write code in rbook/
- ❌ NEVER write missions in src/

---

## MCP Setup (Recommended for AI Agents)

CMOS includes an MCP (Model Context Protocol) server that provides direct database access for AI agents. This is the recommended interface for agent-native workflows.

### Configure MCP Server

Add the CMOS MCP server to your Claude configuration:

**For Claude Desktop** (`~/.claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "cmos-mcp": {
      "command": "npx",
      "args": ["-y", "@anthropic/cmos-mcp"],
      "env": {
        "CMOS_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

**For Claude Code** (`.claude/settings.json` in project root):
```json
{
  "mcpServers": {
    "cmos-mcp": {
      "command": "npx",
      "args": ["-y", "@anthropic/cmos-mcp"]
    }
  }
}
```

### Verify MCP Connection

Once configured, verify the MCP server is working:

```
# In Claude conversation
cmos_db_health()
```

Should return database stats including table counts and connection status.

### MCP vs CLI

| Use Case | Recommended Interface |
|----------|----------------------|
| AI agent workflows | **MCP** - Direct database access, no shell needed |
| Human operators | **CLI** - Familiar command-line interface |
| Automation scripts | **CLI** or **Python API** - Scriptable |
| Quick debugging | **CLI** - Easy to run from terminal |

**MCP Advantages:**
- No shell command execution needed
- Structured JSON responses
- Optimized for agent context windows
- Direct database operations

See `rbook/docs/mcp-reference.md` for complete MCP tool documentation.

---

## Verification Checklist

After setup, verify everything works:

```bash
# From project root

# 1. Database is accessible
./rbook/cli.py db show current
# Should show: "Active mission not set in project context."

# 2. Database health check works
./rbook/cli.py validate health
# Should show: "Database rbook/db/rbook.sqlite is reachable and passed health checks."

# 3. Check database
./rbook/cli.py db show backlog
# Should show: "No sprints defined in the database."

# 4. Both agents.md files exist
ls -la agents.md rbook/agents.md
# Both should exist
```

✅ **If all checks pass, you're ready to plan your first sprint!**

---

## Next Steps

### Phase 1: Foundation (Planning)

1. **Complete your foundational documents**:
   - Fill out `docs/roadmap.md` with your project vision
   - Fill out `docs/technical_architecture.md` with system design
   - Define Sprint 1 deliverables in both docs

2. **Create your first backlog**:
   - Use the CLI (recommended): `./rbook/cli.py mission add <id> "<name>" --sprint "Sprint 01"`
   - Update priorities with `mission update` and link work with `mission depends`
   - Prefer CLI commands because they update SQLite and regenerate `rbook/missions/backlog.yaml` automatically
   - Manual editing of `rbook/missions/backlog.yaml` still works, but remember to re-seed afterward

3. **Seed the database**:
   ```bash
   python rbook/scripts/seed_sqlite.py
   ```
   This imports your backlog into SQLite.

### Phase 2: Build Execution

1. **Start a build session** using `rbook/docs/build-session-prompt.md`
2. **Run missions in a loop** (3-10 per session is typical)
3. **Validate after each mission**
4. **Review progress** in database
5. **Capture research outputs** with `./rbook/cli.py research export <mission-id>` to write `rbook/research/<mission-id>.md`

### Phase 3: Sprint Closure

1. **Review completed missions**
2. **Update minimal backlog** (remove completed sprint from YAML)
3. **Plan next sprint**
4. **Continue cycle**

---

## Common Pitfalls

❌ **DON'T**: Write application code in `rbook/`
- rbook/ is for project management only
- Your code belongs in `src/`, `app/`, or similar

❌ **DON'T**: Create tests in `rbook/tests/`
- Those are CMOS validation tests
- Your app tests belong in project-root `tests/`

❌ **DON'T**: Put both agents.md files in same location
- Project root: YOUR CODE instructions
- rbook/: CMOS operations instructions

❌ **DON'T**: Version control the database
- Database is regenerated from backlog.yaml
- Add `rbook/db/rbook.sqlite` to .gitignore

✅ **DO**: Keep boundaries clear
✅ **DO**: Use database as history store
✅ **DO**: Keep backlog.yaml minimal (current work)
✅ **DO**: Validate database health regularly

---

## Quick Reference

### MCP Tools (Recommended for AI Agents)

| Task | MCP Tool |
|------|----------|
| Agent onboarding | `cmos_agent_onboard()` |
| Database health | `cmos_db_health()` |
| View work queue | `cmos_mission_status()` |
| Create sprint | `cmos_sprint_add(sprintId, title, ...)` |
| List sprints | `cmos_sprint_list()` |
| Create mission | `cmos_mission_add(missionId, name, sprintId, ...)` |
| Start mission | `cmos_mission_start(missionId)` |
| Complete mission | `cmos_mission_complete(missionId, notes)` |
| Start session | `cmos_session_start(type, title)` |
| Capture insight | `cmos_session_capture(category, content)` |
| Complete session | `cmos_session_complete(summary)` |
| Take snapshot | `cmos_context_snapshot(contextType, source)` |
| Search decisions | `cmos_decisions_search(query)` |

### CLI Commands (For Human Operators)

| Task | Command |
|------|---------|
| Initialize database | `python rbook/scripts/seed_sqlite.py` |
| View current mission | `./rbook/cli.py db show current` |
| View all sprints | `./rbook/cli.py db show backlog` |
| Add backlog mission | `./rbook/cli.py mission add <id> "<name>" --sprint "<sprint>"` |
| Update mission status | `./rbook/cli.py mission update <id> --status "<status>"` |
| Add dependency | `./rbook/cli.py mission depends <from> <to> --type "Blocks"` |
| Export research report | `./rbook/cli.py research export <id>` |
| Snapshot MASTER_CONTEXT | `./rbook/cli.py context snapshot master --source "<milestone>"` |
| View context history | `./rbook/cli.py context history master` |
| View specific snapshot | `./rbook/cli.py context view <snapshot-id>` |
| Start session | `./rbook/cli.py session start --type <type> --title "<title>"` |
| Capture session insight | `./rbook/cli.py session capture <category> "<content>"` |
| Complete session | `./rbook/cli.py session complete --summary "<summary>"` |
| Onboard agent | `./rbook/cli.py session onboard` |
| Validate sync | `./rbook/cli.py validate health` |
| Start build session | See `rbook/docs/build-session-prompt.md` |

---

## Getting Help

- **MCP tools reference**: See `rbook/docs/mcp-reference.md`
- **Setup issues**: Check `rbook/docs/operations-guide.md`
- **Session management**: See `rbook/docs/session-management-guide.md`
- **Migration from legacy**: See `rbook/docs/legacy-migration-guide.md`
- **Database queries**: See `rbook/docs/sqlite-schema-reference.md`
- **Build sessions**: See `rbook/docs/build-session-prompt.md`
- **agents.md help**: See `rbook/docs/agents-md-guide.md`

---

**Last Updated**: 2025-12-10
**Status**: Ready for use (MCP-enabled)
**Next**: Complete foundational docs, create backlog, start building!
