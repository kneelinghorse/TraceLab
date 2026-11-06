# Sprint 17 Backlog Draft
## Theme: Stability & Polish

**Status:** Draft
**Created:** 2025-12-07
**Dependencies:** Sprint 16 completed

---

## Overview

Sprint 17 focuses on stability, test infrastructure, and polish for the Missions/DeepSearch integration delivered in Sprint 16. Secondary goals include report versioning (deferred from S16) and enhanced observability.

---

## Proposed Missions

### Track: Infrastructure (B17.1-B17.2)

| ID | Title | Priority | Estimated Tests |
|----|-------|----------|-----------------|
| B17.1 | Test Infrastructure Fix | High | 15-20 |
| B17.2 | CI Pipeline Update | Medium | 5-10 |

**B17.1: Test Infrastructure Fix**
- Create PostgreSQL-compatible test fixtures for TSVector column
- Mock or skip TSVector-dependent tests in SQLite environments
- Ensure all 226 tests can run in CI

**B17.2: CI Pipeline Update**
- Add PostgreSQL service to GitHub Actions
- Configure test matrix for SQLite + PostgreSQL
- Add type checking and build verification steps

---

### Track: Mission Enhancements (B17.3-B17.5)

| ID | Title | Priority | Estimated Tests |
|----|-------|----------|-----------------|
| B17.3 | Mission Edit Page | Medium | 10-15 |
| B17.4 | Webhook Error Recovery | Medium | 15-20 |
| B17.5 | Research Phases Editor | Low | 10-15 |

**B17.3: Mission Edit Page**
- /missions/[id]/edit page
- Reuse MissionForm component
- Pre-populate from existing mission
- Only allow editing draft status missions

**B17.4: Webhook Error Recovery**
- Track failed auto-ingest/auto-report attempts
- Show retry button in mission detail UI
- Add manual result upload fallback
- DLQ for failed webhooks (optional)

**B17.5: Research Phases Editor**
- Visual editor for research_phases in mission form
- Add/remove phases
- Add/remove tasks per phase
- Optional: priority and dependencies

---

### Track: Reports (B17.6-B17.7)

| ID | Title | Priority | Estimated Tests |
|----|-------|----------|-----------------|
| B17.6 | Report Versioning | Medium | 15-20 |
| B17.7 | Report Export Formats | Low | 10-15 |

**B17.6: Report Versioning**
- parent_id chain for report versions
- Version history in report detail view
- Diff between versions (optional)
- Promote draft to final workflow

**B17.7: Report Export Formats**
- Export as PDF (via browser print or server-side)
- Export as DOCX (optional)
- Export as plain text
- Download button in UI

---

### Track: Observability (B17.8)

| ID | Title | Priority | Estimated Tests |
|----|-------|----------|-----------------|
| B17.8 | DeepSearch Dashboard | Medium | 10-15 |

**B17.8: DeepSearch Dashboard**
- /dashboard/deepsearch page
- Job status distribution (running, completed, failed)
- Average duration chart
- Success rate over time
- Recent failures with error messages

---

### Track: Wrap-up (B17.9)

| ID | Title | Priority | Estimated Tests |
|----|-------|----------|-----------------|
| B17.9 | Sprint 17 Retrospective | Required | N/A |

---

## Summary

| Track | Missions | Priority Focus |
|-------|----------|----------------|
| Infrastructure | 2 | Test stability |
| Mission Enhancements | 3 | Edit + recovery |
| Reports | 2 | Versioning |
| Observability | 1 | Dashboard |
| Wrap-up | 1 | Retrospective |
| **Total** | **9** | |

---

## Dependencies

- B17.1 must complete before B17.2 (CI needs working tests)
- B17.6 builds on Sprint 15 reports foundation
- B17.8 depends on DeepSearch job data being captured in B16.6

---

## Deferred to Sprint 18+

- Mission templates (create from existing missions)
- Batch mission submission
- DeepSearch job cancellation (needs DeepSearch API support)
- Real-time WebSocket updates for queue

---

*Draft created by B16.13 retrospective*
*Agent: opus-4.5*
