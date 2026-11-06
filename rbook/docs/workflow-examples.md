# CMOS Workflow Examples

**Practical examples showing how sessions and missions work together across the project lifecycle.**

---

## Overview

CMOS supports two complementary workflows:

1. **Session Management** - For planning, onboarding, reviews, research (non-build work)
2. **Mission Execution** - For implementing features, writing code, building (structured build work)

This guide shows how to combine both for maximum productivity.

**Interface Options:**
- **MCP** (Recommended for AI agents) - Direct database access, structured responses
- **CLI** (For human operators) - Command-line interface
- **Python API** (For automation) - Programmatic access

Examples below show both MCP and CLI approaches.

---

## Example 1: Starting a New Project

### Step 1: Foundation Planning Session

**MCP Approach (Recommended for AI Agents):**
```
# Start a planning session
cmos_session_start(type="planning", title="Sprint 01 Planning", sprintId="sprint-01")

# Capture decisions during planning
cmos_session_capture(category="decision", content="Use PostgreSQL for data persistence")
cmos_session_capture(category="decision", content="FastAPI for REST API framework")
cmos_session_capture(category="constraint", content="Must deploy on AWS within 2 weeks")
cmos_session_capture(category="next-step", content="Define database schema")
cmos_session_capture(category="next-step", content="Set up CI/CD pipeline")
cmos_session_capture(category="next-step", content="Implement authentication")

# Complete the session
cmos_session_complete(summary="Sprint 01 scoped: 8 missions covering infrastructure and core API")
```

**CLI Approach:**
```bash
./rbook/cli.py session start --type planning --title "Sprint 01 Planning" --sprint "Sprint 01"
./rbook/cli.py session capture decision "Use PostgreSQL for data persistence"
./rbook/cli.py session capture decision "FastAPI for REST API framework"
./rbook/cli.py session capture constraint "Must deploy on AWS within 2 weeks"
./rbook/cli.py session capture next-step "Define database schema"
./rbook/cli.py session capture next-step "Set up CI/CD pipeline"
./rbook/cli.py session capture next-step "Implement authentication"
./rbook/cli.py session complete --summary "Sprint 01 scoped: 8 missions covering infrastructure and core API"
```

**What happened:**
- Decisions automatically added to `master_context.decisions_made[]`
- Next steps available in `project_context.working_memory.next_steps[]`
- Session timeline preserved in database

### Step 2: Convert Planning to Missions

**MCP Approach:**
```
# First, create the sprint
cmos_sprint_add(sprintId="sprint-01", title="Sprint 01 - Infrastructure", focus="Core infrastructure and API foundation")

# Add missions
cmos_mission_add(missionId="B1.1", name="Database Schema Design", sprintId="sprint-01", objective="Design and implement PostgreSQL schema")
cmos_mission_add(missionId="B1.2", name="CI/CD Pipeline Setup", sprintId="sprint-01", objective="Configure GitHub Actions for deployment")
cmos_mission_add(missionId="B1.3", name="User Authentication", sprintId="sprint-01", objective="Implement JWT-based auth with FastAPI")

# Define dependencies
cmos_mission_depends(fromId="B1.3", toId="B1.1", type="Requires")

# Verify
cmos_sprint_show(sprintId="sprint-01")
```

**CLI Approach:**
```bash
./rbook/cli.py mission add B1.1 "Database Schema Design" --sprint "Sprint 01"
./rbook/cli.py mission add B1.2 "CI/CD Pipeline Setup" --sprint "Sprint 01"
./rbook/cli.py mission add B1.3 "User Authentication" --sprint "Sprint 01"
./rbook/cli.py mission depends B1.1 B1.3 --type "Blocks"
./rbook/cli.py db show backlog
```

### Step 3: Execute Build Session

**MCP Approach:**
```
# Check work queue
cmos_mission_status()

# Start first mission
cmos_mission_start(missionId="B1.1")

# ... do work ...

# Complete mission
cmos_mission_complete(missionId="B1.1", notes="Schema implemented with user, session, and audit tables")

# Next mission auto-available
cmos_mission_status()
```

**In the build session, the agent:**
1. Calls `cmos_mission_status()` to see the queue
2. Calls `cmos_mission_start(missionId)` to mark it In Progress
3. Implements the feature
4. Calls `cmos_mission_complete(missionId, notes)` with notes
5. Moves to next mission automatically

---

## Example 2: Mid-Sprint Research Spike

**Scenario**: You need to evaluate authentication options before continuing.

### Step 1: Start Research Session

```bash
# Pause build work, start research session
./rbook/cli.py session start --type research --title "Auth library evaluation"

# Capture findings as you research
./rbook/cli.py session capture learning "Passport.js requires Express, not compatible with FastAPI"
./rbook/cli.py session capture learning "FastAPI-Users provides built-in OAuth2 support"
./rbook/cli.py session capture decision "Use FastAPI-Users for authentication"
./rbook/cli.py session capture context "Need JWT token expiry of 24 hours for UX"

# Complete with recommendation
./rbook/cli.py session complete --summary "Evaluated 3 auth libraries, selected FastAPI-Users" \
  --next-steps "Update B1.3 mission with FastAPI-Users implementation"
```

### Step 2: Update Mission with Research Findings

```bash
# Update the blocked mission with your decision
./rbook/cli.py mission update B1.3 --status "Current" \
  --notes "Using FastAPI-Users per research session PS-2024-11-13-002"
```

### Step 3: Resume Build

```bash
# Continue with build session
# Agent will pick up B1.3 with updated context
```

---

## Example 3: Sprint Review and Next Sprint Planning

**Scenario**: Sprint 01 is complete, time to review and plan Sprint 02.

### Step 1: Review Session

```bash
# Start review session
./rbook/cli.py session start --type review --title "Sprint 01 Retrospective"

# Capture learnings
./rbook/cli.py session capture learning "Database migrations need better automation"
./rbook/cli.py session capture learning "CI/CD pipeline saved 2 hours per deploy"
./rbook/cli.py session capture constraint "Performance tests must run under 5 minutes"

# Complete review
./rbook/cli.py session complete --summary "Sprint 01: Delivered core infrastructure, identified migration pain points"
```

### Step 2: Take Context Snapshot

```bash
# Create a milestone snapshot
./rbook/cli.py context snapshot master --source "Sprint 01 completion - infrastructure ready"
```

### Step 3: Plan Next Sprint

```bash
# Start planning for Sprint 02
./rbook/cli.py session start --type planning --title "Sprint 02 Planning" --sprint "Sprint 02"

# Define new objectives
./rbook/cli.py session capture decision "Focus on user-facing features in Sprint 02"
./rbook/cli.py session capture next-step "Implement user registration endpoint"
./rbook/cli.py session capture next-step "Add profile management"
./rbook/cli.py session capture next-step "Build search functionality"

# Complete planning
./rbook/cli.py session complete --summary "Sprint 02 scoped: 6 missions for user features"
```

### Step 4: Create Sprint 02 Backlog

```bash
# Add new missions
./rbook/cli.py mission add B2.1 "User Registration Endpoint" --sprint "Sprint 02"
./rbook/cli.py mission add B2.2 "User Profile Management" --sprint "Sprint 02"
./rbook/cli.py mission add B2.3 "Search Implementation" --sprint "Sprint 02"

# Seed database
python rbook/scripts/seed_sqlite.py
```

---

## Example 4: Onboarding a New Agent

**Scenario**: Starting a new session, agent needs to understand current state.

### Step 1: Quick Onboarding

**MCP Approach (Recommended):**
```
# Get comprehensive context in one call
cmos_agent_onboard()
```

Returns:
- Project identity and current sprint
- Active/blocked missions
- Recent decisions
- Suggested next actions

**CLI Approach:**
```bash
./rbook/cli.py session onboard
```

### Step 2: Start Onboarding Session

**MCP Approach:**
```
cmos_session_start(type="onboarding", title="Onboarding for search feature")

cmos_session_capture(category="context", content="Search must support full-text across user profiles")
cmos_session_capture(category="context", content="Elasticsearch already provisioned in AWS")
cmos_session_capture(category="decision", content="Use Elasticsearch Python client")

cmos_session_complete(
  summary="Onboarded to search implementation",
  nextSteps=["Review Elasticsearch docs", "Start mission B2.3"]
)
```

**CLI Approach:**
```bash
./rbook/cli.py session start --type onboarding --title "Onboarding for search feature"
./rbook/cli.py session capture context "Search must support full-text across user profiles"
./rbook/cli.py session capture context "Elasticsearch already provisioned in AWS"
./rbook/cli.py session capture decision "Use Elasticsearch Python client"
./rbook/cli.py session complete --summary "Onboarded to search implementation" \
  --next-steps "Review Elasticsearch docs" \
  --next-steps "Start mission B2.3"
```

### Step 3: Begin Work

**MCP Approach:**
```
# Check available missions
cmos_mission_status()

# Start the mission
cmos_mission_start(missionId="B2.3")
```

---

## Example 5: Handling Blockers

**Scenario**: Mission blocked on external dependency.

### During Build Session

```python
# In Python runtime, when blocker discovered:
from context.mission_runtime import block

block(
    mission_id="B2.3",
    agent="assistant", 
    summary="Blocked on Elasticsearch credentials",
    reason="AWS Elasticsearch instance not accessible",
    needs=["Request AWS credentials from DevOps", "Update environment variables"]
)
```

### Check-in Session

```bash
# Quick check-in to document blocker resolution
./rbook/cli.py session start --type check-in --title "Elasticsearch access resolved"

./rbook/cli.py session capture context "Received AWS creds from DevOps team"
./rbook/cli.py session capture next-step "Update .env with new credentials"
./rbook/cli.py session capture next-step "Resume mission B2.3"

./rbook/cli.py session complete --summary "Blocker resolved, ready to continue"
```

### Resume Mission

```bash
# Update mission status
./rbook/cli.py mission update B2.3 --status "Current" \
  --notes "Credentials received, blocker resolved"

# Continue with build session
```

---

## Example 6: Research Mission with Export

**Scenario**: Dedicated research mission that produces a report.

### Step 1: Execute Research Mission

```python
# During build session
from context.mission_runtime import start, complete

start("R1.1", agent="assistant", summary="Starting payment gateway evaluation")

# ... do research work ...

complete(
    "R1.1",
    agent="assistant",
    summary="Evaluated 3 payment gateways",
    notes="Stripe recommended for MVP. See exported research report for details."
)
```

### Step 2: Export Research Report

```bash
# Immediately after completing the research mission
./rbook/cli.py research export R1.1
```

**Creates:** `rbook/research/R1.1-payment-gateway-evaluation.md`

### Step 3: Commit and Reference

```bash
# Commit the research report
git add rbook/research/R1.1-payment-gateway-evaluation.md
git commit -m "Research: Payment gateway evaluation"

# Reference in next mission
./rbook/cli.py mission add B2.4 "Implement Stripe Integration" --sprint "Sprint 02"
./rbook/cli.py mission update B2.4 --notes "Based on research R1.1"
```

---

## Best Practices

### When to Use Sessions vs Missions

**Use Sessions for:**
- ✅ Planning and architecture discussions
- ✅ Onboarding new agents/team members
- ✅ Sprint reviews and retrospectives
- ✅ Research spikes that inform decisions
- ✅ Quick check-ins and status updates

**Use Missions for:**
- ✅ Implementing features and code
- ✅ Writing tests and documentation
- ✅ Database migrations
- ✅ Infrastructure setup
- ✅ Any work that modifies the codebase

### Linking Sessions and Missions

1. **Capture mission IDs in sessions**: `./rbook/cli.py session capture context "Related to mission B2.3"`
2. **Reference sessions in missions**: `./rbook/cli.py mission update B2.3 --notes "Per planning session PS-2024-11-13-001"`
3. **Use next-steps to seed missions**: Convert session next-steps into new missions

### Context Hygiene

- **Snapshot after milestones**: Sprint completion, major decisions, architecture changes
- **Export research immediately**: Don't wait - export reports right after mission completion
- **Review onboard output**: Use `session onboard` at the start of every new session

---

## Command Quick Reference

### MCP Tools (Recommended for AI Agents)

```
# Onboarding
cmos_agent_onboard()                              # Get project context
cmos_db_health()                                  # Check database

# Sprints
cmos_sprint_add(sprintId, title, focus, ...)     # Create sprint
cmos_sprint_list()                                # List sprints
cmos_sprint_show(sprintId)                        # Show sprint details

# Missions
cmos_mission_status()                             # View work queue
cmos_mission_add(missionId, name, sprintId, ...) # Create mission
cmos_mission_start(missionId)                     # Start mission
cmos_mission_complete(missionId, notes)           # Complete mission
cmos_mission_block(missionId, reason, blockers)   # Block mission
cmos_mission_unblock(missionId, resolution)       # Unblock mission
cmos_mission_depends(fromId, toId, type)          # Add dependency

# Sessions
cmos_session_start(type, title)                   # Start session
cmos_session_capture(category, content)           # Capture insight
cmos_session_complete(summary, nextSteps)         # Complete session
cmos_session_list()                               # List sessions

# Context
cmos_context_view()                               # View context
cmos_context_snapshot(contextType, source)        # Take snapshot
cmos_decisions_search(query)                      # Search decisions
```

### CLI Commands (For Human Operators)

```bash
# Sessions
./rbook/cli.py session start --type <type> --title "<title>" [--sprint "<sprint>"]
./rbook/cli.py session capture <category> "<content>"
./rbook/cli.py session complete --summary "<summary>" [--next-steps "<step>"]
./rbook/cli.py session onboard
./rbook/cli.py session list [--limit N] [--type <type>]

# Missions
./rbook/cli.py mission add <id> "<name>" --sprint "<sprint>"
./rbook/cli.py mission start <id>
./rbook/cli.py mission complete <id> --notes "<notes>"
./rbook/cli.py mission depends <from> <to> --type "<label>"

# Context
./rbook/cli.py context snapshot master --source "<milestone>"
./rbook/cli.py context history master [--limit N]

# Research
./rbook/cli.py research export <mission-id>
```

### Python API (For Automation)
```python
from context.mission_runtime import next_mission, start, complete, block

candidate = next_mission()
start(mission_id, agent="...", summary="...")
complete(mission_id, agent="...", summary="...", notes="...")
block(mission_id, agent="...", summary="...", reason="...", needs=[...])
```

---

**Last Updated**: 2025-12-10
**CMOS Version**: 2.1 (MCP-enabled)
**Status**: Complete workflow examples
**See Also**:
- `rbook/docs/mcp-reference.md` - Complete MCP tool reference
- `rbook/docs/session-management-guide.md` - Session command details
- `rbook/docs/build-session-prompt.md` - Build session template
- `rbook/docs/user-manual.md` - Complete user manual

