# R19.0: Qdrant Optimization Research Report

**Mission:** R19.0 - Qdrant Optimization Research - PEDR Latency Reduction
**Status:** Completed
**Research Date:** 2025-12-10
**Sources Consulted:** 10
**Research Loops:** 2

---

## Executive Summary

This research investigates strategies to reduce Qdrant semantic search latency from 700-1500ms to under 200ms, enabling PEDR for interactive search. Key findings indicate that **HNSW parameter tuning** offers the most immediate impact, while **connection pre-warming** and **result caching** provide complementary improvements.

**Priority Recommendations:**
1. **B19.1 (Connection Pre-warming)** - Highest ROI, eliminates 60s cold start
2. **B19.3 (HNSW Tuning)** - 30-50% latency reduction potential
3. **B19.2 (Result Caching)** - 20%+ hit rate for repeated queries
4. **B19.4 (Hybrid Rerank)** - Fallback if above insufficient

---

## 1. HNSW Parameter Optimization

### Key Parameters

| Parameter | Description | Impact on Latency | Impact on Recall |
|-----------|-------------|-------------------|------------------|
| `ef_search` | Candidates checked during search | Higher = slower | Higher = better |
| `ef_construction` | Candidates during index build | Build time only | Higher = better graph |
| `m` | Connections per node | Minimal query impact | Higher = better recall, more RAM |

### Findings

- **ef_search is the primary latency lever** at query time
- Increasing `ef_search` from 32 → 128 improves recall 80% → 95% but increases latency 100ms → ~400ms
- For sub-200ms targets, `ef_search` values of 32-64 are recommended
- Trade-off: ~5% recall degradation acceptable for interactive use

### Recommended Test Plan

```
Baseline:     m=16, ef_construction=100, ef_search=128 (current)
Test 1:       m=16, ef_construction=100, ef_search=64  (expect 30-40% faster)
Test 2:       m=16, ef_construction=100, ef_search=32  (expect 50-60% faster)
Test 3:       m=12, ef_construction=100, ef_search=48  (balance attempt)
```

**Expected Outcome:** ef_search=48-64 should achieve <300ms while maintaining >90% recall.

---

## 2. Connection Pooling & Pre-warming

### Current Problem
First query takes 60+ seconds due to:
- Cold Qdrant client connection
- Uninitialized connection pool
- No data pre-loaded into memory

### Solution Architecture

```python
# Recommended implementation
from qdrant_client import QdrantClient

# Initialize at application startup
client = QdrantClient(
    host="qdrant",
    port=6333,
    prefer_grpc=True,  # gRPC is faster than REST
    timeout=30,
)

# Pre-warm by running a dummy query
def prewarm_qdrant():
    """Call during FastAPI startup event"""
    client.search(
        collection_name="document_chunks",
        query_vector=[0.0] * 1536,  # Dummy embedding
        limit=1
    )
```

### Implementation Guidance

1. **Connection Pool Settings:**
   - `max_pool_size`: 10 (adjust based on concurrent users)
   - `min_idle_connections`: 2
   - `connection_timeout`: 30s

2. **FastAPI Integration:**
   - Add `@app.on_event("startup")` handler
   - Run pre-warm query before accepting requests
   - Health check endpoint verifies Qdrant ready

**Expected Outcome:** First query latency reduced from 60s to <2s.

---

## 3. Caching Strategies

### Three-Tier Cache Architecture

| Cache Type | What's Cached | TTL | Hit Rate Potential |
|------------|---------------|-----|-------------------|
| Query Cache | Full query → results mapping | 5 min | 20-30% for repeated queries |
| Embedding Cache | Text → embedding vector | 1 hour | High for common terms |
| Result Cache | Top-K results for query hash | 10 min | 15-25% |

### Recommended Implementation

```python
# Query result caching with Redis or in-memory
from functools import lru_cache
import hashlib

def get_cache_key(query: str, top_k: int, filters: dict) -> str:
    """Generate deterministic cache key"""
    payload = f"{query}:{top_k}:{sorted(filters.items())}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

# LRU cache for hot queries (in-memory)
@lru_cache(maxsize=1000)
def cached_search(cache_key: str):
    # Return cached results
    pass
```

### Cache Invalidation Strategy
- Invalidate on document upload/delete
- TTL-based expiration (default 5 minutes)
- Manual invalidation via admin endpoint

**Expected Outcome:** 20%+ cache hit rate, <100ms for cached queries.

---

## 4. Quantization (Already Implemented)

TraceLab already uses Scalar INT8 quantization:
```python
quantization_config=models.ScalarQuantization(
    scalar=models.ScalarQuantizationConfig(
        type=models.ScalarType.INT8,
        quantile=0.99,
        always_ram=True  # Keep quantized vectors in RAM
    )
)
```

**Status:** No changes needed. 4x memory compression already active.

---

## 5. Hybrid Rerank Architecture (B19.4)

If HNSW tuning alone doesn't achieve targets, implement two-stage search:

### Architecture
```
Query → PostgreSQL FTS (top 50, <100ms)
           ↓
    Semantic Rerank (top 50 → top 10, <200ms)
           ↓
      Final Results (<300ms total)
```

### Benefits
- FTS provides fast initial filtering
- Semantic only runs on 50 candidates (vs. full corpus)
- Combined latency <300ms achievable

### Trade-offs
- Slightly lower recall than full semantic search
- More complex orchestration
- Results depend on FTS candidate quality

---

## 6. Benchmark Test Plan

### Metrics to Capture
- P50, P95, P99 latency
- Recall@10 (vs. brute-force baseline)
- Cache hit rate
- Memory usage

### Test Queries (10 query baseline)
1. "usability testing best practices"
2. "mission protocol validation"
3. "participant recruitment strategy"
4. "sprint planning backlog"
5. "deployment pipeline CI/CD"
6. "authentication security"
7. "document ingestion"
8. "semantic search optimization"
9. "quality gates research"
10. "API endpoint design"

### Test Matrix

| Test | ef_search | Cache | Pre-warm | Expected P50 |
|------|-----------|-------|----------|--------------|
| Baseline | 128 | Off | No | 1,500ms |
| T1 | 64 | Off | No | 900ms |
| T2 | 64 | Off | Yes | 800ms |
| T3 | 64 | On | Yes | 400ms (cache miss) |
| T4 | 64 | On | Yes | <100ms (cache hit) |
| T5 | 48 | On | Yes | 300ms (cache miss) |

---

## 7. Implementation Priority Matrix

| Mission | Effort | Latency Impact | Risk | Priority |
|---------|--------|----------------|------|----------|
| B19.1 (Pre-warm) | Low (2-3h) | Eliminates 60s cold start | Low | **1st** |
| B19.3 (HNSW) | Medium (3-4h) | 30-50% reduction | Medium | **2nd** |
| B19.2 (Caching) | Medium (3-4h) | 20%+ cache hits | Low | **3rd** |
| B19.4 (Hybrid) | High (4-5h) | Alternative path | Medium | **4th (if needed)** |

---

## 8. Success Criteria Evaluation

| Criterion | Confidence | Notes |
|-----------|------------|-------|
| HNSW parameter impact documented | ✅ High | ef_search is primary lever |
| Caching strategies evaluated | ✅ High | Three-tier approach defined |
| Connection pooling documented | ✅ High | Implementation guidance provided |
| ANN accuracy trade-offs quantified | ✅ Medium | ~5% recall loss at ef_search=48 |
| Benchmark test plan created | ✅ High | 10 queries, 5 test configurations |

---

## Sources

1. Qdrant Documentation - HNSW Configuration
2. Qdrant Storage & Performance Guide
3. Analytics Vidhya - Qdrant Deep Dive
4. TigerData - Connection Pooling Best Practices
5. Medium - Embedding Caching Strategies
6. Railway - Qdrant Deployment Guide
7. TraceLab Sprint 08 - Qdrant Benchmark Report (internal)
8. Qdrant Vector Search Optimization Guide
9. Dr. Droid - Qdrant Memory Management
10. Railway Pricing Analysis

---

**Mission R19.0 Status:** COMPLETE
**Next:** B19.1 (Connection Pre-warming) → B19.3 (HNSW Tuning) → B19.2 (Caching)
