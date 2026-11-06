# Sprint 22 Backlog Draft

**Sprint:** 22 - Search Quality & Developer Experience
**Status:** Planned
**Focus:** Search regression prevention, type synchronization, deferred UX improvements

---

## Sprint Themes

1. **Search Quality Assurance:** Prevent regression of newly-fixed PEDR search with automated testing
2. **Developer Experience:** Complete deferred type generation and API standardization
3. **UX Polish:** Add chunk viewer and error boundaries

---

## Mission Backlog

| ID | Name | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| B22.1 | Search Quality Regression Tests | P1 | Medium | None |
| B22.2 | OpenAPI TypeScript Type Generation | P1 | Medium | None |
| B22.3 | Standardize List API Responses | P1 | Medium | B22.2 (types) |
| B22.4 | HybridSearchService Deprecation | P2 | Small | None |
| B22.5 | Document Chunk Viewer | P2 | Small | None |
| B22.6 | Frontend Error Boundary | P2 | Small | None |
| B22.7 | Sprint 22 Retrospective | P3 | Small | All above |

---

## Mission Details

### B22.1: Search Quality Regression Tests

**Objective:** Create automated tests with golden query sets to catch search relevance regressions before they reach users

**Success Criteria:**
- Golden query set with expected top-5 results for 10+ benchmark queries
- Test runner compares actual results to golden set
- CI fails if relevance drops below threshold (e.g., 80% overlap)
- Latency assertions: P50 < 200ms, P99 < 500ms
- Test runs as part of PR checks

**Deliverables:**
- tests/golden_queries.yaml - benchmark queries with expected results
- tests/test_search_quality.py - regression test runner
- CI workflow step for search quality gate

**Rationale:** Sprint 21 revealed that search relevance can silently degrade. Automated checks prevent future regressions.

---

### B22.2: OpenAPI TypeScript Type Generation

**Objective:** Set up automated TypeScript type generation from FastAPI OpenAPI schema to prevent frontend/backend type drift

**Success Criteria:**
- openapi-typescript or similar installed
- npm script generates types from /openapi.json
- Generated types replace hand-written mission/document/project types
- Type-check passes with generated types
- CI/pre-commit validates types are up-to-date

**Deliverables:**
- frontend/src/types/generated.ts - auto-generated types
- package.json script for type generation
- CI workflow step or pre-commit hook

**Carried from:** B21.1

---

### B22.3: Standardize List API Responses

**Objective:** Ensure all list endpoints return consistent PaginatedResponse shape with items, total, page, page_size

**Success Criteria:**
- All /list endpoints return PaginatedResponse
- Frontend updated to handle consistent response shape
- Generated types (B22.2) reflect standardized responses
- API documentation reflects changes

**Deliverables:**
- app/schemas/common.py - PaginatedResponse generic
- Updated endpoints: missions, documents, projects, reports, collections
- frontend/src/lib/api/*.ts - consistent response handling

**Carried from:** B21.2

---

### B22.4: HybridSearchService Deprecation

**Objective:** Remove deprecated HybridSearchService now that PEDR is fully integrated

**Success Criteria:**
- All imports of HybridSearchService removed
- app/services/hybrid_search.py deleted or moved to deprecated/
- No test dependencies on HybridSearchService
- Search functionality verified after removal

**Deliverables:**
- Remove app/services/hybrid_search.py
- Update any remaining imports
- Verify all tests pass

**Context:** Sprint 21 (B21.8) replaced HybridSearchService with PEDR in RagService. The old service can now be removed.

---

### B22.5: Document Chunk Viewer

**Objective:** Add chunk viewer tab/section to document detail page showing how the document was split into chunks

**Success Criteria:**
- Document detail shows chunk count and list
- Each chunk displays: sequence number, character count, preview text
- Chunks collapsible/expandable for long documents
- Loading state while chunks fetch

**Deliverables:**
- GET /documents/{id}/chunks endpoint (if not exists)
- frontend/src/pages/documents/[id].tsx - Chunks tab/section
- frontend/src/components/ChunkViewer.tsx - reusable component

**Carried from:** B21.3

---

### B22.6: Frontend Error Boundary

**Objective:** Add React error boundaries to catch and report UI crashes gracefully

**Success Criteria:**
- Error boundary wraps main app layout
- Errors logged to console with component stack
- User sees friendly error message instead of white screen
- Optional: Send errors to backend logging endpoint

**Deliverables:**
- frontend/src/components/ErrorBoundary.tsx
- frontend/src/pages/_app.tsx - wrap with error boundary

**Carried from:** B21.5

---

### B22.7: Sprint 22 Retrospective

**Objective:** Document Sprint 22 outcomes, learnings, and plan Sprint 23

**Success Criteria:**
- Retrospective document created
- Learnings captured in CMOS
- Sprint 23 backlog drafted

---

## Deferred Items (Sprint 23+)

| ID | Name | Notes |
|----|------|-------|
| B21.4 | Search Result Snippet Previews | Show context around matches |
| B20.6 | Alert Sound on Mission Complete | P3, consider Notification API |
| - | PEDR Metrics Dashboard | Surface latency metrics to users |
| - | Feature Usage Analytics | Track which features are used |
| - | Document Lineage Visualization | Show synthesized → upload relationships |
| - | Collection Management Polish | Edit/delete collections, reorder chunks |

---

## Sprint Planning Notes

### Estimation Guidelines

| Effort | Description | Typical Duration |
|--------|-------------|------------------|
| Small | Single file, clear scope | 1 mission session |
| Medium | Multiple files, some discovery | 2-3 mission sessions |
| Large | Cross-cutting, significant discovery | 4+ mission sessions |

### Risk Factors

1. **B22.1 (Search Quality):** Golden set creation may reveal more search issues
2. **B22.2 (Type Generation):** OpenAPI schema may have gaps requiring backend fixes
3. **B22.3 (API Standardization):** Breaking changes may affect frontend significantly

### Dependencies

```
B22.2 (Types) → B22.3 (API Standardization)
```

Type generation should complete before API standardization so the generated types reflect the standardized responses.

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Missions completed | 6/7 |
| Search quality tests | 10+ golden queries |
| Type drift prevention | Zero hand-written API types |
| API consistency | 100% endpoints return PaginatedResponse |

---

**Created:** 2025-12-11
**Source:** Sprint 21 Retrospective (B21.6)
