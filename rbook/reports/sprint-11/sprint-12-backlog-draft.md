# Sprint 12 Backlog - Make TraceLab Actually Usable

**Date:** 2025-12-05 (REVISED)
**Status:** REVISED - Previous backlog was infrastructure theater for nonexistent scale
**Window:** 2025-12-08 to 2025-12-22

---

## Sprint Summary

Sprint 12 focuses on **making TraceLab actually work** rather than premature production hardening.

**Critical Discovery (2025-12-05):**
- Missions endpoint returns 500 error - core functionality broken
- HTTPS redirects drop auth headers - authentication fails on redirects
- Service account doesn't exist in production - DeepSearch can't authenticate
- API response structures inconsistent - frontend confusion

**Previous backlog was wrong:** Load testing, telemetry rotation, and console auth were infrastructure work for a system that doesn't even function.

---

## REVISED Missions

### B12.1 - Fix Missions Endpoint 500 Error [CRITICAL]
**Priority:** P0
**Objective:** Fix /api/v1/missions/ which returns 500 Internal Server Error

**Root Cause:** Server error - likely DB/serialization issue with MissionProtocolDraft

**Success Criteria:**
- GET /api/v1/missions/ returns 200 with list (even if empty)
- POST /api/v1/missions/ creates missions successfully
- Works in production at https://api.tracelab.aquex.ai

**Files:** app/api/v1/missions.py, app/schemas/mission.py, app/services/mission_protocol_service.py

---

### B12.2 - Fix HTTPS Redirects Dropping Auth Headers [CRITICAL]
**Priority:** P0
**Objective:** Fix FastAPI redirects that use HTTP instead of HTTPS

**Root Cause:** FastAPI redirects to `http://` not `https://`, auth header dropped

**Success Criteria:**
- All redirects use HTTPS
- Auth headers preserved across redirects
- /missions, /documents, /projects work with or without trailing slash

**Files:** app/main.py, app/core/config.py

---

### B12.3 - Create Service Account in Production [CRITICAL]
**Priority:** P0
**Objective:** Create deepsearch-service account in production database

**Root Cause:** Account documented but never created in production DB

**Success Criteria:**
- deepsearch-service can authenticate at production
- Token valid for all API endpoints
- DeepSearch can call /api/v1/deepsearch/ingest

---

### B12.4 - Standardize API Response Structure [HIGH]
**Priority:** P1
**Objective:** Make all API responses consistent

**Current Inconsistency:**
| Endpoint | Key |
|----------|-----|
| /projects | `data` |
| /documents | `data` |
| /retrieval/search | `results` |

**Success Criteria:**
- All list endpoints use consistent structure
- Frontend works without special handling per endpoint

---

### B12.5 - End-to-End Integration Verification [HIGH]
**Priority:** P1
**Objective:** Verify complete DeepSearch → TraceLab flow works

**Test Flow:**
1. Auth with service account
2. Call preflight
3. Call ingest with test mission
4. Verify mission persisted
5. Verify preflight finds it

**Success Criteria:**
- Full flow documented and working
- Test script created
- Any additional issues captured

---

### B12.6 - Sprint 12 Retrospective [NORMAL]
**Priority:** -
**Objective:** Document what was fixed, draft Sprint 13

---

## What We Learned

1. **Don't plan production hardening for systems that don't work**
2. **Actually test the integration before claiming it's "unblocked"**
3. **Service accounts need to exist in production, not just be documented**
4. **Infrastructure theater vs. actual functionality**

---

## DeepSearch Status

**ACTUALLY BLOCKED** (contrary to previous claim):
- Service account: NOT IN PRODUCTION
- Missions endpoint: 500 ERROR
- Redirects: DROP AUTH HEADERS

**After Sprint 12:** Should be actually unblocked.

---

## References

- Diagnostic Session: PS-2025-12-05-004
- Mission YAMLs: cmos/missions/sprint-12/B12.*.yaml
