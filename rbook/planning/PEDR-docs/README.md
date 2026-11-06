# PEDR - Protocol-Enhanced Deep Research

**Status**: Architecture aligned, ready for Sprint 1  
**Timeline**: 3-4 weeks to production  
**Approach**: Hybrid (proven protocols + simple search)

---

## What is PEDR?

**PEDR is THE intelligent search engine** for the autonomous knowledge system.

It replaces simple vector RAG with **protocol-enhanced multi-dimensional search** that's quality-aware, governance-safe, and relationship-rich.

### Why PEDR Exists

**The Problem**: Simple RAG (vector similarity) treats all content equally—drafts rank the same as complete research, PII mixed with public data, no relationship context.

**The Solution**: Protocol-enhanced search that understands quality, governance, and relationships—making research genuinely findable and usable.

---

## Core Value Proposition

PEDR provides **6 dimensions of search intelligence**:

1. **Lexical** - Keyword matching, exact terms
2. **Semantic** - Intent and meaning similarity
3. **Syntactic** - Type filtering (mission, document, insight)
4. **Pragmatic** - Intent classification (Create/Read/Update/Delete/Execute)
5. **Governance** - PII filtering, business impact, compliance
6. **Relational** - Relationship context (mission → docs → insights)

**Result**: Search results that are quality-ranked, governance-safe, and context-rich.

---

## The Ecosystem

```
┌─────────────┐         ┌──────────────┐
│ Human Users │         │  DeepSearch  │
│             │         │    Agent     │
└──────┬──────┘         └──────┬───────┘
       │                       │
       │ All queries           │
       └───────────┬───────────┘
                   │
                   ↓
         ┌─────────────────┐
         │      PEDR       │ ← THE Search Engine
         │   (This repo)   │
         └────────┬────────┘
                  │
                  │ indexes
                  ↓
         ┌─────────────────┐
         │    Tracelab     │ ← Storage + Validation
         │                 │
         │  PostgreSQL     │
         │  Qdrant         │
         └────────▲────────┘
                  │
                  │ writes
         ┌────────┴────────┐
         │   DeepSearch    │
         └─────────────────┘
```

**Key Point**: Tracelab stores, PEDR searches. No one queries Tracelab directly.

---

## Documentation Index

### Start Here
- **[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)** - Executive summary and sprint plan
- **[protocol-integration-plan.md](./protocol-integration-plan.md)** - Technical implementation details

### Architecture & Design
- **[architecture-review-notes.md](./architecture-review-notes.md)** - Architecture decisions and rationale
- **[tracelab-to-pedr-mapping.md](./tracelab-to-pedr-mapping.md)** - Data schema mapping

### Reference
- **[adaptive-capacity.md](./adaptive-capacity.md)** - Mathematical framework foundation
- **Protocol Suite Documentation**: `cmos/planning/protocol-enhanced-deep-research/`

---

## Implementation Approach: Hybrid

**What We're Using**:
- ✅ **Semantic Protocol** - Quality-aware manifests, governance scoring (proven)
- ✅ **Relational Protocol** - Graph relationships, dependency analysis (proven)

**What We're Building**:
- 🔨 Simple 2-layer search (keyword + semantic)
- 🔨 Quality boosting (use Semantic Protocol scores)
- 🔨 FastAPI endpoint

**What We're Skipping** (for MVP):
- ❌ 10 temporal metrics (overkill)
- ❌ Pragmatic automation (not needed yet)
- ❌ Complex orchestration (unnecessary)

**Can add later** if proven valuable in Phase 2.

---

## Quick Start (For Sprint 1)

```bash
# 1. Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic psycopg2-binary

# 2. Import Protocol Suite components
# (Semantic Protocol + Relational Protocol only)

# 3. Connect to Tracelab
export TRACELAB_POSTGRES_URI="postgresql://user:pass@localhost:5432/tracelab"

# 4. Start development
uvicorn pedr.api.main:app --reload --port 8042
```

---

## Success Metrics

| Metric | Target | Why |
|--------|--------|-----|
| Search latency (agent) | <100ms p95 | DeepSearch can't wait |
| Search latency (human) | <500ms p95 | Good UX |
| Search relevance | >80% top-10 precision | Complete missions rank higher |
| Quality awareness | 2x boost for complete | Semantic Protocol works |
| API uptime | >99% | Always available |

---

## Timeline

**Sprint 1** (2 weeks): Core search + protocol integration  
**Sprint 2** (1-2 weeks): Graph context + DeepSearch integration  
**Total**: 3-4 weeks to production

---

## Project Structure

```
PEDR/
├── docs/                    # This documentation
│   ├── README.md            # You are here
│   ├── IMPLEMENTATION_PLAN.md
│   └── protocol-integration-plan.md
│
├── cmos/                    # CMOS project management
│   ├── planning/            # Planning documents
│   ├── research/            # Research reports (DRS.0.1-0.04)
│   ├── missions/            # Mission tracking
│   └── context/             # Project context and history
│
├── src/                     # Application code (to be built)
│   ├── protocols/           # Protocol references
│   └── pedr/                # PEDR implementation
│       ├── adapter/         # Tracelab adapter
│       ├── search/          # Search engine
│       └── api/             # FastAPI endpoints
│
└── tests/                   # Test suite (to be built)
```

---

## Key Decisions

### 1. PEDR is THE Search Layer
**Not** just a helper for DeepSearch. **THE** primary search interface for all users.

### 2. Hybrid Approach
Use proven Semantic + Relational protocols, skip overkill (temporal/pragmatic).

### 3. Quality-First
Complete, validated research ranks 2x higher than drafts.

### 4. Governance-Safe
PII filtering, business impact, compliance built-in.

### 5. Relationship-Rich
Full context (mission → docs → insights), not isolated chunks.

---

## Questions?

- **For implementation**: See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
- **For technical details**: See [protocol-integration-plan.md](./protocol-integration-plan.md)
- **For architecture decisions**: See [architecture-review-notes.md](./architecture-review-notes.md)

---

**Status**: Ready to implement  
**Next**: Start Sprint 1  
**Owner**: PEDR Team
