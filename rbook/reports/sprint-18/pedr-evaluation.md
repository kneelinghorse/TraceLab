# PEDR Decision Gate Evaluation - B18.6

**Evaluation Date:** 2025-12-10
**Sprint:** 18 - PEDR Protocol Implementation
**Evaluator:** Claude Opus 4.5

## Executive Summary

After comprehensive evaluation of PEDR (Pragmatic-Enriched Document Retrieval) against the baseline keyword-only search, the recommendation is:

**DECISION: PEDR SCOPED**

PEDR shows meaningful precision improvements for conceptual queries but does not meet the latency requirements for primary search interface. The architecture is sound and worth preserving for targeted use cases.

---

## Evaluation Criteria Recap

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| Precision improvement | >= 15% | **Partial** - Significant for conceptual queries, marginal for exact-match |
| P50 Latency | < 200ms | **FAIL** - 1,501ms (7.5x threshold) |
| P95 Latency | < 200ms | **FAIL** - 63.5s (cold start skew) |

---

## Performance Comparison

### Latency Analysis

| Metric | Baseline (FTS) | PEDR (5-layer) | Change |
|--------|---------------|----------------|--------|
| P50 Latency | 59.8ms | 1,501ms | +2,412% (25x slower) |
| P95 Latency | 31.6s | 63.5s | +101% |
| Mean Latency | 3,217ms | 7,609ms | +136% |
| Warm Query P50 | ~60ms | ~1,100ms | ~18x slower |

**Root Cause:** Semantic search (Qdrant vector similarity) accounts for 400-1,500ms per query. This is the dominant latency contributor.

### Layer Timing Breakdown (warm queries)

| Layer | Avg Latency | % of Total |
|-------|-------------|------------|
| Semantic (Qdrant) | 700-1,500ms | 60-80% |
| Lexical (PostgreSQL FTS) | 300-420ms | 20-30% |
| Governance (Quality) | 110-120ms | 8-10% |
| Syntactic | <1ms | <0.1% |
| Pragmatic | <1ms | <0.1% |
| RRF Fusion | <3ms | <0.2% |

### Precision Analysis

#### Queries with Clear PEDR Improvement

1. **"usability testing best practices"**
   - Baseline: Top result was about PHP traits (irrelevant)
   - PEDR: Top results about "not a substitute for user testing" and task-based testing (highly relevant)
   - **Improvement: Significant**

2. **"participant recruitment strategy"**
   - Baseline: Top result was YAML stakeholder config (irrelevant)
   - PEDR: Top results about AI in research and formulating research goals (more relevant)
   - **Improvement: Moderate**

3. **"sprint planning backlog prioritization"**
   - Baseline: Only 2 results with very low scores (0.003)
   - PEDR: 5 results with strategic recommendations and sprint methodology content
   - **Improvement: Significant**

#### Queries with Marginal or No Improvement

1. **"mission protocol validation"**
   - Baseline: Excellent precision (0.60 keyword score)
   - PEDR: Good results but lower scores due to RRF normalization
   - **Improvement: None** (already optimal for exact-match queries)

2. **"deployment pipeline CI/CD"**
   - Both systems returned same relevant CR2.3 document
   - **Improvement: Marginal**

### Qualitative Assessment

**PEDR Strengths:**
- Multi-layer fusion provides more diverse results
- Intent classification working (90% confidence on "user research" queries)
- Type detection functional (85% confidence for "mission" type)
- Quality scoring integration enables governance-aware ranking
- Results include contributions from multiple layers, improving recall

**PEDR Weaknesses:**
- Latency unacceptable for interactive use (target was <200ms)
- Semantic layer bottleneck (Qdrant query latency)
- RRF scores are lower and harder to interpret than raw keyword scores
- Cold start penalty severe (~60s for first query)

---

## Technical Architecture Assessment

### What Works Well
1. **RRF Fusion Algorithm** - Correctly combines heterogeneous rankers without score normalization issues
2. **Layer Modularity** - Each layer can be enabled/disabled and weighted independently
3. **Syntactic Detection** - Accurate type inference from query text
4. **Pragmatic Classification** - Intent detection functioning correctly
5. **Code Quality** - Well-structured, documented, testable implementation

### What Needs Work
1. **Semantic Layer Latency** - Consider caching, pre-computation, or approximate nearest neighbors
2. **Cold Start** - First query takes 60+ seconds; needs connection pooling or warm-up
3. **Batch Processing** - Run semantic search in parallel with lexical when possible

---

## Recommendation

### Primary Search Interface: **NO**

PEDR cannot serve as the primary search interface due to latency (1.5s P50 vs 200ms target). Users expect sub-200ms response times for search.

### Scoped Use Cases: **YES**

Preserve PEDR for:
1. **Deep Research Queries** - When precision matters more than speed
2. **MCP Server Integration** - Background searches where latency is acceptable
3. **Batch Processing** - Reranking or enrichment of cached results
4. **Quality-Aware Queries** - When governance/quality scoring is required
5. **Related Entity Discovery** - Graph expansion for exploration use cases

### Recommended Architecture

```
User Query
    |
    v
Fast Path: PostgreSQL FTS (60ms) ────> Interactive Results
    |
    v
Slow Path: PEDR (1.5s) ────> Enhanced Results (async)
    |
    v
Cache: Store PEDR results for common queries
```

---

## Next Steps (if PEDR proceeds)

1. **Latency Optimization (Sprint 19+)**
   - Implement approximate nearest neighbors (HNSW tuning)
   - Add result caching layer
   - Pre-warm Qdrant connections
   - Consider hybrid approach: FTS first, semantic rerank top-N

2. **DeepSearch Integration**
   - PEDR's quality scoring aligns well with DeepSearch's needs
   - Semantic layer enables concept-based research queries
   - Graph expansion (B18.5) supports mission-aware retrieval

3. **API Design**
   - Expose fast search (FTS) and deep search (PEDR) as separate endpoints
   - Add `latency_budget` parameter to control depth

---

## Conclusion

PEDR delivers on its promise of improved precision for conceptual queries through multi-layer fusion, but fails the latency requirement by an order of magnitude. The implementation is architecturally sound and worth preserving for appropriate use cases.

**Final Decision: PEDR SCOPED**
- Not primary search (latency)
- Yes for deep research, MCP, and batch processing
- Optimize latency before reconsidering for interactive use

---

## Artifacts

| Artifact | Location |
|----------|----------|
| Baseline Capture | `cmos/reports/sprint-18/pedr-baseline-capture.json` |
| PEDR Benchmark | `cmos/reports/sprint-18/pedr-benchmark-b18.6.json` |
| Implementation | `app/services/pedr/` |
| Tests | `tests/test_pedr_*.py` |

---

**Mission B18.6 Status:** COMPLETE
**Decision Captured:** 2025-12-10
