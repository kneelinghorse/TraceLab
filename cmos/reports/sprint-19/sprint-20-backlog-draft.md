# Sprint 20 Backlog Draft

**Sprint:** 20 - UI Polish & Workflow Gaps
**Theme:** Close workflow gaps and improve research-to-knowledge loop
**Planned Start:** After Sprint 19

---

## Known UI Gaps

### B20.1: Report-to-Document Promotion UI Button
**Status:** Queued
**Track:** UI
**Priority:** High

**Problem:** Backend endpoint exists (B17.2 `POST /reports/{id}/promote`) but no UI button to trigger it. Users must manually copy/paste research results and re-upload.

**Objective:** Add "Promote to Document" button on Report detail page that calls the promotion endpoint.

**Success Criteria:**
- Button visible on Report detail page
- Clicking triggers POST /reports/{id}/promote
- Success shows confirmation and links to new document
- Error handling for failed promotions

**Deliverables:**
- Updated Report detail page component
- Promotion confirmation modal/toast

---

### B20.2: Research Mission Results Display
**Status:** Queued
**Track:** UI
**Priority:** Medium

**Problem:** When DeepSearch missions complete, result_markdown isn't easily viewable in UI.

**Objective:** Display mission results inline on Mission detail page.

**Success Criteria:**
- Mission detail page shows result_markdown content
- Markdown properly rendered
- Links to generated documents/reports visible

---

## Additional UI Improvements (TBD)

- Document chunk viewer enhancements
- Search result preview improvements
- Collection management UI polish

---

## Notes

Sprint 20 scope will be finalized after Sprint 19 retrospective. Additional items may surface from PEDR optimization work.
