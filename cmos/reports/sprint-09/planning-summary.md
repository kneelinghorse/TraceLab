# Sprint 09 Planning Summary

**Date:** 2025-11-15  
**Session Type:** Planning  
**Participants:** User + Assistant

---

## Executive Summary

Sprint 09 planned with 6 missions focused on advanced search features per roadmap Week 15. Critical UX fixes prioritized (B9.3) based on user feedback showing broken project dropdown and cluttered controls. All missions are build missions - no research needed.

---

## Sprint 09 Overview

**Title:** Advanced Search Features  
**Duration:** 2025-12-01 to 2025-12-15 (2 weeks)  
**Total Missions:** 6  
**Roadmap Alignment:** Phase 4, Week 15 (Advanced Search Features)

**Focus Areas:**
1. Hybrid search backend (semantic + keyword with weighted scoring)
2. Faceted filtering backend (project, document type, date, tags)
3. Search page UX fixes (PRIORITY - wire project dropdown, simplify controls)
4. Search history (track and replay queries)
5. Saved searches (bookmark useful patterns)

---

## Missions Planned

### B9.1: Hybrid Search Backend (HIGH PRIORITY)
**Objective:** Combine semantic (Qdrant) and keyword (PostgreSQL) search  
**Key Deliverables:**
- PostgreSQL full-text search indexes (tsvector + GIN)
- Hybrid search service with weighted scoring
- API search_mode parameter (semantic, keyword, hybrid)

**Success Criteria:**
- Precision improved by ≥15% vs semantic-only
- Hybrid adds <200ms latency
- Default weights: 0.7 semantic / 0.3 keyword

---

### B9.2: Faceted Search Backend (MEDIUM PRIORITY)
**Objective:** Backend support for search filters  
**Key Deliverables:**
- Filter parameters (project, document_type, source_type, date_range, tags)
- Facets endpoint returning available values
- Filter indexes for performance

**Success Criteria:**
- All 5 filter types work correctly
- Filtering adds <100ms latency
- Facets endpoint returns accurate counts

---

### B9.3: Search Page Fixes & UI Overhaul (HIGH PRIORITY - USER FEEDBACK)
**Objective:** Fix broken UI and simplify search controls  

**Specific Issues to Fix:**
1. ❌ **Project dropdown shows "0"** - API not wired, must call GET /api/v1/projects
2. ❌ **RAG Control Room useless** - missions concept doesn't apply, remove entire section
3. ❌ **Too many controls** - clutter, collapse into advanced panel
4. ❌ **Slider UI awkward** - replace with simple number input (+/- buttons)

**What User Wants:**
- ✅ Search box (keep as-is)
- ✅ Project selector (wire properly)
- ✅ Results count: simple number input, default 10, max 25
- ✅ Extra filters: collapse into expandable panel
- ✅ Remove: RAG Control Room, Session Health, missions-related boxes

**Success Criteria:**
- Project dropdown loads actual projects from API
- Results count input (1-25 range, default 10)
- RAG Control Room section removed
- Advanced filters collapsed by default
- Backend supports top_k up to 25

---

### B9.4: Search History (LOW PRIORITY)
**Objective:** Track and replay previous searches  
**Key Deliverables:**
- search_history table
- History API endpoints
- History sidebar in UI

**Success Criteria:**
- All searches logged automatically
- Last 20 searches displayed in UI
- Click to replay search
- Retention: 100 entries or 30 days

---

### B9.5: Saved Searches (LOW PRIORITY)
**Objective:** Bookmark useful search queries  
**Key Deliverables:**
- saved_searches table
- CRUD API for saved searches
- Save/manage UI

**Success Criteria:**
- Users can save searches with custom names
- Quick access to saved searches
- Limit: 50 saved searches per user

---

### B9.6: Sprint 09 Retrospective (STANDARD)
**Objective:** Document outcomes and prepare Sprint 10  
**Key Deliverables:**
- Retrospective document
- Search precision metrics
- Sprint 10 backlog draft

**Success Criteria:**
- Search improvements quantified
- UX fixes validated
- Next sprint planned

---

## Dependencies

```
B9.1 → B9.3 (Hybrid backend before UI)
B9.2 → B9.3 (Filters backend before UI)
B9.3 → B9.4 (Fixed UI before history feature)
B9.4 → B9.5 (History foundation for saved searches)
All → B9.6 (Retrospective depends on all)
```

---

## Key Decisions Made

### UX Design Decisions (Critical):
1. **Project dropdown must work** - Currently broken, showing "0 projects"
2. **Remove RAG Control Room** - Missions don't make sense on search page
3. **Simplify controls** - Only essential controls visible (search, project, count)
4. **Collapse extra filters** - Hide document type, date range until workflow clarity
5. **Increase max results** - From 10 to 25 (verify backend supports)
6. **Simple number input** - Replace slider with +/- buttons

### Technical Decisions:
1. **No research needed** - All features use standard patterns (PostgreSQL FTS, basic CRUD)
2. **Hybrid search weights** - Default 0.7 semantic / 0.3 keyword (configurable)
3. **Search history retention** - 100 entries or 30 days max
4. **Saved search limit** - 50 per user
5. **Filter logic** - AND across filter types, OR within filter type

### Priority Ordering:
- **HIGH**: B9.1, B9.3 (backend + UX fixes)
- **MEDIUM**: B9.2 (filters backend)
- **LOW**: B9.4, B9.5 (history/saved - nice-to-have)

---

## User Feedback Incorporated

**Search Page Issues Identified:**
- "Project dropdown shows 0 even though there are several" → B9.3 fixes API wiring
- "RAG Control Room makes no sense" → B9.3 removes section entirely
- "Search facets not useful yet" → B9.3 collapses into advanced panel
- "Just need search box, project, and count" → B9.3 simplifies to essentials

**Context on Missions:**
- User clarified missions don't make sense on search page
- Mission Protocol is for research methodology, not search features
- Search page should focus purely on finding/retrieving documents

---

## Sprint 08 vs Sprint 09 Relationship

**Sprint 08 (Optimization)** prepares foundation:
- Telemetry automation → enables Sprint 09 measurement
- Database optimization → supports faster filtering
- Query caching → improves search response times
- Monitoring dashboard → tracks Sprint 09 metrics

**Sprint 09 (Advanced Search)** builds on optimized foundation:
- Hybrid search leverages optimized queries
- Faceted filters benefit from database indexes
- Search page fixes create usable interface
- History/saved searches enable workflow efficiency

---

## Next Steps

**Immediate:**
1. ✅ Sprint 09 missions created (6 YAML files)
2. ✅ Backlog updated with Sprint 09
3. ✅ Database seeded
4. ✅ MASTER_CONTEXT updated with planning decisions
5. ✅ Parity validated

**To Launch Sprint 09:**
1. Complete Sprint 08 first (all 6 missions)
2. Start Sprint 09 with B9.1 (Hybrid Search Backend)
3. High priority: Get to B9.3 quickly (user-facing UX fixes)

**Current Queue:**
- Sprint 08: B8.1 → B8.2 → B8.3 → B8.4 → B8.5 → B8.6
- Sprint 09: B9.1 → B9.2 → B9.3 → B9.4 → B9.5 → B9.6

---

## Artifacts Created

**Sprint 09 Missions:**
- `cmos/missions/sprint-09/B9.1_Hybrid-Search-Backend.yaml`
- `cmos/missions/sprint-09/B9.2_Faceted-Search-Backend.yaml`
- `cmos/missions/sprint-09/B9.3_Search-Page-Fixes.yaml`
- `cmos/missions/sprint-09/B9.4_Search-History.yaml`
- `cmos/missions/sprint-09/B9.5_Saved-Searches.yaml`
- `cmos/missions/sprint-09/B9.6_Sprint-Retrospective.yaml`

**Updates:**
- `cmos/missions/backlog.yaml` (Sprint 09 section added)
- `cmos/context/MASTER_CONTEXT.json` (Sprint 09 planning captured)
- `cmos/db/cmos.sqlite` (6 missions seeded)

---

## Validation Status

✅ Database seeded (36 mission YAML files loaded)  
✅ Sprint 09 visible in backlog  
✅ MASTER_CONTEXT updated with planning decisions and UX insights  
✅ Parity check passed  
✅ Sprint 08 next mission ready (B8.1)

---

**Status:** Sprint 08 & 09 fully planned and ready. Launch Sprint 08 when ready to begin optimization work.

