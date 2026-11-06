# Sprint 18 Backlog Draft
## Theme: Observability & Testing Infrastructure

**Created:** 2025-12-09
**Source:** B17.8 Sprint 17 Retrospective

---

## Executive Summary

Sprint 18 focuses on improving observability and establishing testing infrastructure based on Sprint 17 research findings. Key priorities:

1. **CI Migration Testing** - Address gap identified in R17.4
2. **DeepSearch Observability** - Dashboard for job monitoring
3. **Database Backup Documentation** - Recovery procedures
4. **Webhook Error Recovery** - DLQ mechanism for failed processing
5. **Query Optimization** - Address N+1 patterns from R17.5

---

## Mission Candidates

### B18.1: CI Migration Testing Pipeline
**Track:** Infrastructure
**Priority:** High
**Estimated Effort:** 4-6 hours

**Objective:** Create GitHub Actions workflow that tests Alembic migrations in CI to catch issues before production deployment.

**Success Criteria:**
- GitHub workflow tests `alembic upgrade head` on PostgreSQL
- Workflow tests `alembic downgrade -1` and re-upgrade
- Model tests run after migration
- Workflow runs on PR and push to main
- Documentation in docs/ci-migrations.md

**Deliverables:**
- .github/workflows/test-migrations.yml
- docs/ci-migrations.md

**Source:** R17.4 identified "No CI migration testing" as HIGH risk gap

---

### B18.2: DeepSearch Observability Dashboard
**Track:** Observability
**Priority:** Medium
**Estimated Effort:** 6-8 hours

**Objective:** Create dashboard showing DeepSearch job status, duration statistics, and success rates to monitor integration health.

**Success Criteria:**
- Dashboard page at /admin/deepsearch or /missions/dashboard
- Shows: total jobs, running, completed, failed counts
- Shows: average duration, p50/p95 duration charts
- Shows: success rate over time
- Data sourced from missions table execution_metadata
- Auto-refresh capability

**Deliverables:**
- frontend/src/pages/admin/deepsearch-dashboard.tsx (or missions/dashboard)
- frontend/src/components/dashboard/DeepSearchStats.tsx
- API endpoint for aggregated stats if needed

**Dependencies:** Requires missions with execution_metadata populated

---

### B18.3: Database Backup Documentation
**Track:** Operations
**Priority:** Medium
**Estimated Effort:** 2-3 hours

**Objective:** Document Railway PostgreSQL backup configuration and create verified recovery runbook.

**Success Criteria:**
- Railway backup configuration documented
- Step-by-step recovery procedure written
- Recovery procedure tested (at minimum read-through verified)
- Backup monitoring/alerts documented
- Added to docs/operations/ or docs/recovery/

**Deliverables:**
- docs/railway-backup-guide.md
- Update docs/data-protection-audit.md with backup section

**Source:** R17.1 identified backup gaps

---

### B18.4: Webhook Error Recovery (DLQ)
**Track:** Reliability
**Priority:** Medium
**Estimated Effort:** 8-10 hours

**Objective:** Implement dead-letter queue for failed webhook processing with retry mechanism and admin visibility.

**Success Criteria:**
- Failed webhook payloads stored in database table
- Configurable retry count and backoff (default: 3 retries, exponential)
- Admin endpoint to list/retry/delete failed items
- Optional: UI page showing failed webhooks
- Tests for retry logic

**Deliverables:**
- alembic/versions/021_webhook_dlq.py
- app/models/webhook_failure.py
- app/services/webhook_retry.py
- app/api/v1/admin/webhooks.py
- tests/test_webhook_retry.py

**Source:** Sprint 16 identified "No webhook retry/DLQ mechanism"

---

### B18.5: Query Performance Optimization
**Track:** Performance
**Priority:** Low
**Estimated Effort:** 2-3 hours

**Objective:** Add eager loading (selectinload) to document queries to prevent N+1 query patterns.

**Success Criteria:**
- Document.chunks uses selectinload() in detail queries
- Report.sources uses selectinload() where missing
- No N+1 patterns in main list/detail endpoints
- Performance verified with SQLAlchemy query logging

**Deliverables:**
- Updated app/services/document_service.py
- Updated app/api/v1/documents.py
- Optional: SQLAlchemy query logging config for development

**Source:** R17.5 identified "N+1 query risks in relationship loading"

---

### B18.6: Sprint 18 Retrospective
**Track:** Retrospective
**Priority:** Required
**Estimated Effort:** 1-2 hours

**Objective:** Close Sprint 18 with retrospective documenting outcomes and planning Sprint 19.

**Success Criteria:**
- Sprint 18 retrospective document created
- All mission outcomes documented
- Sprint 19 backlog draft created
- MASTER_CONTEXT updated
- Context snapshot taken

**Deliverables:**
- cmos/reports/sprint-18/retrospective.md
- cmos/reports/sprint-18/sprint-19-backlog-draft.md

---

## Deferred Items (Future Sprints)

These items were considered but deferred:

| Item | Reason | Target Sprint |
|------|--------|---------------|
| PEDR HTTP Client | No immediate need | When PEDR approved |
| Report Metadata Extraction | R17.3: NOT NOW | Knowledge graph phase |
| Multi-language FTS | No non-English content | When needed |
| Mission Edit Page | Lower priority | Sprint 19+ |
| Research Phases Editor | Lower priority | Sprint 19+ |

---

## Sprint 18 Summary

| Mission | Track | Priority | Est. Effort |
|---------|-------|----------|-------------|
| B18.1 | Infrastructure | High | 4-6 hours |
| B18.2 | Observability | Medium | 6-8 hours |
| B18.3 | Operations | Medium | 2-3 hours |
| B18.4 | Reliability | Medium | 8-10 hours |
| B18.5 | Performance | Low | 2-3 hours |
| B18.6 | Retrospective | Required | 1-2 hours |

**Total Estimated Effort:** 23-32 hours

---

## Notes

1. B18.1 should be completed first to establish testing foundation
2. B18.2 and B18.3 can run in parallel (no dependencies)
3. B18.4 is the largest mission - consider splitting if needed
4. B18.5 is quick win but low impact at current scale

---

*Created by B17.8 Sprint 17 Retrospective*
*Agent: opus-4.5*
