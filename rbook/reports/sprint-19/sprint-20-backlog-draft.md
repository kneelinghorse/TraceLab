# Sprint 20 Backlog

**Sprint:** 20 - UI Polish & Workflow Gaps
**Theme:** Fix critical UI bugs and close workflow gaps
**Status:** Planning

---

## Critical Bugs (P0)

### B20.1: Report-to-Document Promotion Button
**Status:** Queued
**Priority:** P0
**Track:** UI

**Problem:** Backend endpoint exists (B17.2 `POST /reports/{id}/promote`) but no UI button to trigger it. Also need to mark mission as complete when promoted.

**Objective:** Add "Promote to Document" button on Report/Mission detail page.

**Success Criteria:**
- Button visible on Report detail page
- Clicking triggers POST /reports/{id}/promote
- Success shows confirmation and links to new document
- Mission status updated to Completed on successful promotion
- Error handling for failed promotions

**Deliverables:**
- Updated Report detail page component
- Mission status auto-update logic

---

### B20.2: Fix Edit Mission (Black Screen)
**Status:** Queued
**Priority:** P0
**Track:** UI Bug

**Problem:** Clicking edit on a mission causes the page to go black. No way to edit missions even in draft status.

**Objective:** Fix mission edit functionality.

**Success Criteria:**
- Edit button opens edit form/modal
- All mission fields editable
- Save persists changes
- Cancel returns to detail view without changes

**Investigation:**
- Check mission edit route/component
- Verify API endpoint for mission updates
- Check for JS errors in console

---

### B20.3: Fix Document Delete (confirm=true)
**Status:** Queued
**Priority:** P0
**Track:** UI Bug

**Problem:** Delete document button shows error: `"Document deletion requires confirm=true query parameter"`. UI doesn't pass the required parameter.

**Objective:** Fix delete confirmation to pass `confirm=true` to API.

**Success Criteria:**
- Delete button shows confirmation dialog
- On confirm, API called with `?confirm=true`
- Document soft-deleted successfully
- Works universally (document list, detail page, project page)

**Scope:**
- All places where documents can be deleted need this fix

---

## Nice to Haves - Mission Workflow

### B20.4: Mission-Project Cross-Link
**Status:** Queued
**Priority:** P1
**Track:** UI Enhancement

**Problem:** Mission details don't show parent project link.

**Objective:** Add project cross-link on mission detail page.

**Success Criteria:**
- Mission detail shows "Project: [Project Name]" with clickable link
- Link navigates to project detail page

---

### B20.5: Mission Archive on Promotion
**Status:** Queued
**Priority:** P2
**Track:** Workflow

**Problem:** When report is promoted to document, mission status should update and link to outputs.

**Objective:** Auto-archive missions when their deliverables are promoted.

**Success Criteria:**
- Mission status changes to "Archived" or "Completed" on promotion
- Mission detail shows links to promoted document
- Mission detail shows links to associated project

---

### B20.6: Alert Sound on Mission Complete
**Status:** Queued
**Priority:** P3
**Track:** UX

**Problem:** No notification when long-running missions complete.

**Objective:** Play notification sound when mission completes.

**Success Criteria:**
- Configurable audio notification (ding)
- Plays when mission transitions to Completed
- Can be disabled in settings

---

## Investigation Items

### B20.7: Search History Missing
**Status:** Queued
**Priority:** P1
**Track:** Investigation

**Problem:** Search no longer retains search history. Was this removed or broken?

**Investigation:**
- Check if search history feature was removed
- If removed, was it intentional?
- If broken, identify root cause
- Sprint 9 added search history (B9.4) - verify implementation

**Success Criteria:**
- Determine if feature was removed or broken
- If broken, fix to restore history
- If removed, document decision

---

### B20.8: Console Page Not Wired Up
**Status:** Queued
**Priority:** P1
**Track:** Investigation

**Problem:** Console page shows cards with zeros - not connected to real data.

**Investigation:**
- Console was built in Sprint 11 (B11.3)
- Check API endpoints console is calling
- Verify data flow from backend

**Success Criteria:**
- Console displays real mission/correction/sync data
- All cards show actual counts
- Dashboard is functional

---

## Sprint 20 Retrospective

### B20.9: Sprint 20 Retrospective
**Status:** Queued
**Priority:** Required
**Track:** Process

---

## Execution Order

**Phase 1 - Critical Bugs:**
1. B20.2 (Edit Mission) - blocks all mission editing
2. B20.3 (Delete Document) - blocks document cleanup
3. B20.1 (Promote Button) - completes workflow loop

**Phase 2 - Investigation:**
4. B20.7 (Search History) - determine scope
5. B20.8 (Console) - determine scope

**Phase 3 - Enhancements:**
6. B20.4 (Project Cross-Link)
7. B20.5 (Mission Archive)
8. B20.6 (Alert Sound) - if time permits

**Phase 4 - Close:**
9. B20.9 (Retrospective)

---

## Notes

- P0 bugs are blocking user workflows
- Investigation items may expand scope if bugs found
- Nice-to-haves can be deferred to Sprint 21 if needed
