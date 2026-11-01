# Sprint 19 Backlog Draft

**Sprint:** 19 - PEDR Optimization & Dual-Path Search
**Theme:** Make PEDR usable for interactive search through latency optimization
**Planned Start:** 2025-12-11
**Based On:** B18.6 PEDR SCOPED decision

---

## Sprint Context

Sprint 18's PEDR validation sprint concluded with a **PEDR SCOPED** decision:
- PEDR delivers meaningful precision improvements for conceptual queries
- Latency is unacceptable for interactive use (1,501ms P50 vs 200ms target)
- Root cause: Semantic layer (Qdrant) accounts for 60-80% of query time

Sprint 19 focuses on **latency optimization** to bring PEDR closer to interactive viability, while establishing a dual-path architecture for different use cases.

---

## Mission Backlog

### R19.0: Qdrant Optimization Research
**Status:** Queued
**Track:** Research
**Objective:** Research Qdrant optimization strategies to reduce semantic search latency from 700-1500ms to <200ms.

**Success Criteria:**
- HNSW parameter impact documented (ef_search, ef_construction, m)
- Caching strategies evaluated (query cache, result cache)
- Pre-warming approaches documented
- Benchmark plan for measuring improvements

**Deliverables:**
- `cmos/reports/sprint-19/qdrant-optimization-research.md`

**Estimated Hours:** 2-3

---

### B19.1: Qdrant Connection Pre-warming
**Status:** Queued
**Track:** Build
**Objective:** Eliminate cold-start penalty by pre-warming Qdrant connections on application startup.

**Success Criteria:**
- First query latency reduced from 60s to <2s
- Connection pool initialized at startup
- Health check verifies Qdrant ready before accepting requests

**Deliverables:**
- Connection pooling implementation
- Startup health check
- Benchmark before/after

**Estimated Hours:** 2-3

---

### B19.2: Semantic Search Result Caching
**Status:** Queued
**Track:** Build
**Objective:** Implement query result caching to reduce latency for repeated or similar queries.

**Success Criteria:**
- Cache hit rate >= 20% for common query patterns
- Cache invalidation on document updates
- P50 latency <100ms for cached queries
- TTL configurable (default: 5 minutes)

**Deliverables:**
- `app/services/pedr/cache.py`
- Cache metrics in response metadata
- Tests for cache behavior

**Estimated Hours:** 3-4

---

### B19.3: HNSW Parameter Tuning
**Status:** Queued
**Track:** Build
**Objective:** Tune Qdrant HNSW parameters to optimize for lower latency while maintaining acceptable recall.

**Success Criteria:**
- ef_search optimized for latency/recall trade-off
- Semantic layer latency reduced by >= 30%
- Recall degradation < 5% from baseline

**Deliverables:**
- Updated Qdrant collection configuration
- Benchmark comparison (before/after)
- Parameter selection documented

**Estimated Hours:** 3-4

---

### B19.4: Hybrid Rerank Architecture
**Status:** Queued
**Track:** Build
**Objective:** Implement "FTS first, semantic rerank" pattern for faster results with semantic enhancement.

**Success Criteria:**
- FTS returns top-50 candidates in <100ms
- Semantic rerank of top-50 in <200ms
- Combined P50 latency <300ms
- Precision comparable to full PEDR

**Deliverables:**
- `app/services/pedr/hybrid_rerank.py`
- API parameter: `rerank_mode: "full" | "hybrid"`
- Benchmark comparison

**Estimated Hours:** 4-5

---

### B19.5: Dual-Path Search API
**Status:** Queued
**Track:** Build
**Objective:** Expose both fast (FTS) and deep (PEDR) search as explicit API options.

**Success Criteria:**
- GET `/api/v1/search` - Fast FTS path (<100ms P50)
- POST `/api/v1/pedr/search` - Deep PEDR path (precision-focused)
- `latency_budget` parameter for adaptive depth
- Documentation updated

**Deliverables:**
- Updated API endpoints
- Parameter documentation
- Search mode selection in response

**Estimated Hours:** 2-3

---

### B19.6: PEDR Latency Benchmark Suite
**Status:** Queued
**Track:** Build
**Objective:** Create automated benchmark suite to track PEDR latency improvements.

**Success Criteria:**
- Reproducible benchmark with 10+ queries
- P50, P95, mean latency metrics
- Layer timing breakdown
- Comparison to baseline captured
- Can run as CI/CD check

**Deliverables:**
- `scripts/pedr_latency_benchmark.py`
- Benchmark results in telemetry
- Threshold alerts for regression

**Estimated Hours:** 2-3

---

### B19.7: Sprint 19 Retrospective
**Status:** Queued
**Track:** Retrospective
**Objective:** Document Sprint 19 outcomes and evaluate PEDR latency improvements.

**Success Criteria:**
- Sprint retrospective document created
- Latency improvement quantified
- Decision: PEDR ready for interactive use? (Yes/No/More work)
- Sprint 20 direction determined

**Deliverables:**
- `cmos/reports/sprint-19/retrospective.md`
- MASTER_CONTEXT updated
- Context snapshot taken

**Estimated Hours:** 1-2

---

## Sprint 19 Success Criteria

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| PEDR P50 Latency | 1,501ms | <400ms | 75% reduction |
| Cold Start | 60s | <2s | Via pre-warming |
| Cache Hit Rate | 0% | >=20% | For common queries |
| Semantic Layer | 700-1500ms | <300ms | Via HNSW tuning |

---

## Dependencies & Risks

**Dependencies:**
- Qdrant configuration access for HNSW tuning
- Baseline benchmark data from Sprint 18

**Risks:**
- HNSW tuning may not achieve target latency reduction
- Cache effectiveness depends on query patterns
- Hybrid rerank may degrade precision more than acceptable

**Mitigations:**
- B19.6 benchmark suite enables data-driven decisions
- Multiple optimization strategies in parallel
- Fallback: maintain dual-path if interactive latency not achieved

---

## Alternative Sprint 19 (if optimization deferred)

If latency optimization is deferred, Sprint 19 could focus on PEDR's approved use cases:

1. **MCP Integration** - PEDR as DeepSearch backend
2. **Batch Processing** - Scheduled enrichment jobs
3. **Quality Dashboard** - Governance scoring visualization
4. **Graph Explorer** - Related entity discovery UI

---

## Notes

Sprint 19 assumes the goal is to make PEDR viable for interactive search. If the team decides PEDR should remain scoped to batch/async use cases only, the alternative backlog above would be more appropriate.

The decision of which path to pursue should be made before Sprint 19 execution begins.
