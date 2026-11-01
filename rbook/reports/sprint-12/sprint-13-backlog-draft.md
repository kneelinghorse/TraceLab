# Sprint 13 Backlog Draft

**Based on:** Sprint 12 E2E Integration Findings
**Theme:** Integration Refinement & Operational Polish
**Drafted:** 2025-12-05

## Context

Sprint 12 successfully made TraceLab usable - the DeepSearch integration flow works end-to-end. Sprint 13 should address the findings from E2E testing and polish the integration experience.

**Important Principle:** TraceLab is a single-builder internal tool. Avoid over-engineering. Focus on actual friction points, not hypothetical scale problems.

## Proposed Missions

### B13.1: Pre-flight Mission Discovery Enhancement
**Priority:** High
**Type:** Build.Enhancement

**Problem:** Missions ingested via DeepSearch are not immediately discoverable via pre-flight queries. Pre-flight search only finds missions linked via document chunks, not missions stored directly.

**Solution Options:**
1. Add fallback query to missions table in preflight endpoint
2. Auto-update `Project.mission_protocol_id` on mission ingestion
3. Accept limitation - missions are still retrievable via GET /missions

**Recommendation:** Option 1 - simple fallback query. Low effort, immediate benefit.

**Success Criteria:**
- Pre-flight can discover missions ingested via /deepsearch/ingest
- No performance regression on existing document-based searches

---

### B13.2: Evidence Requirements Documentation
**Priority:** Medium
**Type:** Build.Documentation

**Problem:** DeepSearch needs clear documentation of what evidence is required for successful mission ingestion.

**Deliverables:**
- Documentation of evidence requirements for /deepsearch/ingest
- Quality gate thresholds documented (1 source per insight minimum)
- Example payloads with valid evidence structures

**Success Criteria:**
- DeepSearch team can reference clear evidence requirements
- Example payloads pass all quality gates

---

### B13.3: Test Data Cleanup Automation
**Priority:** Low
**Type:** Build.Operations

**Problem:** E2E testing creates test missions that accumulate in production database.

**Solution:**
- Add admin endpoint to delete missions by tag
- Or periodic cleanup script for missions with specific prefixes (e.g., `TEST-E2E-*`)

**Decision Required:** Is manual cleanup sufficient for now? (Probably yes for internal tool)

**Success Criteria:**
- Mechanism exists to clean up test missions
- Test data doesn't pollute production data long-term

---

### B13.4: API Error Response Consistency
**Priority:** Medium
**Type:** Build.Improvement

**Problem:** Error responses vary across endpoints. Some return structured errors, others return plain text.

**Solution:**
- Standardize error response format: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Add consistent HTTP status codes
- Ensure all validation errors return 422 with field details

**Success Criteria:**
- All endpoints return consistent error structure
- DeepSearch can reliably parse error responses

---

### B13.5: Sprint 13 Retrospective
**Priority:** Normal
**Type:** Build.Review

Standard retrospective:
- Document outcomes
- Update MASTER_CONTEXT
- Draft Sprint 14 if needed

---

## Not Recommended for Sprint 13

The following were considered but rejected as over-engineering for a single-user tool:

| Item | Reason to Skip |
|------|----------------|
| Load testing infrastructure | No users to load test for |
| Telemetry rotation | Can manually rm files if needed |
| Multi-user authentication | Single builder, single account |
| Error monitoring/alerting | Manual checking sufficient |
| Complex caching | Current TTL cache is adequate |

## Priority Order

1. **B13.1** - Pre-flight discovery (unblocks full integration loop)
2. **B13.2** - Evidence documentation (helps DeepSearch team)
3. **B13.4** - Error consistency (better debugging)
4. **B13.3** - Test cleanup (nice to have)
5. **B13.5** - Retrospective (standard)

## Estimated Effort

| Mission | Estimate |
|---------|----------|
| B13.1 | 2-3 hours |
| B13.2 | 1 hour |
| B13.3 | 1 hour |
| B13.4 | 2 hours |
| B13.5 | 1 hour |
| **Total** | ~8 hours |

## Notes for Sprint 13 Planning Session

1. Review whether B13.1 is truly needed - missions ARE stored and retrievable, just not in pre-flight recommendations
2. B13.2 could be a simple markdown doc in existing docs/ folder
3. B13.3 might be deferred if test data volume is low
4. Consider whether Sprint 13 is even necessary or if system is "done enough" for current needs

---

**Drafted by:** Claude Code Assistant
**Source:** Sprint 12 E2E Integration Verification Report
