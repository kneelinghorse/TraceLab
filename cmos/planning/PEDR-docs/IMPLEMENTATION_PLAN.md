# PEDR Implementation Plan - Simplified

**Date**: 2025-11-16  
**Approach**: Build as Tracelab module (not separate microservice)  
**Timeline**: 1-2 weeks (1 sprint + optional polish)  
**Status**: Ready to implement

---

## Executive Summary

PEDR is **THE intelligent search engine** for the autonomous knowledge system. It replaces simple RAG with protocol-enhanced multi-dimensional search that's quality-aware, governance-safe, and relationship-rich.

### Key Architectural Decision: Build Inside Tracelab

**PEDR is a module within Tracelab** (`app/services/pedr/`), not a separate microservice.

**Why this is smarter**:
- ✅ Reuse Tracelab's PostgreSQL FTS (already built in Sprint 09!)
- ✅ Reuse Tracelab's Qdrant embeddings (already built!)
- ✅ Reuse Tracelab's JWT auth (no coordination needed)
- ✅ Direct database access (no polling/syncing)
- ✅ Single deployment, single codebase
- ✅ Faster: 1-2 weeks instead of 3-4 weeks

### Why PEDR is Better Than Simple RAG

**Simple RAG** (Tracelab's basic Qdrant search):
- Vector similarity only
- No quality awareness (drafts rank equally with complete missions)
- No governance filtering
- Isolated chunks without context

**Protocol-Enhanced Search** (PEDR module):
- ✅ **Quality-aware ranking**: Complete missions rank 2x higher (Semantic Protocol)
- ✅ **3-layer search**: Keyword (PostgreSQL FTS) + Semantic (Qdrant) + Quality boost
- ✅ **Governance filtering**: PII handling, business impact (PostgreSQL WHERE clauses)
- ✅ **Leverages existing infrastructure**: No duplicate systems
- ✅ **Simple to maintain**: One codebase, one deployment

### What PEDR Actually Adds

PEDR enhances Tracelab's existing search with:
1. **Better ranking algorithm** - Uses Semantic Protocol quality scores
2. **Quality boosting** - Complete missions rank 2x higher than drafts
3. **Governance filtering** - Safe for automated agents
4. **Optional: Graph context** - Add later if relationship traversal proves valuable

**Timeline**: 1-2 weeks (vs 6 months building from scratch, vs 3-4 weeks as microservice)

---

## The Plan (Simplified)

### Week 1: Enhanced Search Module (Core)

**In Tracelab repository**: `app/services/pedr/`

**Day 1-2: Import Semantic Protocol**
```bash
# In Tracelab repo
mkdir -p app/services/pedr/protocols/
# Copy semantic-protocol.js (just the core, not orchestrator)
# Adapt for Python if needed, or use Node subprocess

# Create adapter
touch app/services/pedr/adapter.py
touch app/services/pedr/search.py
```

**Day 3-4: Enhanced Search Endpoint**
```python
# app/api/v1/pedr.py (new file)
@router.post("/pedr/search")
async def pedr_search(query: str, filters: SearchFilters, db: Session):
    # 1. Keyword search (reuse existing PostgreSQL FTS)
    keyword_results = await search_missions_fts(db, query)
    
    # 2. Semantic search (reuse existing Qdrant)
    semantic_results = await search_missions_qdrant(query)
    
    # 3. Quality boost (NEW - use Semantic Protocol)
    ranked = boost_by_quality(keyword_results, semantic_results)
    
    # 4. Governance filter (PostgreSQL WHERE clauses)
    filtered = apply_governance_filters(ranked, filters)
    
    return filtered[:20]
```

**Day 5: Testing & Integration**
- Test quality ranking (complete missions > drafts)
- Test governance filters (PII filtering works)
- Coordinate with DeepSearch team
- Update API documentation

**Deliverable**: Enhanced search endpoint in Tracelab (`POST /api/v1/pedr/search`)

---

### Week 2 (Optional): Graph Context

**Only if relationship context proves valuable:**

```python
# app/services/pedr/graph.py
class RelationshipGraph:
    def get_related(self, mission_id: UUID, db: Session):
        # Use SQL joins (no separate graph database needed for MVP)
        documents = db.query(Document).filter(
            Document.project_id == mission.project_id
        ).all()
        
        insights = db.query(Insight).join(insight_sources).filter(
            insight_sources.c.chunk_id.in_([chunk.id for chunk in chunks])
        ).all()
        
        return {
            'documents': documents,
            'insights': insights,
            'chunks': chunks
        }
```

**Deliverable**: `GET /api/v1/pedr/missions/{id}/related` endpoint

---

### Total Timeline: 1-2 weeks

**Week 1**: Core enhanced search (MUST HAVE)  
**Week 2**: Graph context (NICE TO HAVE)

---

## Architecture: PEDR as Tracelab Module

```
┌─────────────┐         ┌──────────────┐
│ Human Users │         │  DeepSearch  │
└──────┬──────┘         └──────┬───────┘
       │                       │
       │ "What do we          │ "Does research
       │  know about X?"      │  on X exist?"
       │                      │
       └──────────┬───────────┘
                  │
                  │ ALL queries go to Tracelab
                  ↓
       ┌──────────────────────────────────┐
       │         Tracelab API             │
       │                                  │
       │  POST /api/v1/missions           │ ← Write
       │  POST /api/v1/pedr/search  ⭐    │ ← Enhanced search
       │  GET  /api/v1/missions/{id}      │ ← Read detail
       │                                  │
       │  ┌─────────────────────────────┐│
       │  │  app/services/pedr/         ││ ← PEDR module
       │  │   - search.py               ││
       │  │   - protocols/semantic.py   ││
       │  │   - adapter.py              ││
       │  │                             ││
       │  │  Reuses:                    ││
       │  │   - PostgreSQL FTS          ││
       │  │   - Qdrant embeddings       ││
       │  │   - JWT auth                ││
       │  └─────────────────────────────┘│
       │                                  │
       │  PostgreSQL + Qdrant             │
       └──────────────────────────────────┘
                     ▲
                     │ writes
              ┌──────┴───────┐
              │  DeepSearch  │
              └──────────────┘
```

**Key Points**: 
- PEDR is a **module** inside Tracelab, not a separate service
- Reuses existing PostgreSQL FTS and Qdrant infrastructure
- No auth coordination needed (same JWT system)
- No deployment complexity (same service)
- Direct database access (no polling/syncing)

---

## What Makes PEDR Better Than Simple RAG?

### The Difference in Action

**Scenario**: User searches "passwordless authentication"

#### Simple RAG (Tracelab Qdrant only)
```python
query_embedding = embed("passwordless authentication")
results = qdrant.search(query_embedding, top_k=10)

# Returns:
# 1. Chunk from incomplete draft (0.92 similarity)
# 2. Chunk from complete mission (0.91 similarity)
# 3. Chunk with PII data (0.89 similarity)
# 4. Random document snippet (0.88 similarity)
# ...isolated text chunks with no context
```

**Problems**:
- Draft research ranks as high as complete
- PII mixed with public data
- No context about quality or relationships
- Just similarity scores

#### Protocol-Enhanced Search (PEDR)
```python
results = pedr.search("passwordless authentication", filters={
    "allow_pii": False,
    "min_quality_gates": 4
})

# Returns:
# 1. Mission DRM.0.5 (complete, 5/5 gates, high impact) - 0.95 score
#    └─ Quality boost: +0.20 for complete status
#    └─ Related: 5 documents, 12 insights, 47 chunks
#    └─ Validated: 2025-11-10, no contradictions
#
# 2. Mission DRM.0.3 (complete, 5/5 gates) - 0.88 score
#    └─ Quality boost: +0.20
#    └─ Related: 3 documents, 8 insights
#
# 3. Document DOC-123 (linked to DRM.0.5) - 0.82 score
#    └─ Context: Part of DRM.0.5 evidence chain
#
# [Incomplete missions and PII-containing content filtered out]
```

**Advantages**:
- ✅ Complete missions ranked 2x higher
- ✅ PII automatically filtered
- ✅ Full relationship context included
- ✅ Quality metadata visible
- ✅ Evidence trail traceable

### 1. Quality-Aware Ranking (Semantic Protocol)

**Value**: Humans and agents get validated, complete research first—not drafts or fragments.

### 2. Governance Filtering (Semantic Protocol)

**Value**: Safe for automated agents. PII handling, business impact, and compliance built-in.

### 3. Relationship Context (Relational Protocol)

**Value**: Not just "here's a chunk"—get the full story (mission → supporting docs → derived insights).

### 4. Multi-Dimensional Fusion

**Value**: Combines keyword + semantic + quality + governance + relationships for genuinely better ranking than similarity alone.

---

## Success Criteria

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Search latency | <200ms p95 | Fast enough for both humans and agents |
| Search relevance | Top-10 >80% precision | Complete missions rank higher |
| Quality awareness | 2x boost for complete | Semantic Protocol scoring works |
| Code complexity | <500 LOC | Keep it simple, maintainable |
| No new infrastructure | 0 new services | Reuse PostgreSQL + Qdrant |

---

## Can Add Later (If Needed)

### Phase 2 Enhancements
- **Basic temporal metrics**: Research completion rate, velocity trends
- **Advanced graph queries**: Centrality, blast radius, knowledge gaps
- **Smart recommendations**: "You might also be interested in..."

### Phase 3 Nice-to-Haves
- Dashboard with visualizations
- Full temporal analytics (all 10 metrics)
- Pragmatic automation (auto-prioritization)

**But**: Only if we see concrete need after MVP usage

---

## Decision Rationale

**Why hybrid?**
- Protocol Suite has 20+ metrics, we need ~5
- Full orchestration is overkill for search
- Semantic + Relational protocols solve 80% of needs
- Can add advanced features later if valuable

**Why not build from scratch?**
- Semantic Protocol's quality scoring is proven (validated across 10 domains)
- Relational Protocol's graph analysis is tested
- Don't reinvent what works

**Why not use full Protocol Suite?**
- Temporal analytics: Overkill for "find research on X"
- Pragmatic automation: Don't know if we need it yet
- Orchestration: Unnecessary complexity

**Result**: Practical implementation that solves actual user needs

---

## Next Steps

1. **Review this plan** - Any concerns or questions?
2. **Set up environment** - Import Protocol Suite components
3. **Start Sprint 1** - Build Tracelab adapter
4. **Ship in 3-4 weeks** - Learn from usage, iterate

---

**Questions to Consider**:
- Does this solve DeepSearch's "check for existing research" need? ✅ Yes
- Does this solve human "search our knowledge base" need? ✅ Yes  
- Is it worth 3-4 weeks? ✅ Yes (vs 2 weeks DIY, we get proven quality scoring)
- Can we add more later? ✅ Yes (Phase 2/3 enhancements clear)

**Recommendation**: Proceed with Sprint 1

---

**Status**: Approved hybrid approach  
**Timeline**: Start immediately, ship in 3-4 weeks  
**Risk**: Low (using proven components, building simple search)

