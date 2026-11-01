# Protocol System Integration Plan (Hybrid Approach)

**Date**: 2025-11-16  
**Approach**: Hybrid - Use proven components, skip overkill  
**Timeline**: 3-4 weeks (2 sprints)

---

## Executive Summary

**PEDR is THE intelligent search engine** for the autonomous knowledge system—the only search interface for both humans and agents. It replaces simple vector RAG with protocol-enhanced multi-dimensional search.

The metrics team delivered a production-ready Protocol Suite. We're taking a **hybrid approach**: use the proven, high-value components (Semantic + Relational protocols) and skip the overkill (Temporal analytics, Pragmatic automation).

**Key Decision**: PEDR is not just a "does this exist" checker—it's the primary search layer that makes research findable and usable through quality-aware, governance-safe, relationship-rich search.

**What We're Using**:
- ✅ **Semantic Protocol** - Quality-aware manifest creation, governance scoring, intent classification
- ✅ **Relational Protocol** - Graph relationships, dependency analysis

**What We're Skipping (for MVP)**:
- ❌ Temporal Protocol - 10 time-series metrics (overkill for search)
- ❌ Pragmatic Protocol - Automated directives (not needed yet)
- ❌ Protocol Orchestrator - Meta-protocol complexity (unnecessary)

**Timeline**: 3-4 weeks instead of 9 weeks

---

## 🎯 What We're Using

### Semantic Protocol (High Value)
**Purpose**: Quality-aware manifest creation with governance scoring

**What It Gives Us**:
- ✅ Auto-calculate quality scores from Tracelab quality gates
- ✅ Intent classification (Create/Read/Update/Delete/Execute)
- ✅ Criticality scoring (business impact + PII + visibility)
- ✅ Confidence scoring (Bayesian approach based on completeness)
- ✅ Governance metadata (PII handling, impact levels)

**Why We're Using It**: Proven, tested code that gives us quality-aware ranking for free

### Relational Protocol (High Value)
**Purpose**: Graph relationship analysis

**What It Gives Us**:
- ✅ Build relationship graph (mission → document → insight → chunk)
- ✅ Graph traversal (find related research)
- ✅ Dependency analysis (what evidence supports what)
- ✅ Architectural metrics (if needed later)

**Why We're Using It**: Enables "show me everything related to this mission"

### What We're Building Fresh
**Simple 2-Layer Search**:
1. **Lexical**: PostgreSQL full-text search on missions/documents/insights
2. **Semantic**: Vector similarity using embeddings (OpenAI or sentence-transformers)

**Simple Fusion**: Merge keyword + semantic results, boost by quality scores from Semantic Protocol

### What We're Skipping (Can Add Later)
- ❌ **Temporal Protocol**: 10 time-series metrics - Overkill for search MVP
- ❌ **Pragmatic Protocol**: Automated directives - Not needed yet
- ❌ **Syntactic Protocol**: Type validation - Research artifacts don't need strict typing
- ❌ **Protocol Orchestrator**: Meta-protocol - Unnecessary complexity

---

## 🔄 Integration Architecture

### Current State

```
┌──────────────┐         ┌────────────────┐
│  Tracelab    │────────▶│     PEDR       │
│  PostgreSQL  │         │  (Unbuilt)     │
│              │         │                │
│  - missions  │         │  - Need to     │
│  - documents │         │    implement   │
│  - insights  │         │    6 layers    │
│  - chunks    │         │                │
└──────────────┘         └────────────────┘
```

### Target State

```
┌──────────────┐         ┌────────────────────────────────┐
│  Tracelab    │────────▶│  PEDR Integration Layer        │
│  PostgreSQL  │  Read   │  (New: Map Tracelab → Protocol)│
│              │         │                                │
│  - missions  │         │  - Mission → Semantic Manifest │
│  - documents │         │  - Document → Semantic Manifest│
│  - insights  │         │  - Insight → Semantic Manifest │
│  - chunks    │         │  - Build Relational Graph      │
└──────────────┘         └──────────────┬─────────────────┘
                                         │
                                         ▼
                         ┌───────────────────────────────┐
                         │  Protocol Suite               │
                         │  (Production System)          │
                         │                               │
                         │  ┌──────────────────────────┐ │
                         │  │  Protocol Orchestrator   │ │
                         │  └─────────┬────────────────┘ │
                         │            │                  │
                         │  ┌─────────▼────────────┐    │
                         │  │  5 Core Protocols    │    │
                         │  │  - Semantic          │    │
                         │  │  - Syntactic         │    │
                         │  │  - Temporal          │    │
                         │  │  - Relational        │    │
                         │  │  - Pragmatic         │    │
                         │  └──────────────────────┘    │
                         │                               │
                         │  20+ Production Metrics       │
                         │  6-Layer Search Engine        │
                         └────────────┬──────────────────┘
                                      │
                                      ▼
                         ┌────────────────────────────┐
                         │  PEDR Search API           │
                         │  POST /api/v1/search       │
                         │                            │
                         │  Returns: Ranked URNs      │
                         │  with protocol metadata    │
                         └────────────────────────────┘
```

---

## 📋 Integration Strategy

### Phase 1: Tracelab → Protocol Mapping (Sprint 1)

**Goal**: Transform Tracelab entities into Protocol Suite manifests

**Implementation**:

#### 1.1 Mission → Semantic Manifest

```javascript
// PEDR Integration Layer
class TracelabProtocolAdapter {
  constructor(tracelab, orchestrator) {
    this.tracelab = tracelab;  // Tracelab PostgreSQL client
    this.orchestrator = orchestrator;  // Protocol Orchestrator instance
  }
  
  async mapMissionToManifest(mission) {
    // Extract from Tracelab mission_data JSON
    const missionData = mission.mission_data;
    
    // Create semantic manifest using Protocol Suite
    const manifest = this.orchestrator.cores.semantic.createManifest({
      id: missionData.mission_id,
      urn: `urn:research:mission:${missionData.mission_id}`,
      
      element: {
        type: 'research.mission',
        role: 'knowledge_artifact',
        intent: 'Read'  // Missions are research outputs (read-focused)
      },
      
      semantics: {
        purpose: missionData.research_statement.objective,
        description: missionData.title,
        tags: missionData.tags || [],
        summary: missionData.summary
      },
      
      governance: {
        piiHandling: this.detectPII(missionData.synthesis),
        businessImpact: this.calculateImpactFromQualityGates(mission.quality_gates),
        userVisibility: mission.status === 'complete' ? 1.0 : 0.5
      },
      
      context: {
        domain: 'research',
        project_id: mission.project_id,
        created_at: mission.created_at,
        updated_at: mission.updated_at,
        status: mission.status,
        completion_percentage: mission.completion_percentage
      },
      
      // Protocol bindings for relational layer
      relationships: {
        belongs_to: [`urn:research:project:${mission.project_id}`],
        references: missionData.evidence.map(e => 
          e.chunk_id ? `urn:research:chunk:${e.chunk_id}` : null
        ).filter(Boolean)
      },
      
      // Store full mission data for retrieval
      metadata: {
        tracelab_id: mission.id,
        research_statement: missionData.research_statement,
        key_questions: missionData.key_questions,
        synthesis: missionData.synthesis,
        quality_gates: mission.quality_gates
      }
    });
    
    return manifest;
  }
  
  async mapDocumentToManifest(document) {
    return this.orchestrator.cores.semantic.createManifest({
      id: document.id,
      urn: `urn:research:document:${document.id}`,
      
      element: {
        type: `research.document.${document.file_type || 'generic'}`,
        role: 'source_material',
        intent: 'Read'
      },
      
      semantics: {
        purpose: `Research document: ${document.name}`,
        description: document.content?.substring(0, 500) || '',
        tags: [document.source_type, document.file_type].filter(Boolean)
      },
      
      governance: {
        piiHandling: this.detectPII(document.content),
        businessImpact: 5,  // Default medium impact
        userVisibility: document.processed && document.embedded ? 1.0 : 0.5
      },
      
      context: {
        domain: 'research',
        project_id: document.project_id,
        file_type: document.file_type,
        source_type: document.source_type,
        uploaded_at: document.uploaded_at
      },
      
      relationships: {
        belongs_to: [`urn:research:project:${document.project_id}`],
        contains: await this.getDocumentChunkURNs(document.id)
      },
      
      metadata: {
        tracelab_id: document.id,
        file_path: document.file_path,
        file_size: document.file_size,
        chunk_count: await this.getChunkCount(document.id)
      }
    });
  }
  
  async mapInsightToManifest(insight) {
    return this.orchestrator.cores.semantic.createManifest({
      id: insight.id,
      urn: `urn:research:insight:${insight.id}`,
      
      element: {
        type: `research.insight.${insight.insight_type || 'finding'}`,
        role: 'derived_knowledge',
        intent: insight.insight_type === 'recommendation' ? 'Execute' : 'Read'
      },
      
      semantics: {
        purpose: insight.title,
        description: insight.content,
        tags: [insight.insight_type, insight.created_by].filter(Boolean)
      },
      
      governance: {
        piiHandling: this.detectPII(insight.content),
        businessImpact: insight.validated ? 7 : 5,
        userVisibility: insight.validated ? 1.0 : 0.7
      },
      
      context: {
        domain: 'research',
        project_id: insight.project_id,
        insight_type: insight.insight_type,
        created_by: insight.created_by,
        validated: insight.validated,
        validation_date: insight.validation_date
      },
      
      relationships: {
        belongs_to: [`urn:research:project:${insight.project_id}`],
        derived_from: await this.getInsightSourceChunks(insight.id)
      },
      
      metadata: {
        tracelab_id: insight.id
      }
    });
  }
}
```

#### 1.2 Build Relational Graph

```javascript
class RelationalGraphBuilder {
  constructor(orchestrator) {
    this.relational = orchestrator.cores.relational;
  }
  
  async buildFromTracelab(manifests) {
    // Extract all URNs and relationships
    const nodes = new Map();
    const edges = [];
    
    for (const manifest of manifests) {
      nodes.set(manifest.urn, {
        type: manifest.element.type,
        criticality: manifest.element.criticality || 0.5
      });
      
      // Process relationships
      if (manifest.relationships?.belongs_to) {
        for (const target of manifest.relationships.belongs_to) {
          edges.push({
            source: manifest.urn,
            target,
            relationship: 'belongs_to',
            weight: 1.0
          });
        }
      }
      
      if (manifest.relationships?.references) {
        for (const target of manifest.relationships.references) {
          edges.push({
            source: manifest.urn,
            target,
            relationship: 'references',
            weight: 0.8
          });
        }
      }
      
      if (manifest.relationships?.derived_from) {
        for (const target of manifest.relationships.derived_from) {
          edges.push({
            source: manifest.urn,
            target,
            relationship: 'derived_from',
            weight: 0.9
          });
        }
      }
    }
    
    // Create relational manifest
    const graph = this.relational.createRelationalGraph({
      nodes: Array.from(nodes.entries()).map(([urn, data]) => ({
        id: urn,
        ...data
      })),
      edges
    });
    
    // Calculate relational metrics
    const metrics = this.relational.evaluateArchitecturalHealth(graph);
    
    return { graph, metrics };
  }
}
```

---

### Phase 2: Protocol Search Integration (Sprint 2)

**Goal**: Implement 6-layer search using Protocol Suite

#### 2.1 Search Orchestration

```javascript
class PEDRSearchEngine {
  constructor(orchestrator, manifests, graph) {
    this.orchestrator = orchestrator;
    this.manifests = manifests;  // All semantic manifests (indexed)
    this.graph = graph;  // Relational graph
  }
  
  async search(query, options = {}) {
    const results = {
      lexical: [],
      semantic: [],
      syntactic: [],
      pragmatic: [],
      governance: [],
      relational: []
    };
    
    // Layer 1: Lexical - Keyword matching
    results.lexical = await this.lexicalSearch(query);
    
    // Layer 2: Semantic - Intent and purpose matching
    results.semantic = await this.semanticSearch(query);
    
    // Layer 3: Syntactic - Type filtering
    if (options.element_type) {
      results.syntactic = this.manifests.filter(m => 
        m.element.type.includes(options.element_type)
      );
    }
    
    // Layer 4: Pragmatic - Intent filtering
    if (options.intent) {
      results.pragmatic = this.manifests.filter(m => 
        m.element.intent === options.intent
      );
    }
    
    // Layer 5: Governance - PII and impact filtering
    results.governance = this.manifests.filter(m => {
      if (options.allow_pii === false && m.governance.piiHandling) return false;
      if (options.min_impact && m.governance.businessImpact < options.min_impact) return false;
      return true;
    });
    
    // Layer 6: Relational - Graph expansion
    results.relational = await this.relationalExpansion(query, options);
    
    // Fuse results using Reciprocal Rank Fusion
    const fused = this.fuseResults(results, options);
    
    return fused;
  }
  
  async lexicalSearch(query) {
    // Simple keyword matching on purpose, description, tags
    const keywords = query.toLowerCase().split(/\s+/);
    
    return this.manifests.filter(m => {
      const searchText = [
        m.semantics.purpose,
        m.semantics.description,
        ...(m.semantics.tags || [])
      ].join(' ').toLowerCase();
      
      return keywords.some(kw => searchText.includes(kw));
    }).map(m => ({
      urn: m.urn,
      score: this.calculateKeywordScore(m, keywords),
      manifest: m
    }));
  }
  
  async semanticSearch(query) {
    // Use semantic protocol's vector similarity
    const queryVector = this.orchestrator.cores.semantic._generateSemanticVector({
      semantics: { purpose: query }
    });
    
    return this.manifests.map(m => ({
      urn: m.urn,
      score: this.cosineSimilarity(queryVector, m.semantics.features.vector),
      manifest: m
    })).filter(r => r.score > 0.3);  // Threshold
  }
  
  async relationalExpansion(query, options) {
    // Find initial matches, then expand via graph
    const initialMatches = await this.lexicalSearch(query);
    
    if (options.expand_graph && initialMatches.length > 0) {
      const expanded = new Set();
      
      for (const match of initialMatches.slice(0, 5)) {  // Top 5
        const neighbors = this.orchestrator.cores.relational.getNeighbors(
          this.graph,
          match.urn,
          options.max_depth || 2
        );
        
        neighbors.forEach(n => expanded.add(n));
      }
      
      return Array.from(expanded).map(urn => ({
        urn,
        score: 0.7,  // Lower score for expanded results
        manifest: this.manifests.find(m => m.urn === urn)
      }));
    }
    
    return [];
  }
  
  fuseResults(results, options) {
    // Reciprocal Rank Fusion
    const urnScores = new Map();
    const weights = options.layer_weights || {
      lexical: 0.2,
      semantic: 0.3,
      syntactic: 0.1,
      pragmatic: 0.1,
      governance: 0.2,
      relational: 0.1
    };
    
    for (const [layer, items] of Object.entries(results)) {
      const weight = weights[layer] || 0.1;
      
      items.forEach((item, rank) => {
        const rrfScore = weight / (rank + 60);  // RRF formula
        const current = urnScores.get(item.urn) || { score: 0, manifest: item.manifest };
        current.score += rrfScore;
        urnScores.set(item.urn, current);
      });
    }
    
    // Sort by fused score
    const ranked = Array.from(urnScores.entries())
      .map(([urn, data]) => ({ urn, score: data.score, manifest: data.manifest }))
      .sort((a, b) => b.score - a.score);
    
    return {
      results: ranked.slice(0, options.top_k || 20),
      total: ranked.length,
      layers: Object.fromEntries(
        Object.entries(results).map(([layer, items]) => [layer, items.length])
      )
    };
  }
}
```

---

### Phase 3: Temporal Monitoring (Sprint 3)

**Goal**: Apply temporal metrics to research workflows

```javascript
class ResearchTemporalMonitor {
  constructor(orchestrator) {
    this.temporal = orchestrator.cores.temporal;
  }
  
  async createMissionMonitoring(mission) {
    // Track mission completion metrics
    return this.temporal.createTemporalManifest({
      scope: 'mission',
      bindings: { 
        semantic_id: mission.urn,
        mission_id: mission.metadata.mission_id
      },
      expectations: [
        {
          metric: 'temporal.metric.latency.v1',
          window: '1d',
          target: { max: 86400000 }  // 1 day max completion time
        },
        {
          metric: 'research.quality.qpf',  // Custom metric
          window: '7d',
          target: { min: 0.7 }  // Quality gate fairness
        }
      ]
    });
  }
  
  async evaluateResearchVelocity(project_id, timeWindow = '30d') {
    // Get all missions for project
    const missions = await this.getMissionsForProject(project_id);
    
    // Extract completion times
    const observations = missions.map(m => ({
      timestamp: new Date(m.metadata.updated_at).getTime(),
      duration: this.calculateMissionDuration(m),
      success: m.context.status === 'complete'
    }));
    
    // Calculate Directional Momentum
    const durations = observations.map(o => o.duration);
    const dm = this.temporal.evaluateMetric('temporal.metric.dm.v1', durations);
    
    // Calculate Error Rate (incomplete missions)
    const errorRate = this.temporal.evaluateMetric(
      'temporal.metric.error_rate.v1',
      observations
    );
    
    return {
      directional_momentum: dm.value,  // Trend: improving or declining?
      error_rate: errorRate.value,  // Percentage of incomplete
      recommendation: dm.value < 0.3 ? 'Research velocity declining' : 'Healthy'
    };
  }
}
```

---

## 📦 Revised Implementation Roadmap (3-4 Weeks)

### Sprint 1: Core Search + Protocol Integration (2 weeks)
**Goal**: Working search with quality-aware ranking

**Week 1: Foundation**
- [ ] Set up minimal Protocol Suite
  - Import ONLY semantic-protocol and relational-core
  - Skip orchestrator, temporal, pragmatic
  - Verify core protocols work
- [ ] Build Tracelab adapter (simplified)
  - Connect to Tracelab PostgreSQL
  - Read missions, documents, insights
  - Transform to semantic manifests (use Semantic Protocol)
  - Extract quality scores from quality_gates
- [ ] Set up basic storage
  - SQLite for manifest metadata
  - PostgreSQL for full-text search (use Tracelab's tsvector)
  - pgvector or Qdrant for embeddings

**Week 2: Search Implementation**
- [ ] Implement 2-layer search
  - Layer 1: Keyword search (PostgreSQL FTS on Tracelab data)
  - Layer 2: Semantic search (vector similarity)
- [ ] Add quality boosting
  - Use Semantic Protocol quality scores in ranking
  - Boost complete missions over drafts
  - Filter by governance (PII handling, business impact)
- [ ] Build FastAPI endpoint
  - `POST /api/v1/search`
  - Basic query parsing
  - JSON response with URNs + metadata
- [ ] Basic testing
  - Test queries: "passwordless auth", "user research", etc.
  - Verify ranking makes sense
  - Check latency (<500ms)

**Deliverable**: Working search API that returns quality-ranked results

---

### Sprint 2: Graph + DeepSearch Integration (1-2 weeks)
**Goal**: Add relationship context and complete DeepSearch integration

**Week 3: Relational Layer**
- [ ] Build relationship graph (use Relational Protocol)
  - Extract relationships from manifests
  - Build graph: mission → document → insight → chunk
  - Store in NetworkX or simple adjacency list
- [ ] Add graph expansion to search
  - "Find mission X" → also return related documents/insights
  - Optional graph traversal (depth 1-2)
- [ ] Implement GET endpoints
  - `GET /api/v1/missions/{id}` - Full mission with relationships
  - `GET /api/v1/search/related/{urn}` - Find related entities

**Week 4: Integration + Polish**
- [ ] DeepSearch coordination
  - Finalize request/response format
  - Add authentication (JWT or API key)
  - Performance testing (<100ms for agent queries)
- [ ] Ingestion automation
  - Scheduled polling from Tracelab (every 15 min)
  - Track last_sync timestamp
  - Incremental updates only
- [ ] End-to-end testing
  - DeepSearch → PEDR → return results flow
  - Human search scenarios
  - Edge cases (no results, PII filtering, etc.)
- [ ] Documentation
  - API documentation (OpenAPI spec)
  - Integration guide for DeepSearch team
  - Deployment instructions

**Deliverable**: Production-ready PEDR integrated with DeepSearch and Tracelab

---

## What We Can Add Later (Post-MVP)

### Phase 2 Enhancements (if needed)
- [ ] **Temporal Analytics** - Research velocity tracking
  - Add basic completion rate tracking
  - Mission duration analysis
  - Don't need all 10 temporal metrics
- [ ] **Advanced Graph Queries** - Deeper relationship analysis
  - Centrality metrics (which missions are most referenced?)
  - Blast radius (if we delete mission X, what breaks?)
- [ ] **Pragmatic Automation** - Smart recommendations
  - "You might also be interested in..."
  - Knowledge gap detection
  - Research prioritization

### Phase 3 Nice-to-Haves
- [ ] Dashboard with visualizations
- [ ] Full Protocol Orchestrator integration (if we need composition)
- [ ] Advanced temporal metrics (if we need trend analysis)

---

## 🔑 Key Decisions

### 1. Hybrid Approach - Use Best Parts Only
**Decision**: Use Semantic + Relational protocols, skip Temporal/Pragmatic/Orchestrator for MVP  
**Rationale**: Get 80% of value with 20% of complexity. Temporal analytics and automation are overkill for search.  
**Impact**: 3-4 weeks instead of 9 weeks, simpler codebase, faster iteration

### 2. Simple 2-Layer Search + Quality Boosting
**Decision**: Keyword + semantic search, boost results by Semantic Protocol quality scores  
**Rationale**: Covers core use case (DeepSearch needs quality-ranked results), proven to work  
**Impact**: Practical search that meets actual user needs

### 3. Graph for Context, Not Analytics
**Decision**: Use Relational Protocol for "show related research", skip complex graph analytics  
**Rationale**: Users want "what else is related to this mission", not centrality scores  
**Impact**: Useful feature without overthinking it

### 4. Can Add Advanced Features Later
**Decision**: MVP gets job done, add temporal/pragmatic if we see concrete need  
**Rationale**: Don't build features we're not sure we need  
**Impact**: Ship faster, learn from usage, iterate

---

## 🎯 Success Metrics (MVP)

| Metric | Target | Validation |
|--------|--------|------------|
| **Search latency (agent)** | <100ms p95 | DeepSearch query response time - CRITICAL |
| **Search latency (human)** | <500ms p95 | UI query response time |
| **Search relevance** | Top-10 precision >80% | Manual evaluation: "Do complete missions rank higher?" |
| **Quality awareness** | Complete missions rank 2x higher | Semantic Protocol scoring working |
| **Graph context** | Related items returned | Can find documents linked to mission |
| **Ingestion latency** | <15 min | Time from Tracelab update to PEDR availability |
| **API uptime** | >99% | DeepSearch can always query |

### Not Measuring (Yet)
- ❌ Temporal metrics (not implementing)
- ❌ Research velocity (Phase 2)
- ❌ Complex graph analytics (Phase 2)
- ❌ Pragmatic automation metrics (Phase 2)

---

## 📚 Next Steps

1. **Review this plan with team** - Validate approach
2. **Set up Protocol Suite** - Import into PEDR project
3. **Start Sprint 1** - Build Tracelab adapter
4. **Coordinate with DeepSearch** - Share URN format and API specs

---

**Status**: Draft integration plan  
**Next Review**: Team alignment meeting  
**Owner**: PEDR Team

