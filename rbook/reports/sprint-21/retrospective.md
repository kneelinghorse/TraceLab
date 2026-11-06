# Sprint 21 Retrospective

**Sprint:** 21 - Developer Experience & API Consistency
**Status:** Completed
**Date:** 2025-12-11

## Executive Summary

Sprint 21 underwent a significant mid-sprint pivot. The original focus on developer tooling (TypeScript type generation, API standardization) was deprioritized when critical search issues emerged. The sprint pivoted to fix broken main search functionality and document the stabilizing architecture.

**Key Achievement:** PEDR search is now fully integrated into RagService, fixing broken min-max score normalization. Search results now use proper RRF ranking instead of flattened scores that destroyed relevance ordering.

---

## Mission Outcomes

| Mission | Status | Key Outcome |
|---------|--------|-------------|
| B21.7 | Completed | PEDR enhanced with `include_embeddings` and `source_origin` filter for RAG and provenance queries |
| B21.8 | Completed | RagService now uses PEDR instead of broken HybridSearchService |
| B21.9 | Completed | Search UX improved with history in empty state, project/document names with links |
| B21.10 | Completed | Fixed CSS selection highlighting (`hsla()` → `hsl() / alpha` syntax) |
| B21.11 | Completed | Created 4 comprehensive architecture docs (~44KB total) |
| B21.1 | Deferred | OpenAPI TypeScript generation - P1 but superseded by search fixes |
| B21.2 | Deferred | API response standardization - P1 but superseded by search fixes |
| B21.3 | Deferred | Document chunk viewer - P2 |
| B21.4 | Deferred | Search result snippets - P2 |
| B21.5 | Deferred | Frontend error boundaries - P2 |

**Completion Rate:** 5/10 (50%) - 5 intentionally deferred
**Original planned:** 6 missions
**Added mid-sprint:** 4 urgent missions (B21.7-B21.11 except B21.6)

---

## Technical Changes

### Backend Changes

| File | Change |
|------|--------|
| app/services/pedr/search_orchestrator.py | Added `include_embeddings`, `source_origin` params; updated result dataclass |
| app/services/qdrant_service.py | Added `source_origin` payload index and filter |
| app/services/retrieval_service.py | Pass `source_origin` to Qdrant |
| app/services/document_ingestion.py | Include `source_origin` in Qdrant payload |
| app/services/rag_service.py | **Major:** Replaced HybridSearchService with PEDRSearchOrchestrator |
| app/schemas/pedr_search.py | Added `source_origin`, `include_embeddings`, `embedding` fields |

### Frontend Changes

| File | Change |
|------|--------|
| frontend/src/features/search/SearchExperience.tsx | Empty state shows search history; projectIndex map for name resolution |
| frontend/src/components/ResultCard.tsx | Project/document names with links instead of UUIDs |
| frontend/src/styles/globals.css | Fixed `::selection` CSS using modern alpha syntax |

### Documentation Created (B21.11)

| File | Size | Contents |
|------|------|----------|
| docs/architecture/PEDR-search.md | 9.9KB | 5-layer architecture, RRF fusion, filter params, cache |
| docs/architecture/mission-protocol.md | 11.3KB | Evidence objects, synthesis, KeyQuestion lifecycle |
| docs/api/README.md | 10KB | 70+ endpoint map organized by domain |
| docs/integration/deepsearch.md | 12.3KB | Preflight queries, mission ingestion, best practices |

### Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| tests/test_pedr_enhancements.py | 23 new | `include_embeddings`, `source_origin`, cache keys |
| tests/test_rag_service.py | 6 updated | All pass with PEDR backend |

---

## Critical Bug Fix: Search Score Normalization

### The Problem

`HybridSearchService._normalize_scores()` used min-max normalization that destroyed score magnitude:

```python
span = maximum - minimum
payload[target_key] = (score - minimum) / span
```

**Result:** A semantic score of 0.92 and a keyword score of 0.05 both became 1.0 if they were the "best" in their category. This made fusion meaningless.

### The Fix (B21.8)

Replaced HybridSearchService with PEDRSearchOrchestrator which uses Reciprocal Rank Fusion (RRF):

```
RRF_score(d) = Σ (weight_i / (k + rank_i(d)))
```

RRF operates on rank positions, not raw scores, so no normalization is needed. This preserves proper relevance ordering.

---

## Mid-Sprint Pivot Analysis

### What Triggered the Pivot

While working on Sprint 21's original scope (DX improvements), search quality issues emerged:
1. Main search results had poor relevance ordering
2. Investigation traced to HybridSearchService score normalization
3. PEDR was already implemented but not integrated into main search path

### Decision Made

**Pause DX work. Fix search first.**

Rationale:
- Users can't effectively use TraceLab if search doesn't work
- DX improvements help developers; working search helps all users
- PEDR infrastructure was ready; integration was straightforward

### Lessons

1. **Don't ship broken core features:** DX polish means nothing if fundamentals are broken
2. **Monitor production quality:** The search issue existed but wasn't caught earlier
3. **Flexible sprints are okay:** Pivoting to fix critical issues is the right call

---

## What Worked Well

1. **PEDR readiness:** The 5-layer architecture was already implemented, making the fix a matter of integration
2. **Clear problem diagnosis:** B21.8 notes document exactly what was broken and why
3. **Documentation sprint:** B21.11 created durable artifacts that will help future developers
4. **CSS fix precision:** B21.10 identified exact line and modern syntax fix (hsla → hsl / alpha)
5. **Test coverage:** 23 new tests ensure PEDR enhancements don't regress

---

## What Needs Improvement

1. **Search quality monitoring:** Need automated checks that search relevance stays reasonable
2. **Type synchronization (still needed):** Frontend types still drift from backend - deferred B21.1
3. **API consistency (still needed):** Mix of raw arrays and PaginatedResponse - deferred B21.2
4. **Pre-production testing:** The score normalization bug should have been caught before this sprint

---

## Deferred Work (Carry to Sprint 22)

### P1 - Developer Experience

| ID | Name | Notes |
|----|------|-------|
| B21.1 | OpenAPI TypeScript Type Generation | Still needed; prevents type drift |
| B21.2 | Standardize List API Responses | Still needed; prevents frontend bugs |

### P2 - User Experience

| ID | Name | Notes |
|----|------|-------|
| B21.3 | Document Chunk Viewer | Nice to have for transparency |
| B21.4 | Search Result Snippet Previews | Would improve result scanning |
| B21.5 | Frontend Error Boundary | Should catch crashes gracefully |

### From Sprint 20

| ID | Name | Notes |
|----|------|-------|
| B20.6 | Alert Sound on Mission Complete | P3, consider Notification API |

---

## Sprint 22 Recommendations

### Theme: Search Quality & Developer Experience

Based on Sprint 21 outcomes:

### Priority 1: Search Quality Assurance

1. **Search regression tests:** Automated tests that verify search relevance on known queries
2. **Query-result golden sets:** Maintain expected results for benchmark queries
3. **PEDR latency monitoring:** Track P50/P99 latencies in production

### Priority 2: Deferred DX Items

1. **B21.1: OpenAPI TypeScript generation** - Automate to prevent drift
2. **B21.2: API response standardization** - All lists return PaginatedResponse

### Priority 3: User Experience

1. **B21.3: Chunk viewer** - Help users understand document processing
2. **Search result improvements** - Snippets, highlighting

### New Items Identified

1. **HybridSearchService deprecation:** Can be removed now that PEDR is integrated
2. **Search quality dashboard:** Surface hit rates, latencies to users
3. **Document lineage visualization:** Show synthesized → upload relationships

---

## Key Decisions Made

1. **PEDR is primary search path:** HybridSearchService deprecated in favor of PEDR
2. **Mid-sprint pivot justified:** User-facing fixes > developer tooling when core is broken
3. **Documentation investment:** 44KB of architecture docs created while system is fresh
4. **Modern CSS syntax:** Use `hsl(var(--color) / alpha)` not `hsla(var(--color), alpha)`

---

## Artifacts

| Artifact | Location |
|----------|----------|
| Sprint 21 Retrospective | cmos/reports/sprint-21/retrospective.md |
| Sprint 22 Backlog Draft | cmos/reports/sprint-21/sprint-22-backlog-draft.md |
| PEDR Architecture | docs/architecture/PEDR-search.md |
| Mission Protocol | docs/architecture/mission-protocol.md |
| API Overview | docs/api/README.md |
| DeepSearch Integration | docs/integration/deepsearch.md |

---

## Metrics

| Metric | Value |
|--------|-------|
| Missions completed | 5 |
| Missions deferred | 5 |
| Tests added | 23 |
| Documentation created | ~44KB |
| Bug fixes | 2 (search normalization, CSS selection) |

---

**Mission B21.6 Status:** COMPLETE
**Sprint 21 Status:** COMPLETE
