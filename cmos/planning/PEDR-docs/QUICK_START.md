# PEDR Quick Start - Build in Tracelab

**Timeline**: 1-2 weeks  
**Location**: Tracelab repository (`app/services/pedr/`)  
**Approach**: Module, not microservice

---

## What Are We Building?

Enhanced search endpoint for Tracelab that ranks results by quality using Semantic Protocol.

```
POST /api/v1/pedr/search
{
  "query": "passwordless auth",
  "filters": {
    "allow_pii": false,
    "min_quality_gates": 4
  }
}

Returns: Top 20 results, ranked by:
- Keyword relevance
- Semantic similarity
- Quality score (complete missions rank 2x higher)
- Governance filters applied
```

---

## Week 1: Core Implementation

### Day 1-2: Setup

```bash
cd /path/to/tracelab

# Create PEDR module
mkdir -p app/services/pedr/protocols/
touch app/services/pedr/__init__.py
touch app/services/pedr/search.py
touch app/services/pedr/adapter.py

# Copy Semantic Protocol
# From: /path/to/metrics_and_protocols/semantic-protocol-v3.2.0.js
# To: app/services/pedr/protocols/semantic.py
# (Adapt JavaScript → Python or use Node subprocess)
```

### Day 3-4: Build Search Endpoint

```python
# app/api/v1/pedr.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.services.pedr.search import PEDRSearchService

router = APIRouter(prefix="/pedr", tags=["pedr"])

@router.post("/search")
async def search(
    query: str,
    filters: Optional[SearchFilters] = None,
    db: Session = Depends(get_db)
):
    service = PEDRSearchService(db)
    results = await service.search(query, filters)
    return {"results": results, "total": len(results)}
```

```python
# app/services/pedr/search.py
class PEDRSearchService:
    def __init__(self, db: Session):
        self.db = db
        self.semantic = SemanticProtocol()
    
    async def search(self, query: str, filters: SearchFilters):
        # 1. Keyword (reuse existing)
        keyword_results = self.keyword_search(query)
        
        # 2. Semantic (reuse existing)
        semantic_results = self.semantic_search(query)
        
        # 3. Quality boost (NEW)
        ranked = self.boost_by_quality(keyword_results + semantic_results)
        
        # 4. Governance filter
        filtered = self.filter_by_governance(ranked, filters)
        
        return filtered[:20]
    
    def boost_by_quality(self, results):
        for result in results:
            manifest = self.semantic.createManifest({
                'governance': {
                    'businessImpact': self.calc_impact(result.mission)
                }
            })
            # Boost complete missions
            if result.mission.status == 'complete':
                result.score *= (1 + manifest.element.criticality)
        
        return sorted(results, key=lambda r: r.score, reverse=True)
```

### Day 5: Test & Deploy

```python
# tests/test_pedr.py
def test_complete_missions_rank_higher():
    results = pedr_search("auth")
    # First result should be complete
    assert results[0].mission.status == "complete"
    # Complete should score 2x higher than draft
    assert results[0].score > results[1].score * 1.5
```

---

## What We Reuse from Tracelab

- ✅ PostgreSQL FTS (missions, documents - already indexed)
- ✅ Qdrant embeddings (text-embedding-3-small - already working)
- ✅ JWT auth (no new auth needed)
- ✅ Database models (Mission, Document, Insight)
- ✅ API patterns (FastAPI routers)

---

## What's New

- `app/services/pedr/` module (~500 LOC)
- `app/api/v1/pedr.py` endpoint
- Semantic Protocol quality scoring
- Quality-aware ranking algorithm

---

## Week 2 (Optional): Graph Context

```python
# app/services/pedr/graph.py
@router.get("/missions/{mission_id}/related")
async def get_related(mission_id: UUID, db: Session):
    # SQL joins to find related entities
    mission = db.query(Mission).get(mission_id)
    documents = db.query(Document).filter_by(
        project_id=mission.project_id
    ).all()
    # ... more relations
    
    return {
        "mission": mission,
        "related_documents": documents,
        "related_insights": insights
    }
```

---

## Success Criteria

| What | Target |
|------|--------|
| Search latency | <200ms p95 |
| Complete missions rank higher | 2x boost |
| Code added | <500 LOC |
| New infrastructure | 0 services |

---

## References

- **Full plan**: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
- **Technical details**: [protocol-integration-plan.md](./protocol-integration-plan.md)
- **Semantic Protocol**: `cmos/planning/protocol-enhanced-deep-research/PROTOCOL_ARCHITECTURE_GUIDE.md`

---

**Status**: Ready to implement in Tracelab  
**Next**: Create `app/services/pedr/` directory in Tracelab repo

