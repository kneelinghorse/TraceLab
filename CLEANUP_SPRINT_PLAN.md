# Sprint 08: Cleanup & Baseline Establishment

**Goal**: Establish ground truth - make tests, docs, and CMOS reflect the working production system.

**Status**: Planning (Created 2025-11-14)

---

## Phase 1: CMOS System Repair 🔧

**Priority**: HIGH (Blocking other cleanup work)

### B8.1: Fix CMOS Session Management Foreign Key Issue
**Status**: Queued
**Complexity**: Low
**Estimated**: 30min

**Problem**: 
```
sqlite3.IntegrityError: FOREIGN KEY constraint failed
```
When running: `./cmos/cli.py session start`

**Tasks**:
- [ ] Inspect `cmos/context/session_runtime.py` line 152
- [ ] Check `cmos/db/schema.sql` for foreign key constraints
- [ ] Verify sprint references exist in sprints table
- [ ] Add missing sprint records OR relax constraint
- [ ] Test session start/capture/complete workflow
- [ ] Document fix in mission notes

**Success Criteria**:
- ✅ `./cmos/cli.py session start --type planning --title "Test" --sprint "Sprint 08"` succeeds
- ✅ Session capture and complete work end-to-end
- ✅ No foreign key errors in logs

---

### B8.2: Validate CMOS Database Migration
**Status**: Queued (Depends on B8.1)
**Complexity**: Medium
**Estimated**: 1hr

**Context**: Migration happened 2025-11-14, need to verify completeness

**Tasks**:
- [ ] Run `./cmos/cli.py db show current` (verify no errors)
- [ ] Run `./cmos/cli.py db show backlog` (verify missions loaded)
- [ ] Check context snapshots: `./cmos/cli.py context history master`
- [ ] Verify session events table populated
- [ ] Export contexts: `./cmos/cli.py db export contexts`
- [ ] Compare exported contexts to working memory in PROJECT_CONTEXT
- [ ] Document any discrepancies

**Success Criteria**:
- ✅ All CMOS CLI commands execute without errors
- ✅ Mission history from Sprints 01-07 accessible in database
- ✅ Context snapshots show proper timeline
- ✅ Parity check passes (if applicable)

---

### B8.3: Clean Up Stale Mission State
**Status**: Queued (Depends on B8.2)
**Complexity**: Low
**Estimated**: 30min

**Context**: Backlog has missions from interrupted sprint work

**Tasks**:
- [ ] Review B6.3 (marked Blocked) - still relevant?
- [ ] Review B7.6 (marked Completed but embedding issues noted)
- [ ] Review B7.7 (Current) - close or continue?
- [ ] Mark outdated missions as Cancelled
- [ ] Document current production state in MASTER_CONTEXT
- [ ] Clear blocked_missions if resolved

**Success Criteria**:
- ✅ Backlog reflects actual work status
- ✅ No "zombie" missions in In Progress/Current
- ✅ MASTER_CONTEXT documents production reality

---

## Phase 2: Test Suite Restoration 🧪

**Priority**: HIGH (Quality gate for future work)

### B8.4: Fix Test Collection Errors
**Status**: Queued (Depends on B8.1)
**Complexity**: Low
**Estimated**: 30min

**Problem**: 3 collection errors preventing test runs

**Tasks**:
- [ ] Fix `cmos/tests/test_cli_research_export.py` import error
- [ ] Fix `cmos.old/tests/test_cli_research_export.py` (delete if obsolete)
- [ ] Fix `cmos.old/tests/test_mission_runtime_api.py` (delete if obsolete)
- [ ] Run `pytest --collect-only` until clean
- [ ] Document what was fixed/removed

**Success Criteria**:
- ✅ `pytest --collect-only` succeeds with 0 errors
- ✅ All tests are importable
- ✅ No collection errors in output

---

### B8.5: Audit and Categorize Test Failures
**Status**: Queued (Depends on B8.4)
**Complexity**: Medium
**Estimated**: 1hr

**Goal**: Understand which tests are broken and why

**Tasks**:
- [ ] Run full test suite: `pytest -v --tb=short > test-audit.log 2>&1`
- [ ] Categorize failures:
  - Outdated tests (expectations don't match production)
  - Environment issues (missing credentials, services)
  - Real bugs (features actually broken)
- [ ] Create test failure report with categories
- [ ] Prioritize which failures to fix first
- [ ] Mark tests that need updating vs tests that found bugs

**Success Criteria**:
- ✅ Complete list of failing tests with categorization
- ✅ Priority order for fixes
- ✅ Distinction between test issues vs code issues

---

### B8.6: Fix Integration Test: test_markdown_cli_flow
**Status**: Queued (Depends on B8.5)
**Complexity**: High
**Estimated**: 2-3hrs

**Problem**: CLI auth not working in test environment

**Investigation Plan**:
1. [ ] Run test with verbose output: `pytest tests/integration/test_ingestion_flow.py::test_markdown_cli_flow -vvs`
2. [ ] Check if `scripts/ingest_cli.py` has auth implementation
3. [ ] Verify test fixtures provide auth credentials
4. [ ] Check if `--offline` flag properly mocks OpenAI/Qdrant
5. [ ] Trace auth flow: CLI → FastAPI → token validation

**Fix Options**:
- **Option A**: Add auth to ingest_cli.py (if missing)
- **Option B**: Mock auth in test fixtures
- **Option C**: Add test-only bypass in FastAPI

**Tasks**:
- [ ] Implement chosen fix
- [ ] Verify test passes locally
- [ ] Verify test doesn't require production credentials
- [ ] Update test documentation
- [ ] Add auth flow diagram to docs

**Success Criteria**:
- ✅ `pytest tests/integration/test_ingestion_flow.py::test_markdown_cli_flow` passes
- ✅ Test can run in CI without real credentials
- ✅ Test validates full ingestion pipeline

---

### B8.7: Fix Remaining Critical Tests
**Status**: Queued (Depends on B8.6)
**Complexity**: Medium
**Estimated**: 2-4hrs (depends on B8.5 findings)

**Scope**: Fix tests identified as "high priority" in B8.5 audit

**Approach**:
- Work through prioritized list from B8.5
- Fix tests that validate core functionality first
- Update/remove tests for deprecated features
- Add missing tests for new production features

**Success Criteria**:
- ✅ Core test suite (unit + integration) passes
- ✅ Test coverage ≥80% for critical paths
- ✅ CI pipeline ready for automation

---

## Phase 3: Documentation Sync 📚

**Priority**: MEDIUM (Enables team understanding)

### B8.8: Update Architecture Documentation
**Status**: Queued (Depends on B8.3)
**Complexity**: Medium
**Estimated**: 2hrs

**Context**: Production differs from documented architecture

**Tasks**:
- [ ] Review `docs/technical_architecture.md`
- [ ] Update ingestion pipeline diagram (include embedding)
- [ ] Document Qdrant collection initialization
- [ ] Document Railway deployment architecture
- [ ] Update JWT auth flow documentation
- [ ] Add Cloudflare domain wiring details
- [ ] Document environment variable requirements
- [ ] Add troubleshooting section

**Files to Update**:
- `docs/technical_architecture.md`
- `docs/ingestion_pipeline_developer_guide.md`
- `docs/auth_and_cors_guidance.md`
- `docs/local-development.md`
- `README.md` (high-level overview)

**Success Criteria**:
- ✅ Architecture docs match production system
- ✅ Deployment guide is accurate
- ✅ New developers can understand system from docs

---

### B8.9: Create Production Runbook
**Status**: Queued (Depends on B8.8)
**Complexity**: Low
**Estimated**: 1hr

**Goal**: Document how production actually works

**Tasks**:
- [ ] Document production URLs (namozine.com, api.namozine.com)
- [ ] Document Railway services and configs
- [ ] Document Cloudflare settings
- [ ] Document Qdrant Railway setup
- [ ] List required environment variables
- [ ] Add health check procedures
- [ ] Add troubleshooting playbook
- [ ] Document backup/restore procedures

**Deliverable**: `docs/production-runbook.md`

**Success Criteria**:
- ✅ Complete production environment documentation
- ✅ Incident response procedures documented
- ✅ Deployment checklist created

---

### B8.10: Update CMOS Documentation
**Status**: Queued (Depends on B8.2)
**Complexity**: Low
**Estimated**: 30min

**Context**: CMOS underwent rapid fixes, docs may be stale

**Tasks**:
- [ ] Review `cmos/docs/getting-started.md`
- [ ] Review `cmos/docs/operations-guide.md`
- [ ] Verify CLI commands still work as documented
- [ ] Update session management guide with fixes
- [ ] Document foreign key fix from B8.1
- [ ] Add known issues/workarounds section

**Success Criteria**:
- ✅ CMOS docs match current behavior
- ✅ All documented commands work
- ✅ Migration notes included

---

## Phase 4: Code Quality & Maintenance 🧹

**Priority**: LOW (Nice to have, not blocking)

### B8.11: Fix Deprecation Warnings
**Status**: Queued (Optional)
**Complexity**: Medium
**Estimated**: 2hrs

**Warnings to Fix**:
1. Pydantic V2 `config` → `ConfigDict`
2. SQLAlchemy `declarative_base()` → `orm.declarative_base()`
3. passlib `crypt` deprecation (Python 3.13 prep)

**Tasks**:
- [ ] Update Pydantic models to V2 style
- [ ] Update SQLAlchemy imports
- [ ] Update passlib usage (if needed)
- [ ] Run tests to verify no regressions
- [ ] Document changes in CHANGELOG

**Success Criteria**:
- ✅ `pytest` runs with 0 deprecation warnings
- ✅ Code compatible with Python 3.13
- ✅ All tests still pass

---

### B8.12: Establish CI/CD Pipeline
**Status**: Queued (Optional)
**Complexity**: High
**Estimated**: 3-4hrs

**Goal**: Automate testing and deployment

**Tasks**:
- [ ] Create GitHub Actions workflow
- [ ] Configure test environment (secrets, services)
- [ ] Add pytest run on PR
- [ ] Add lint/type-check steps
- [ ] Add deployment automation (Railway?)
- [ ] Configure status badges
- [ ] Document CI/CD setup

**Success Criteria**:
- ✅ Tests run automatically on every PR
- ✅ Deployment automation functional
- ✅ Team can see test status easily

---

## Phase 5: Baseline Validation ✅

**Priority**: HIGH (Sprint completion gate)

### B8.13: Sprint 08 Validation & Retrospective
**Status**: Queued (Final mission)
**Complexity**: Low
**Estimated**: 1hr

**Goal**: Confirm everything is green and documented

**Validation Checklist**:
- [ ] CMOS: All CLI commands work
- [ ] CMOS: Database is healthy and consistent
- [ ] Tests: Core test suite passes (≥80% pass rate)
- [ ] Tests: Integration tests pass
- [ ] Tests: No collection errors
- [ ] Docs: Architecture reflects production
- [ ] Docs: Production runbook complete
- [ ] Docs: CMOS docs updated
- [ ] Production: System still working (smoke test)
- [ ] Production: Can create project, upload doc, search

**Retrospective Questions**:
1. What was the biggest blocker during cleanup?
2. What technical debt remains?
3. What processes prevented this mess?
4. What should Sprint 09 focus on?

**Deliverables**:
- [ ] `cmos/reports/sprint-08/sprint-08-summary.md`
- [ ] Updated MASTER_CONTEXT with learnings
- [ ] Sprint 09 planning notes

**Success Criteria**:
- ✅ All validation checks pass
- ✅ Retrospective documented
- ✅ Baseline established for future work

---

## Mission Dependency Graph

```
B8.1 (CMOS Fix)
  ├── B8.2 (CMOS Validation)
  │     ├── B8.3 (Clean State)
  │     │     └── B8.8 (Arch Docs)
  │     │           ├── B8.9 (Runbook)
  │     │           └── B8.13 (Retrospective)
  │     └── B8.10 (CMOS Docs)
  └── B8.4 (Test Collection)
        └── B8.5 (Test Audit)
              ├── B8.6 (CLI Test Fix)
              │     └── B8.7 (Other Tests)
              │           └── B8.13 (Retrospective)
              └── B8.13 (Retrospective)

B8.11 (Deprecations) → Optional, can run parallel
B8.12 (CI/CD) → Optional, can run after tests pass
```

---

## Estimated Timeline

**Critical Path** (Required for baseline):
- Phase 1 (CMOS): 2 hours
- Phase 2 (Tests): 6-9 hours
- Phase 3 (Docs): 3.5 hours
- Phase 5 (Validation): 1 hour

**Total Critical**: ~12-15 hours (1.5-2 work days)

**Optional Work**:
- Phase 4 (Code Quality): 5-7 hours

---

## Next Steps

1. **Review this plan** - Is this the right scope?
2. **Prioritize phases** - Which are most important?
3. **Assign missions** - Which can agents handle, which need human review?
4. **Set timeline** - When should this sprint complete?

---

**Last Updated**: 2025-11-14
**Sprint Status**: Planning
**Owner**: Team

