# Sprint 10 Planning Summary - DeepSearch Integration

**Date:** 2025-11-17  
**Session Type:** Planning  
**Status:** Complete

---

## Executive Summary

Sprint 10 planned with 6 missions focused on DeepSearch integration foundation and PEDR Phase 1 implementation. Full alignment achieved with DeepSearch team through integration contract. Phased approach reduces risk: TraceLab builds validation infrastructure (Sprint 10), DeepSearch builds autonomous agent (Sprint 1-3), both teams coordinate integration testing (Week 7).

---

## Sprint 10 Overview

**Title:** DeepSearch Integration & PEDR Phase 1  
**Duration:** 2025-12-16 to 2025-12-31 (2 weeks)  
**Total Missions:** 6  
**Integration Coordination:** Week 7 joint testing with DeepSearch team

**Focus Areas:**
1. PEDR Phase 1 (quality-aware search ranking)
2. DeepSearch ingestion endpoint with post-processing
3. Pydantic schema sharing for pre-validation
4. Relationship context API
5. Integration testing infrastructure

---

## Missions Planned

### B10.1: Quality-Aware Search (PEDR Phase 1) - HIGH PRIORITY
**Objective:** Extend HybridSearch with quality boosting  
**Key Features:**
- Complete missions rank 2× higher than drafts
- Governance filters (min_quality_gates, status, allow_pii)
- Quality score from quality_gates JSON
- Built as app/services/pedr/ module

**PEDR Simplified:**
- Reuses PostgreSQL FTS + Qdrant (from Sprint 09)
- Pure Python, no JavaScript Protocol Suite
- 3-layer (keyword + semantic + quality boost)
- Can enhance to full 6-layer later if needed

---

### B10.2: DeepSearch Ingestion Endpoint + Post-Processing - HIGH PRIORITY
**Objective:** API for autonomous agent research submissions  
**Key Features:**
- POST /api/v1/deepsearch/ingest endpoint
- Accepts Mission Protocol JSON
- Validates via Pydantic + quality gates
- Post-processing auto-linking (evidence → chunks via similarity)

**Auto-Linking Algorithm:**
- Match evidence.content to chunks using embeddings
- Similarity threshold 0.7 (configurable)
- Async background job
- Target ≥80% matching success rate

---

### B10.3: Pydantic Schema Package - MEDIUM PRIORITY
**Objective:** Share Mission Protocol schemas with DeepSearch  
**Key Features:**
- Standalone Python package (tracelab_schemas)
- DeepSearch pre-validates before submission
- Reduces 422 validation errors
- Version synchronized with TraceLab

**Deadline:** Week 5 (DeepSearch Sprint 3 start)

---

### B10.4: Relationship Context API - MEDIUM PRIORITY
**Objective:** Provide related entities for missions  
**Key Features:**
- GET /api/v1/missions/{id}/related endpoint
- Returns linked documents, insights, chunks
- SQL JOIN-based (no separate graph DB)
- Cached results (5min TTL)

---

### B10.5: Integration Testing & Documentation - HIGH PRIORITY
**Objective:** Enable Week 7 integration testing  
**Key Features:**
- 10+ integration test scenarios
- 5+ sample Mission Protocol JSON files
- Phased testing checklist (Week 4, 6, 7, 8)
- Integration guide for coordination

**Critical:** Supports DeepSearch Week 7 testing milestone

---

### B10.6: Sprint 10 Retrospective - STANDARD
**Objective:** Document outcomes and plan Sprint 11  
**Key Features:**
- Integration readiness assessment
- Auto-linking effectiveness metrics
- Sprint 11 backlog draft

---

## DeepSearch Integration Alignment

### All Questions Answered ✅

**1. Output Format:** Markdown (Sprint 1-2) → JSON (Sprint 3+)  
**2. Project Handling:** Config-based mapping with auto-create fallback  
**3. Authentication:** 24-hour JWT with retry-on-401, service account by Week 5  
**4. Timeline:** Integration testing Week 7 (DeepSearch Sprint 4)  
**5. Pre-Research Query:** Yes, but deferred to Sprint 5

### All Open Issues Resolved ✅

**1. Evidence Linking:** Post-processing (Option C) - TraceLab auto-links via similarity  
**2. Evidence Content:** Brief summaries (1-2 sentences), not full quotes  
**3. Pre-Validation:** Shared Pydantic schemas enable local validation  
**4. Token Refresh:** 24-hour JWT, retry on 401, no refresh tokens needed  
**5. Testing Timeline:** Week 4/6/7/8 phased coordination confirmed

---

## Key Decisions Captured

### Integration Architecture
1. **Post-processing auto-linking** - TraceLab matches evidence to chunks via similarity
2. **Schema sharing** - TraceLab exposes Pydantic package for DeepSearch pre-validation
3. **Phased integration** - Independent build (Weeks 1-6) → joint testing (Week 7+)
4. **JWT authentication** - 24-hour tokens with retry-on-401 strategy

### PEDR Implementation
5. **PEDR as TraceLab module** - Not separate service (app/services/pedr/)
6. **Simplified 3-layer** - Keyword + semantic + quality boost (reuses Sprint 09 work)
7. **Pure Python** - No JavaScript Protocol Suite imports for MVP
8. **Phased enhancement** - Phase 1 (Sprint 10), Phase 2 (Sprint 11), Phase 3+ (if valuable)

### Sprint 10 Scope
9. **6 missions, 2 weeks** - Quality search, ingestion, schema package, relationships, testing, retro
10. **Integration focus** - Foundation for autonomous knowledge loop

---

## Dependencies

```
B10.1 → B10.2 (Quality scoring used in ingestion validation)
B10.2 → B10.4 (Missions stored before relationships queryable)
B10.2 → B10.5 (Ingestion tested)
B10.3 → B10.5 (Shared schemas used in tests)
B10.4 → B10.5 (Relationship API tested)
All → B10.6 (Retrospective)
```

---

## Coordination Timeline

**TraceLab (Sprint 10):**
- Weeks 1-2: Build integration infrastructure
- Week 2 end: Deliver schema package (Week 5 deadline)

**DeepSearch (Sprint 1-3):**
- Weeks 1-4: Standalone MVP (markdown output)
- Week 4: Provide sample JSON payloads to TraceLab
- Weeks 5-6: JSON generation + TraceLab client

**Joint (Week 7):**
- Integration testing coordination
- Bug fixes and iteration
- Production validation prep

---

## TraceLab Action Items

From integration alignment:

- [ ] **B10.1:** Implement quality-aware search with boosting
- [ ] **B10.2:** Build ingestion endpoint + post-processing auto-linking
- [ ] **B10.3:** Package Pydantic schemas (deadline: Week 5)
- [ ] **B10.4:** Implement relationship context API
- [ ] **B10.5:** Create integration test suite
- [ ] **B10.6:** Document outcomes and plan Sprint 11
- [ ] Provide service account creation guide
- [ ] Document auto-linking algorithm (similarity threshold, confidence)
- [ ] Coordinate Week 7 integration testing session

---

## DeepSearch Action Items

From their responses:

- [ ] Build standalone agent (Sprint 1-2)
- [ ] Provide sample JSON payloads (Week 4)
- [ ] Implement JWT client (Sprint 3)
- [ ] Test manual uploads (Week 6)
- [ ] Coordinate integration testing (Week 7)
- [ ] Update architecture docs (PEDR now part of TraceLab)

---

## Artifacts Created

**Sprint 10 Missions:**
- `cmos/missions/sprint-10/B10.1_Quality-Aware-Search.yaml`
- `cmos/missions/sprint-10/B10.2_DeepSearch-Ingestion-Endpoint.yaml`
- `cmos/missions/sprint-10/B10.3_Pydantic-Schema-Package.yaml`
- `cmos/missions/sprint-10/B10.4_Relationship-Context-API.yaml`
- `cmos/missions/sprint-10/B10.5_Integration-Testing.yaml`
- `cmos/missions/sprint-10/B10.6_Sprint-Retrospective.yaml`

**Integration Documents:**
- `cmos/planning/DeepSearch-TraceLab-Integration-Contract.md` (sent to DeepSearch)
- `cmos/planning/DeepSearch-Responses-to-Integration-Contract.md` (received from DeepSearch)

**Planning Sessions:**
- PS-2025-11-17-001: PEDR integration strategy
- PS-2025-11-17-002: DeepSearch alignment and Sprint 10 planning

**Updates:**
- `cmos/missions/backlog.yaml` (Sprint 10 section added)
- `cmos/context/MASTER_CONTEXT.json` (integration decisions captured)
- `cmos/db/cmos.sqlite` (53 missions seeded)

---

## Validation Status

✅ Sprint 10 missions created (6 YAML files)  
✅ Backlog updated with Sprint 10  
✅ Database seeded (53 missions total)  
✅ MASTER_CONTEXT updated with integration details  
✅ Context snapshot taken (source: sprint_10_deepsearch_integration_planning)  
✅ Contexts exported to JSON  
✅ Parity validated (database ↔ files in sync)  
✅ Planning sessions captured (PS-2025-11-17-001, PS-2025-11-17-002)

---

## Integration Readiness

**TraceLab Ready:**
- ✅ Sprint 08 complete (performance optimized)
- ✅ Sprint 09 complete (hybrid search + facets)
- ✅ Sprint 10 planned (integration foundation)
- ✅ Schema contract defined
- ✅ API endpoints specified
- ✅ Testing approach documented

**DeepSearch Ready:**
- ✅ Architecture aligned (2-service not 3-service)
- ✅ Output format agreed (phased: markdown → JSON)
- ✅ Timeline coordinated (Week 7 integration)
- ✅ Requirements documented
- ✅ Sample data commitment (Week 4)

**Integration Risk:** LOW - Phased approach with multiple validation points

---

## Next Steps

**Immediate:**
- ✅ Sprint 10 fully planned and ready
- ✅ All decisions captured in database
- ✅ DeepSearch team has integration contract

**Sprint 10 Launch:**
- Start with B10.1 (Quality-Aware Search)
- Execute all 6 missions
- Deliver schema package by Week 5
- Prepare for Week 7 integration testing

**DeepSearch Coordination:**
- Week 4: Receive sample JSON payloads
- Week 5: Deliver schema package
- Week 7: Integration testing session
- Week 8: Production validation

---

**Status:** Sprint 10 ready to launch. DeepSearch integration foundation complete.

