# TraceLab Development Roadmap — Sprints 31-34

## Executive Summary

This roadmap covers four sprints of work spanning MCP description updates, frontend UX improvements, multi-user authentication, mission observability, and cross-platform integration. It replaces the original Sprint 31 plan (which focused on DeepSearch Phase 2 endpoints and skeleton/toast UI that was deprioritized).

**Key Drivers:**
- DeepSearch behavior has evolved — MCP descriptions are stale and mislead agents
- Single-user auth blocks collaboration; cmos-dashboard already has multi-user JWT patterns to follow
- Mission reports render as plain `<pre>` text, documents aren't exportable from research workflows
- No real-time mission progress visibility — operators watch Railway logs directly
- Error noise between DeepSearch and TraceLab creates confusion in logs
- Login page pre-fills "tracelab-admin" — needs clean login + registration

**Sprints at a Glance:**

| Sprint | Theme | Missions |
|--------|-------|----------|
| **31** | MCP Descriptions, Login & Export Polish | 5 missions |
| **32** | Multi-User Authentication | 4 missions |
| **33** | Mission Observability & Communication Cleanup | 3 missions |
| **34** | Cross-Platform Integration | 2 missions |

---

## Sprint 31 — MCP Descriptions, Login & Export Polish

**Focus:** Fix stale DeepSearch descriptions that mislead agents, clean up the login experience, add document export, and prettify markdown reports. Context condensation from original plan retained.

### T31.1: Update DeepSearch Research Depth Descriptions

**Objective:** Update all MCP tool descriptions, schema docstrings, and tier documentation to reflect actual DeepSearch behavior post-recent updates. The current descriptions (baseline = "quick verification", deep = "comprehensive analysis", alpha = "novel domain exploration") are stale and cause agents to make poor tier selections.

**Actual observed behavior to reflect:**
- **Baseline**: The new standard research tier. Produces thorough reports with 50-60 sources across multiple loops. This is a comprehensive report suitable for most research needs. Takes 8-12 minutes. Use as the default for any research task.
- **Deep**: Higher-rigor research with 30-40 carefully vetted sources. Enforces stricter quality gates and runs a minimum of 5 loops, typically taking 20-25 minutes. Use when you need higher confidence and are willing to wait for more rigorous source evaluation.
- **Alpha**: Maximum-rigor research with ~20 highly scrutinized sources. Very strict quality gates that may reject the research if the available evidence doesn't meet the bar. Use only when precision and source authority are critical AND the topic domain has sufficient high-quality sources to satisfy the gates. Not every topic is suitable for alpha.

**Files to update:**
- `app/mcp_server/tools/missions.py` — `create_mission` and `submit_mission` tool description strings (lines 139-143, 204-207)
- `app/schemas/mission.py` — `ResearchDepth` docstring and field descriptions
- `app/schemas/deepsearch.py` — `research_depth` field description in `DeepSearchExecuteRequest`
- Coordinate with DeepSearch.alpha: `docs/research-depth-tiers.md` — Quick Reference table, tier descriptions, Cost and Time Tradeoffs table, tier selection criteria

**Success Criteria:**
- [ ] All MCP tool descriptions for `research_depth` reflect actual behavior (source counts, timing, rigor level)
- [ ] Schema docstrings updated in both TraceLab and DeepSearch repos
- [ ] Tier selection criteria guide agents toward appropriate choices (baseline as default, alpha as careful decision)
- [ ] Cost and Time Tradeoffs table updated with realistic figures

**Deliverables:**
- Updated `app/mcp_server/tools/missions.py`
- Updated `app/schemas/mission.py` and `app/schemas/deepsearch.py`
- Updated `DeepSearch.alpha/docs/research-depth-tiers.md`

---

### T31.2: Login Page Overhaul & Registration Endpoint

**Objective:** Remove the pre-filled "tracelab-admin" default from the login page and create a clean login + registration experience. Reference the cmos-dashboard implementation (`src/routes/auth.ts`, `src/views/login.ejs`, `src/views/register.ejs`) for a simple, proven pattern. This is a frontend + light backend task — the full multi-user database migration happens in Sprint 32. For now, registration can create users in-memory or use env-based validation, but the UI and API contract should be production-ready.

**What changes:**
- Frontend `LoginPanel.tsx`: Remove hardcoded "tracelab-admin" default username, clean up the form
- Add a registration page/component (`RegisterPanel.tsx`) with email + password fields
- Backend `app/api/v1/auth.py`: Add `POST /api/v1/auth/register` endpoint (initially validates and returns token using env-based single-user flow; Sprint 32 will add DB-backed users)
- Update `AuthContext.tsx` to support registration flow
- Update `AuthGate.tsx` to show register link from login

**Success Criteria:**
- [ ] Login page has no pre-filled credentials
- [ ] Registration page exists with email + password (min 8 chars) + optional display name
- [ ] Registration endpoint returns JWT on success
- [ ] Login and registration forms have proper error handling
- [ ] Visual design is clean and minimal (reference cmos-dashboard dark theme)

**Deliverables:**
- Updated `frontend/src/components/LoginPanel.tsx`
- New `frontend/src/components/RegisterPanel.tsx`
- Updated `frontend/src/components/AuthGate.tsx`
- Updated `frontend/src/contexts/AuthContext.tsx`
- Updated `app/api/v1/auth.py` with register endpoint

---

### T31.3: Document & Report Export

**Objective:** Add export/download capability for documents and reports that originate from DeepSearch research missions. Currently, only physically uploaded documents have a download endpoint (`/documents/{id}/download`). Mission result documents and reports (synthesized markdown) have no export path. Users should be able to export from both the mission detail page and the document/report detail pages.

**Export formats:**
- Markdown (.md) — primary, since results are already markdown
- JSON (.json) — structured export with metadata (existing pattern from console `ExportButtons.tsx`)
- Plain text (.txt) — stripped markdown

**Implementation approach:**
- Backend: Add `GET /api/v1/reports/{id}/export?format=md|json|txt` endpoint
- Backend: Ensure `GET /api/v1/documents/{id}/download` works for DeepSearch-generated documents (not just uploaded files)
- Frontend mission detail page (`pages/missions/[id].tsx`): Add export buttons for result_markdown
- Frontend report detail page (`pages/reports/[id].tsx`): Add export buttons
- Frontend document detail page (`pages/documents/[id].tsx`): Add download button
- Reuse the `downloadFile()` utility pattern from existing export code

**Success Criteria:**
- [ ] Reports exportable as .md, .json, and .txt from report detail page
- [ ] Mission results exportable as .md from mission detail page
- [ ] Documents downloadable from document detail page (both uploaded and generated)
- [ ] Export buttons visible and functional on all three page types
- [ ] Downloaded files have sensible names (e.g., `{mission_id}-report.md`)

**Deliverables:**
- New `app/api/v1/reports.py` export endpoint (or addition to existing)
- Updated `frontend/src/pages/missions/[id].tsx` with export controls
- Updated `frontend/src/pages/reports/[id].tsx` with export controls
- Updated `frontend/src/pages/documents/[id].tsx` with download button
- `frontend/src/lib/api/reports.ts` — export API functions

---

### T31.4: Markdown Report Rendering

**Objective:** Mission result reports currently render as plain `<pre>` text in both the mission detail page and the console mission detail page. Replace this with proper markdown rendering so reports look polished on screen — headings, lists, tables, code blocks, links all rendered correctly.

**Implementation approach:**
- Add a markdown rendering library (e.g., `react-markdown` with `remark-gfm` for GitHub-flavored markdown support)
- Create a reusable `MarkdownRenderer` component in `frontend/src/components/ui/`
- Apply to mission detail page (`pages/missions/[id].tsx`) — replace `<pre>` result display
- Apply to console mission detail page (`pages/console/missions/[id].tsx`) — replace `<pre>` result display
- Apply to report detail page (`pages/reports/[id].tsx`) — replace `whitespace-pre-wrap` display
- Style markdown output to match the existing dark design system (code blocks, tables, headings)

**Success Criteria:**
- [ ] Markdown reports render with proper formatting (headings, lists, tables, code blocks, links)
- [ ] Rendering works on mission detail, console mission detail, and report detail pages
- [ ] Styled consistently with existing design system
- [ ] No XSS risk — sanitize HTML output
- [ ] Reusable `MarkdownRenderer` component available for future use

**Deliverables:**
- New `frontend/src/components/ui/MarkdownRenderer.tsx`
- Updated `frontend/src/pages/missions/[id].tsx`
- Updated `frontend/src/pages/console/missions/[id].tsx`
- Updated `frontend/src/pages/reports/[id].tsx`
- Package addition: `react-markdown`, `remark-gfm`

---

### T31.5: Context Condensation & Sprint 30 Closure

**Objective:** Master context is at 125% of the 100KB limit and contains stale data. Condense to under 60%, clean up stale fields, and close out Sprint 30 properly.

*(Retained from original Sprint 31 plan — objective and success criteria unchanged.)*

**Success Criteria:**
- [ ] Pre-condensation snapshot taken
- [ ] Master context condensed from 125% to under 60%
- [ ] Stale fields cleaned (current_sprint → Sprint 31, roadmap pruned)
- [ ] All key decisions, learnings, and constraints preserved
- [ ] Post-condensation snapshot taken
- [ ] Context loads correctly after changes

**Deliverables:**
- Condensed master_context at <60% usage
- Pre and post condensation snapshots
- Clean context fields reflecting Sprint 31 state

---

## Sprint 32 — Multi-User Authentication

**Focus:** Migrate from single-user env-based auth to database-backed multi-user auth. All users share the same data and permissions — the goal is identity tracking, not access control. Follow cmos-dashboard patterns (bcrypt, JWT, PostgreSQL users table).

### T32.1: Users Table & Registration API

**Objective:** Create a `users` table in PostgreSQL via Alembic migration and build the registration endpoint. The schema should mirror cmos-dashboard's proven pattern: UUID id, email (unique), password_hash (bcrypt), display_name (optional), created_at, last_login_at.

**Implementation approach:**
- New Alembic migration: `xxx_add_users_table.py`
- New SQLAlchemy model: `app/models/user.py`
- New Pydantic schemas: `app/schemas/user.py` (RegisterRequest, UserResponse)
- Update `POST /api/v1/auth/register` from Sprint 31's stub to write to the users table
- bcrypt hashing via existing passlib dependency
- Email uniqueness enforced at DB level
- Password minimum 8 characters

**Success Criteria:**
- [ ] Users table created via Alembic migration with proper indexes
- [ ] Registration endpoint creates user with bcrypt-hashed password
- [ ] Duplicate email returns 409 Conflict
- [ ] Password validation enforced (min 8 chars)
- [ ] Registration returns JWT token (user is logged in immediately)
- [ ] Existing single-user env-based login still works as fallback

**Deliverables:**
- `alembic/versions/xxx_add_users_table.py`
- `app/models/user.py`
- `app/schemas/user.py`
- Updated `app/api/v1/auth.py`

---

### T32.2: Multi-User JWT Auth Flow

**Objective:** Update the authentication flow to support database-backed users alongside the existing env-based admin account. Login should check the users table first, then fall back to env-based credentials. JWT payload should include user_id and email.

**Implementation approach:**
- Update `app/core/security.py`:
  - `verify_credentials()` → check users table first, then env fallback
  - `create_access_token()` → include `user_id` and `email` in JWT payload
  - `require_authenticated_user()` → return `AuthenticatedUser` with user_id, email, username
- Update `AuthenticatedUser` dataclass to include `user_id: Optional[UUID]` and `email: Optional[str]`
- Ensure API key auth still works (api_keys.user_id maps to users.id)
- JWT secret: use same `SECRET_KEY` env var (shared with cmos-dashboard if needed)

**Success Criteria:**
- [ ] DB-backed users can log in with email + password
- [ ] Env-based admin still works as fallback
- [ ] JWT contains user_id and email
- [ ] API key auth still functional
- [ ] Token refresh works for both user types
- [ ] Existing tests pass + new tests for multi-user flow

**Deliverables:**
- Updated `app/core/security.py`
- Updated `app/schemas/auth.py`
- New/updated tests in `tests/test_auth_flow.py`

---

### T32.3: User Attribution & Audit Trail

**Objective:** Track which user creates or modifies resources. The `created_by` field already exists on missions (as string). Extend user attribution across the system so actions are traceable to specific users.

**Implementation approach:**
- Missions: `created_by` → store user_id (UUID) instead of "mcp-tool" or username string
- Documents: Add `uploaded_by` field (or use existing `user_id` column)
- Reports: Add `created_by` field
- Collections: Add `created_by` field
- Update API endpoints to extract user_id from `require_authenticated_user()` and pass to service layer
- Migration to add any missing columns

**Success Criteria:**
- [ ] All new missions track creating user's ID
- [ ] All new documents track uploading user's ID
- [ ] All new reports track creating user's ID
- [ ] API endpoints consistently use authenticated user for attribution
- [ ] Existing data gracefully handles NULL user_id (pre-migration resources)

**Deliverables:**
- Alembic migration for new/updated columns
- Updated service layer methods to accept user_id
- Updated API endpoints to pass user_id from auth

---

### T32.4: Frontend Auth Integration

**Objective:** Update the frontend to fully support multi-user auth — registration page, user display, and auth context updates.

**Implementation approach:**
- Update `AuthContext.tsx`: store user_id, email from JWT payload
- Update `AuthGate.tsx` header: show email/display_name instead of just username
- Update `RegisterPanel.tsx` from Sprint 31: connect to real registration endpoint
- Add user profile indicator in header (email + logout)
- Update `localStorage` auth storage to include user_id, email
- Update `httpClient` to send user context where needed

**Success Criteria:**
- [ ] New users can register and are logged in immediately
- [ ] Login works for both registered users and env-based admin
- [ ] Header shows user email/display name
- [ ] Auth state persists across refreshes
- [ ] Logout clears all user state

**Deliverables:**
- Updated `frontend/src/contexts/AuthContext.tsx`
- Updated `frontend/src/components/AuthGate.tsx`
- Updated `frontend/src/components/RegisterPanel.tsx`
- Updated `frontend/src/lib/auth/storage.ts`

---

## Sprint 33 — Mission Observability & Communication Cleanup

**Focus:** Give operators visibility into mission execution progress and clean up noisy error chatter between DeepSearch and TraceLab.

### T33.1: Mission Progress API & Live Updates

**Objective:** Missions currently show no real-time progress — operators watch Railway logs to monitor DeepSearch execution. Build a progress reporting mechanism so the frontend can display execution stage, current loop, source count, and log messages as they happen.

**Implementation approach (investigate both, pick one):**

**Option A — SSE (Server-Sent Events):**
- DeepSearch worker writes progress to a shared table or Redis
- TraceLab exposes `GET /api/v1/missions/{id}/progress/stream` as SSE endpoint
- Frontend subscribes and renders live updates

**Option B — Enhanced Polling with Log Buffer:**
- DeepSearch worker writes structured log entries to missions table (`execution_metadata` JSONB)
- TraceLab exposes `GET /api/v1/missions/{id}/progress` with latest stage, loop, sources, log tail
- Frontend polls every 5-10 seconds while mission is in_progress (already has 30s polling infra)

**Progress data to surface:**
- Current stage (researching / reflecting / converging / writing)
- Current loop number / total loops
- Sources found so far
- Quality gate status
- Recent log messages (last 10-20 lines)
- Elapsed time

**Success Criteria:**
- [ ] In-progress missions show current execution stage and loop count
- [ ] Source count updates as research progresses
- [ ] Recent log messages visible on mission detail page or console
- [ ] Progress updates appear within 10 seconds of occurring
- [ ] Completed missions show final execution summary

**Deliverables:**
- New progress endpoint(s) in `app/api/v1/missions.py`
- DeepSearch worker progress reporting (coordination with DeepSearch.alpha repo)
- Frontend progress component on mission detail and/or console pages
- Updated `frontend/src/pages/missions/[id].tsx` or `frontend/src/pages/console/index.tsx`

---

### T33.2: DeepSearch-TraceLab Communication Audit

**Objective:** Investigate and fix the error noise in logs between DeepSearch and TraceLab. The systems work operationally but produce chatter — likely from deprecated endpoints, mismatched schemas, or redundant calls. Clean up so logs reflect actual operational state.

**Investigation areas:**
- DeepSearch `webhook.py` — is it still being called? If direct DB writes replaced it, remove or disable the webhook handler
- DeepSearch `uploader.py` — are there endpoints it calls that don't exist or return errors that get swallowed?
- TraceLab `deepsearch.py` ingest endpoint — are there validation warnings that should be info-level, not error-level?
- Schema mismatches: `objectives` (list in DeepSearch) vs `objective` (string in TraceLab)
- Check Railway logs for actual error patterns and categorize them

**Success Criteria:**
- [ ] Root cause of error noise identified and documented
- [ ] Deprecated endpoints removed or silenced
- [ ] Log levels adjusted (info vs warning vs error) for operational chatter
- [ ] Schema mismatches resolved or documented with conversion logic
- [ ] Clean logs during normal mission execution (errors = actual errors only)

**Deliverables:**
- Audit report documenting findings
- Code changes in TraceLab and/or DeepSearch.alpha to fix noise
- Updated log levels where appropriate

---

### T33.3: Console Mission Log Viewer

**Objective:** Build a log viewer component for the console dashboard that shows mission execution logs. The console page already has a DeepSearch Worker Health card — extend it with a log viewer that shows recent mission activity and allows drilling into specific mission logs.

**Implementation approach:**
- Backend: `GET /api/v1/console/missions/{id}/logs` — returns structured log entries from execution_metadata
- Frontend: New `MissionLogViewer` component with auto-scroll, log-level coloring, timestamp display
- Integrate on console dashboard and/or mission detail page
- Support filtering by log level (info, warning, error)

**Success Criteria:**
- [ ] Console shows recent mission execution logs
- [ ] Logs color-coded by level (info=gray, warning=amber, error=red)
- [ ] Auto-scrolls to latest entry
- [ ] Can filter by mission and log level
- [ ] Accessible from both console dashboard and mission detail page

**Deliverables:**
- New `frontend/src/components/console/MissionLogViewer.tsx`
- New backend endpoint for mission logs
- Updated console dashboard page
- Optionally updated mission detail page

---

## Sprint 34 — Cross-Platform Integration

**Focus:** Improve the integration between TraceLab, CMOS-MCP, and cmos-dashboard. Make the pointer/reference system more robust so each tool complements the others without creating dependencies.

### T34.1: CMOS-MCP TraceLab Reference Enhancement

**Objective:** CMOS-MCP already supports `tracelab://` URIs in mission reference_docs and decision evidence, but the resolution is agent-delegated (agents must use TraceLab MCP tools to fetch content). Enhance the integration so CMOS-MCP can provide richer context about TraceLab references without fetching full documents.

**Improvements:**
- `cmos_resolve_references` tool: Add metadata preview (title, type, date) by calling TraceLab's lightweight API endpoints (document metadata, report info) instead of requiring full document fetch
- Add `tracelab_project_id` configuration to CMOS project metadata for scoped lookups
- Improve collection tagging conventions (`cmos:{sprint_id}`, `cmos:{mission_id}`) — document and validate these patterns
- Add a `cmos_link_evidence` tool or action that simplifies creating TraceLab URI references from search results

**Success Criteria:**
- [ ] `cmos_resolve_references` returns metadata previews for TraceLab URIs (title, type, date)
- [ ] TraceLab project linking configurable via CMOS project metadata
- [ ] Collection tagging conventions documented and validated
- [ ] Agents can create TraceLab URI references without manual URI construction

**Deliverables:**
- Updated `cmos_resolve_references` in cmos-mcp
- Documentation updates in `cmos/docs/tracelab-bridge.md`
- Optional: new `link_evidence` action in `cmos_mission` tool

---

### T34.2: cmos-dashboard TraceLab Sync

**Objective:** The cmos-dashboard already parses `tracelab://` URIs and renders them as clickable links. Enhance the integration to support bidirectional workflow: viewing TraceLab research context from the dashboard, and sending dashboard decisions/messages as TraceLab references.

**Improvements:**
- Dashboard message evidence: When composing messages with TraceLab URIs, validate the URI resolves (ping TraceLab API)
- Dashboard mission detail: Show TraceLab reference_docs with rendered previews (title + link)
- Dashboard → TraceLab: Allow creating TraceLab missions from dashboard context (via API)
- Shared JWT: If both apps share the same `JWT_SECRET`, tokens from one app work in the other — document this pattern and verify it works

**Success Criteria:**
- [ ] TraceLab URIs in dashboard messages validated on compose
- [ ] Mission reference_docs show TraceLab content previews
- [ ] Shared JWT pattern documented and tested
- [ ] No hard dependency created — dashboard works without TraceLab available

**Deliverables:**
- Updated cmos-dashboard message compose with URI validation
- Updated mission detail view with reference previews
- Documentation on shared JWT configuration
- Graceful degradation when TraceLab is unreachable

---

## Dependency Map

```
Sprint 31:
  T31.1 (MCP descriptions)     — independent, can start immediately
  T31.2 (Login overhaul)        — independent, can start immediately
  T31.3 (Document export)       — independent, can start immediately
  T31.4 (Markdown rendering)    — independent, can start immediately
  T31.5 (Context condensation)  — independent, can run anytime

Sprint 32:
  T32.1 (Users table)           — depends on T31.2 (registration endpoint contract)
  T32.2 (Multi-user JWT)        — depends on T32.1 (users table must exist)
  T32.3 (User attribution)      — depends on T32.2 (auth returns user_id)
  T32.4 (Frontend auth)         — depends on T32.1 + T32.2 (backend ready)

Sprint 33:
  T33.1 (Progress API)          — independent of Sprint 32
  T33.2 (Communication audit)   — independent, can start anytime
  T33.3 (Log viewer)            — depends on T33.1 (progress data available)

Sprint 34:
  T34.1 (CMOS-MCP enhancement)  — independent of Sprints 32-33
  T34.2 (Dashboard sync)        — depends on T32.2 (shared JWT)
```

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Multi-user auth breaks existing API key auth | High | T32.2 preserves API key flow; env-based admin is fallback |
| DeepSearch depth configs don't match observed behavior | Medium | T31.1 updates descriptions; config validation can follow |
| SSE streaming adds infrastructure complexity | Medium | T33.1 offers polling fallback option |
| Shared JWT between apps creates security coupling | Low | Document pattern, use separate secrets per env if needed |
| Context condensation loses important decisions | Medium | T31.5 takes pre/post snapshots for safety |

---

**Created:** 2026-03-08
**Scope:** Sprints 31-34 (14 missions)
**Status:** Draft — pending review
