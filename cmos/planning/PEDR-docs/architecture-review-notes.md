# PEDR Architecture Review - Session Notes

**Date**: 2025-11-16  
**Session**: PS-2025-11-16-002 (Planning)  
**Purpose**: PEDR architecture review in context of Autonomous Knowledge System

---

## Setup Completion Status

✅ **CMOS System**: Fully operational
- SQLite database initialized and healthy
- All CLI tools functional
- Documentation complete

✅ **Project Structure**: Properly configured
- `.gitignore` created with CMOS exclusions
- `docs/` directory established
- Both `agents.md` files in place (project + CMOS)
- Dependencies verified (Python 3.11.9, Node v24.6.0)

✅ **Foundational Assets**: Strong research base
- Combined system architecture documented
- 4 research reports (DRS.0.1-0.04)
- 3 protocol files in `src/protocols/`

⏸️ **Backlog**: Empty (ready for sprint planning after architecture review)

---

## 🎯 THE BIG PICTURE: Autonomous Knowledge System

**Source**: `cmos/foundational-docs/Autonomous Knowledge System – Combined Technical Architecture.md`

PEDR is **one component** of a three-service autonomous knowledge system:

```
┌─────────────┐
│ DeepSearch  │ ← The Researcher (autonomous agent, web search)
└──────┬──────┘
       │ writes structured data
       ↓
┌─────────────┐
│  Tracelab   │ ← The Library (PostgreSQL + Qdrant, validation)
└──────┬──────┘
       │ indexes data
       ↓
┌─────────────┐
│    PEDR     │ ← The Catalog (6-layer search engine) ← YOU ARE HERE
└─────────────┘
```

### The Virtuous Knowledge Loop
1. **DeepSearch** queries PEDR: "Does this research already exist?"
2. If not, **DeepSearch** researches the web, generates structured JSON
3. **Tracelab** validates and stores the research (PostgreSQL + Qdrant)
4. **PEDR** indexes Tracelab's data into its 6-layer catalog
5. Next time, **DeepSearch** finds existing work via PEDR → Loop complete!

---

## PEDR's Role in the System

### Core Vision (Updated)
**PEDR is the "read engine"** for the autonomous knowledge system. It provides sophisticated, multi-layer hybrid search over research artifacts stored in Tracelab.

### Key Components

#### 1. Six-Layer Search Architecture
1. **Lexical Layer** - Keyword/facet search (Typesense or SQLite FTS5)
2. **Semantic Layer** - Vector search (hnswsqlite)
3. **Syntactic Layer** - Element type filtering
4. **Pragmatic Layer** - Intent classification (Create/Read/Update/Delete/Execute)
5. **Governance Layer** - PII/impact/visibility filtering
6. **Relational Layer** - Graph traversal (NetworkX/Memgraph)

#### 2. Core Services (PEDR-Specific)
- **FastAPI Gateway** - Query orchestration, parallel layer execution
- **Protocol Catalog** - SQLite-based normalized search index
- **Query DSL** - Natural language → layer-specific query plans
- **Fusion Engine** - Reciprocal Rank Fusion (RRF) + weighted ranking
- **Protocol Intelligence Engine** - DBSCAN clustering, gap detection
- **Ingestion Service** - **NEW**: Reads from Tracelab PostgreSQL, not YAML files

#### 3. Technology Stack
- **Languages**: Python 3.11+ (services), TypeScript/Node (optional tooling)
- **Storage**: SQLite (local catalog), hnswsqlite (vectors), NetworkX/Memgraph (graph)
- **Frameworks**: FastAPI, LangChain, LlamaIndex
- **Search**: Typesense (preferred) or SQLite FTS5
- **Embeddings**: Local model (sentence-transformers)
- **Data Source**: **Tracelab PostgreSQL** (projects, documents, insights tables)

#### 4. Key Design Decisions
- **Service-oriented**: PEDR is one service in a three-service system
- **Read/Index from Tracelab**: Scheduled or webhook-based ingestion from PostgreSQL
- **Governance-aware**: All queries respect PII/impact/visibility constraints
- **Hybrid search**: Parallel execution across 6 layers, fused results
- **Dual-client model**: Serves both humans (UI) and DeepSearch agent (API)
- **Sub-500ms SLO**: Target p95 latency for hybrid queries

---

## Architecture Review Discussion Topics

### 1. Integration with Tracelab (Critical!)

**Questions to Consider**:
- **Ingestion Flow**: Scheduled (hourly?) vs webhook-triggered indexing?
- **Schema Mapping**: How do Tracelab's `projects`, `documents`, `insights` tables map to PEDR's `protocol_catalog`?
- **Connection**: Direct PostgreSQL connection or via Tracelab API?
- **Incremental Updates**: Do we re-index everything or track deltas?
- **Tracelab Schema**: Do we need to review Tracelab's PostgreSQL schema first?

### 2. Integration with DeepSearch Agent

**Questions to Consider**:
- **Query Format**: What does DeepSearch expect from `POST /api/v1/search`?
- **Response Format**: URNs only? Full metadata? Relevance scores?
- **Performance**: Agent queries need to be fast (<100ms?) to avoid blocking research
- **Authentication**: How does DeepSearch authenticate with PEDR?

### 3. Technology Stack for the New Context

**Questions to Consider**:
- **Typesense vs SQLite FTS5**: Still valid choice for indexing Tracelab data?
- **hnswsqlite**: Appropriate for research document embeddings?
- **Graph Layer**: Do research artifacts have dependency relationships to model?
- **Protocol Files in `src/`**: Are these still relevant, or are they for DeepSearch/Tracelab?

### 4. Data Model & Schema Updates

**Questions to Consider**:
- **protocol_catalog**: Does this schema fit research artifacts (missions, documents, insights)?
- **URN Format**: What do PEDR URNs look like? `urn:research:mission-001`?
- **Metadata**: What fields from Tracelab do we need to index?
- **Relationships**: How do we model document→mission, insight→document relationships?

### 5. Implementation Priority & MVP

**Questions to Consider**:
- **MVP Definition**: Can we start with just 2-3 layers (Lexical + Semantic + Governance)?
- **Sprint 1 Options**:
  - Option A: Build ingestion from Tracelab PostgreSQL
  - Option B: Build basic search API (mocked data)
  - Option C: Build one layer end-to-end (e.g., Lexical)
- **Dependencies**: Do we need Tracelab running first, or can we mock its schema?
- **Testing**: Can we use sample Tracelab exports for development?

### 6. Deployment & Service Communication

**Questions to Consider**:
- **Local Development**: All three services running locally during dev?
- **Service Discovery**: How do services find each other? (hardcoded ports? env vars?)
- **Containerization**: Docker Compose for the full stack?
- **Environment Separation**: Separate DBs for PEDR catalog vs Tracelab repository?

### 7. Protocol Files & Their Role

**Questions to Consider**:
- The three protocol files in `src/protocols/` - are these:
  - A) For PEDR's internal query/metadata model?
  - B) For DeepSearch's output format?
  - C) Legacy from standalone architecture?
- Do we need them at all in the integrated system?

### 8. Testing & Validation Strategy

**Questions to Consider**:
- **Integration Testing**: How do we test PEDR + Tracelab interaction without full DeepSearch?
- **Search Quality**: How do we validate relevance/ranking without real user queries?
- **Performance**: Latency targets when indexing 1k, 10k, 100k documents?
- **Mock Data**: Do we need to create sample Tracelab database exports?

---

## Research Foundation

### DRS.0.1: 6-Layer Search Architecture
Foundation for multi-dimensional protocol search, theoretical framework

### DRS.0.02: Implementation Blueprint
Detailed technical specifications for building the search engine

### DRS.0.03: Protocol Intelligence Engine
Knowledge-gap detection using DBSCAN + hierarchical clustering

### DRS.0.04: RAG Integration
LangChain and LlamaIndex adapter patterns for protocol-enhanced RAG

---

## Critical Dependencies & Assumptions

**Must Clarify Before Sprint Planning**:

1. **Tracelab Schema**: Need the actual PostgreSQL schema (tables, columns, relationships)
2. **Tracelab Status**: Is it already built? In progress? Do we need it first?
3. **DeepSearch Integration**: What's its current state? Can we get API specs?
4. **Protocol Files**: Understand their actual role in the integrated system
5. **Development Order**: Build PEDR first (with mocks), or wait for Tracelab?

---

## Next Steps After Review

### Phase 1: Architecture Alignment
1. **Review Tracelab Schema** - Understand source data structure
2. **Map Data Models** - Tracelab tables → PEDR catalog schema
3. **Define Integration Points** - APIs, connection patterns, auth
4. **Clarify Protocol Files** - Determine if/how we use `src/protocols/`

### Phase 2: Sprint Planning
1. **Define MVP Scope** - Which layers? Which features?
2. **Choose Development Strategy**:
   - Option A: Mock Tracelab, build PEDR independently
   - Option B: Wait for Tracelab, integrate from day 1
   - Option C: Build both in parallel with shared contracts
3. **Create Mission Backlog** - Break work into CMOS missions
4. **Set Success Criteria** - How do we know Sprint 1 is done?

### Phase 3: Implementation
1. **Sprint 1 Kickoff** - Start first build session
2. **Iterate on Integration** - Adjust as we learn
3. **Validate End-to-End** - Test full DeepSearch → Tracelab → PEDR flow

---

## Notes Section

*Use this space during the review discussion to capture decisions, changes, and action items*

### Key Insights from Combined Architecture
- PEDR is NOT standalone - it's the "read engine" for a three-service system
- Data source changed from YAML manifests to Tracelab PostgreSQL
- Dual clients: Human users AND DeepSearch agent
- Virtuous loop: Agent populates Tracelab → PEDR indexes → Agent queries before researching

### Decisions Made
- (To be filled during discussion)

### Architecture Changes from Original PEDR Design
- **Ingestion Source**: YAML files → Tracelab PostgreSQL
- **Deployment Model**: Standalone → Service in ecosystem
- **Client Model**: Human-only → Human + Agent
- **Data Flow**: Manual ingestion → Scheduled/webhook indexing

### Questions Resolved
- (To be filled during discussion)

### Open Questions
- Tracelab schema and availability?
- DeepSearch API specifications?
- Protocol files - still needed?
- Development order strategy?

---

**Review Status**: 🟡 Pending Discussion  
**Next Session**: Architecture Alignment Discussion (Critical Dependencies)  
**Blocking Questions**: Tracelab schema, DeepSearch status, protocol file role

