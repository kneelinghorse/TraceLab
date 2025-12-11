# Sprint 21 Backlog Draft

**Sprint:** 21 - Developer Experience & API Consistency
**Status:** Planned
**Focus:** Auto-generate types, standardize API responses, improve document and search UX

---

## Sprint Themes

1. **Developer Experience:** Reduce friction in frontend development by automating type generation
2. **API Consistency:** Standardize response shapes to prevent frontend bugs
3. **UX Polish:** Add chunk viewer and search snippets for better user insight

---

## Mission Backlog

| ID | Name | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| B21.1 | OpenAPI TypeScript Type Generation | P1 | Medium | None |
| B21.2 | Standardize List API Responses | P1 | Medium | None |
| B21.3 | Document Chunk Viewer | P2 | Small | None |
| B21.4 | Search Result Snippet Previews | P2 | Medium | None |
| B21.5 | Frontend Error Boundary & Tracking | P2 | Small | None |
| B21.6 | Sprint 21 Retrospective | P3 | Small | All above |

---

## Mission Details

### B21.1: OpenAPI TypeScript Type Generation

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

---

### B21.2: Standardize List API Responses

**Objective:** Ensure all list endpoints return consistent PaginatedResponse shape with items, total, page, page_size

**Success Criteria:**
- All /list endpoints return PaginatedResponse
- Frontend updated to handle consistent response shape
- Backward compatibility maintained during transition
- API documentation reflects changes

**Deliverables:**
- app/schemas/common.py - PaginatedResponse generic
- Updated endpoints: missions, documents, projects, reports, collections
- frontend/src/lib/api/*.ts - consistent response handling

---

### B21.3: Document Chunk Viewer

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

---

### B21.4: Search Result Snippet Previews

**Objective:** Show context snippets around matched text in search results instead of truncated chunk content

**Success Criteria:**
- Search results show highlighted snippet around match
- Snippet shows ~50 chars before/after match
- Match term highlighted in snippet
- Falls back to chunk start if no specific match position

**Deliverables:**
- Backend: Return match positions or snippets in search response
- frontend/src/features/search/SearchResultCard.tsx - snippet display
- Highlight styling for matched terms

---

### B21.5: Frontend Error Boundary & Tracking

**Objective:** Add React error boundaries and centralized error tracking to catch and report UI crashes

**Success Criteria:**
- Error boundary wraps main app layout
- Errors logged to console with component stack
- User sees friendly error message instead of white screen
- Optional: Send errors to backend logging endpoint

**Deliverables:**
- frontend/src/components/ErrorBoundary.tsx
- frontend/src/pages/_app.tsx - wrap with error boundary
- Optional: POST /errors endpoint for client error logging

---

### B21.6: Sprint 21 Retrospective

**Objective:** Document Sprint 21 outcomes, learnings, and plan Sprint 22

**Success Criteria:**
- Retrospective document created
- Learnings captured in CMOS
- Sprint 22 backlog drafted

---

## Deferred from Sprint 20

| ID | Name | Status | Notes |
|----|------|--------|-------|
| B20.6 | Alert Sound on Mission Complete | Deferred | P3, consider Notification API |

---

## Future Backlog Items (Sprint 22+)

1. **Collection Management Polish:** Edit/delete collections, reorder chunks
2. **PEDR Metrics Dashboard:** Surface latency metrics to users
3. **Feature Usage Analytics:** Track which features are actually used
4. **Browser Notifications:** Alternative to sound for long-running tasks

---

**Created:** 2025-12-11
**Source:** Sprint 20 Retrospective (B20.9)
