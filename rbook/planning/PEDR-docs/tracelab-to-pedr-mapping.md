# Tracelab → PEDR Schema Mapping

**Date**: 2025-11-16  
**Purpose**: Define how PEDR indexes Tracelab's PostgreSQL data into its 6-layer search catalog

---

## Data Flow Overview

```
┌─────────────────────────────────────────────────────┐
│ Tracelab PostgreSQL Database                        │
│  - missions (mission_data JSON, quality_gates)      │
│  - projects (metadata)                               │
│  - documents (content, file metadata)                │
│  - document_chunks (auto-generated, with embeddings) │
│  - insights (findings, recommendations)              │
│  - insight_sources (chunk links)                     │
└──────────────────┬──────────────────────────────────┘
                   │ Scheduled/Webhook Ingestion
                   ↓
┌─────────────────────────────────────────────────────┐
│ PEDR Ingestion Service                               │
│  - Reads Tracelab tables                            │
│  - Normalizes to protocol_catalog schema            │
│  - Builds 6-layer indexes                           │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│ PEDR Search Indexes                                  │
│  - protocol_catalog (SQLite)                        │
│  - vector_index (hnswsqlite)                        │
│  - graph_edges (NetworkX/Memgraph)                  │
└─────────────────────────────────────────────────────┘
```

---

## Tracelab Schema Summary

### Core Tables

**missions**
```sql
id: UUID (PK)
project_id: UUID (FK → projects)
mission_data: JSON              # Full MissionProtocol structure
quality_gates: JSON             # Gate validation results
status: VARCHAR                 # draft | in_progress | review | complete
completion_percentage: INTEGER
created_at: TIMESTAMP
updated_at: TIMESTAMP
```

**documents**
```sql
id: UUID (PK)
project_id: UUID (FK → projects)
name: VARCHAR                   # Title
content: TEXT                   # Extracted text
file_type: VARCHAR              # transcript | survey | notes | report | etc
source_type: VARCHAR            # interview | survey | observation | analysis
processed: BOOLEAN
chunked: BOOLEAN
embedded: BOOLEAN
uploaded_at: TIMESTAMP
```

**document_chunks**
```sql
id: UUID (PK)
document_id: UUID (FK → documents)
chunk_index: INTEGER            # 0-based sequence
content: TEXT                   # Chunk text
content_tsv: TSVECTOR          # PostgreSQL full-text search
embedding_id: VARCHAR           # Qdrant vector ID
token_count: INTEGER
prev_chunk_id: UUID (nullable)
next_chunk_id: UUID (nullable)
created_at: TIMESTAMP
```

**insights**
```sql
id: UUID (PK)
project_id: UUID (FK → projects)
title: VARCHAR
content: TEXT                   # The insight text
insight_type: VARCHAR           # finding | contradiction | surprising | recommendation
created_by: VARCHAR             # human | ai | human_validated_ai
validated: BOOLEAN
created_at: TIMESTAMP
updated_at: TIMESTAMP
```

**insight_sources** (junction)
```sql
insight_id: UUID (FK → insights)
chunk_id: UUID (FK → document_chunks)
relevance_score: DECIMAL(3,2)  # 0.00-1.00
```

**projects**
```sql
id: UUID (PK)
name: VARCHAR
description: TEXT
created_at: TIMESTAMP
updated_at: TIMESTAMP
```

---

## PEDR Catalog Schema (Target)

**From original architecture**: `protocol_catalog` table

```sql
urn: TEXT (PK)                  # Unique protocol identifier
manifest: JSON                  # Original manifest payload
purpose: TEXT                   # Flattened semantic summary
description: TEXT               # Human description
context_domain: TEXT            # Domain facet
element_type: TEXT              # Syntactic type
element_intent: TEXT            # Pragmatic intent (Create/Read/Update/Delete/Execute)
governance_pii: BOOLEAN         # PII handling flag
governance_impact: INTEGER      # Business impact (1-10)
bindings: JSON                  # Relationship refs (for graph)
```

---

## Mapping Strategy

### 1. Mission → Protocol Entry

**Source**: Tracelab `missions` table

**Mapping**:
```python
urn = f"urn:research:mission:{mission_data['mission_id']}"
manifest = mission_data  # Full MissionProtocol JSON
purpose = mission_data['research_statement']['objective']
description = mission_data['title']
context_domain = "research"  # or extract from tags
element_type = "mission"
element_intent = "Read"  # Missions are research artifacts (read-focused)
governance_pii = detect_pii_from_synthesis(mission_data)
governance_impact = calculate_impact_from_quality_gates(quality_gates)
bindings = {
    "project_id": project_id,
    "evidence_chunks": [e['chunk_id'] for e in mission_data['evidence']],
    "related_documents": extract_document_refs(mission_data)
}
```

**Vector Content** (for semantic layer):
- Concatenate: title + objective + key_insights + recommendations
- Generate embedding via sentence-transformer

**Graph Edges**:
- `mission → project` (belongs_to)
- `mission → document_chunk` (references, via evidence)
- `mission → mission` (if missions reference each other)

---

### 2. Document → Protocol Entry

**Source**: Tracelab `documents` table

**Mapping**:
```python
urn = f"urn:research:document:{document.id}"
manifest = {
    "id": str(document.id),
    "name": document.name,
    "file_type": document.file_type,
    "source_type": document.source_type,
    "project_id": str(document.project_id),
    "uploaded_at": document.uploaded_at.isoformat()
}
purpose = f"Research document: {document.name}"
description = truncate(document.content, 500)  # First 500 chars
context_domain = "research"
element_type = document.file_type or "document"
element_intent = "Read"
governance_pii = detect_pii_in_content(document.content)
governance_impact = 5  # Default medium impact
bindings = {
    "project_id": str(document.project_id),
    "chunk_count": count_chunks(document.id)
}
```

**Vector Content**:
- Use first 1000 characters of `content` or full content if shorter
- Or: aggregate chunk embeddings (mean pooling)

**Graph Edges**:
- `document → project` (belongs_to)
- `document → document_chunk` (contains)

---

### 3. DocumentChunk → Protocol Entry (Optional)

**Decision Point**: Should we index individual chunks or just documents?

**Option A: Index Chunks** (granular search)
```python
urn = f"urn:research:chunk:{chunk.id}"
purpose = truncate(chunk.content, 200)
description = chunk.content
element_type = "chunk"
element_intent = "Read"
bindings = {
    "document_id": str(chunk.document_id),
    "chunk_index": chunk.chunk_index,
    "prev_chunk": str(chunk.prev_chunk_id) if chunk.prev_chunk_id else None,
    "next_chunk": str(chunk.next_chunk_id) if chunk.next_chunk_id else None
}
```

**Option B: Aggregate at Document Level** (simpler)
- Index only documents and missions
- Use chunk content for vector embeddings but don't create separate URNs
- Reference chunk IDs in mission bindings only

**Recommendation**: Start with Option B (aggregate), add Option A if needed for granularity

---

### 4. Insight → Protocol Entry

**Source**: Tracelab `insights` table

**Mapping**:
```python
urn = f"urn:research:insight:{insight.id}"
manifest = {
    "id": str(insight.id),
    "title": insight.title,
    "insight_type": insight.insight_type,
    "created_by": insight.created_by,
    "validated": insight.validated,
    "project_id": str(insight.project_id)
}
purpose = insight.title
description = insight.content
context_domain = "research"
element_type = insight.insight_type or "insight"
element_intent = "Read" if insight.insight_type == "finding" else "Execute"
governance_pii = detect_pii_in_content(insight.content)
governance_impact = 7 if insight.validated else 5
bindings = {
    "project_id": str(insight.project_id),
    "source_chunks": get_linked_chunks(insight.id)  # via insight_sources
}
```

**Vector Content**:
- title + content

**Graph Edges**:
- `insight → project` (belongs_to)
- `insight → document_chunk` (derived_from, via insight_sources)
- `insight → mission` (if mission references insight)

---

## Layer-Specific Indexing

### Layer 1: Lexical (Typesense/SQLite FTS5)

**Documents to Index**:
- URN
- purpose (indexed)
- description (indexed)
- element_type (facet)
- context_domain (facet)

**Sources**:
- Missions: title, objective, key_insights, recommendations
- Documents: name, content (truncated or full)
- Insights: title, content

---

### Layer 2: Semantic (hnswsqlite)

**Embeddings to Generate**:
- Mission: `title + objective + synthesis.key_insights[]`
- Document: `content` (first 1000 chars or aggregated chunks)
- Insight: `title + content`

**Storage**: `vector_index` table
```sql
urn: TEXT (PK)
embedding: BLOB              # numpy array serialized
updated_at: INTEGER
```

---

### Layer 3: Syntactic (Element Type Filtering)

**Facet**: `element_type`

**Values**:
- `mission` (from missions table)
- `report`, `transcript`, `survey`, `notes` (from documents.file_type)
- `finding`, `contradiction`, `recommendation` (from insights.insight_type)
- `chunk` (if indexing chunks separately)

---

### Layer 4: Pragmatic (Intent Classification)

**Facet**: `element_intent`

**Mapping Logic**:
- Missions: Always "Read" (research outputs)
- Documents: Always "Read" (reference materials)
- Insights:
  - `finding` → "Read"
  - `recommendation` → "Execute"
  - `contradiction` → "Update" (needs resolution)
  - Default → "Read"

**Note**: Unlike standalone PEDR (protocols with CRUD operations), research artifacts are primarily read-focused.

---

### Layer 5: Governance (PII/Impact Filtering)

**Fields**:
- `governance_pii`: BOOLEAN (detect in content)
- `governance_impact`: INTEGER 1-10

**Logic**:
```python
def calculate_governance(entity):
    pii = detect_pii(entity.content)  # Use regex/NER
    
    if entity_type == "mission":
        impact = 8 if quality_gates_all_pass else 6
    elif entity_type == "insight":
        impact = 7 if validated else 5
    else:  # document
        impact = 5  # default
    
    return {"pii": pii, "impact": impact}
```

---

### Layer 6: Relational (Graph Traversal)

**Edges to Create** (`graph_edges` table):

```sql
source_urn: TEXT
target_urn: TEXT
relationship: TEXT  # belongs_to | contains | references | derived_from
```

**Relationships**:
- `mission → project`: `belongs_to`
- `mission → chunk`: `references` (via evidence)
- `document → project`: `belongs_to`
- `document → chunk`: `contains`
- `insight → project`: `belongs_to`
- `insight → chunk`: `derived_from` (via insight_sources)

**Graph Queries**:
- "Find all missions in project X"
- "Find all insights derived from document Y"
- "Find evidence trail for mission Z"

---

## Ingestion Implementation

### Approach: Scheduled Polling

**Frequency**: Every 5-15 minutes (configurable)

**Process**:
1. Connect to Tracelab PostgreSQL (read-only user)
2. Query for new/updated entities since last sync:
   ```sql
   SELECT * FROM missions WHERE updated_at > $last_sync_timestamp
   SELECT * FROM documents WHERE uploaded_at > $last_sync_timestamp
   SELECT * FROM insights WHERE updated_at > $last_sync_timestamp
   ```
3. For each entity:
   - Map to `protocol_catalog` row
   - Generate embedding
   - Create graph edges
4. Bulk insert into PEDR indexes
5. Update `last_sync_timestamp`

**State Tracking**:
```python
# Store in PEDR metadata table
sync_state = {
    "last_sync": "2025-11-16T12:00:00Z",
    "missions_synced": 42,
    "documents_synced": 150,
    "insights_synced": 89
}
```

---

### Alternative: Webhook-Based (Future)

**Tracelab Enhancement**:
- Add webhook configuration: `POST https://pedr-api/webhooks/tracelab`
- Trigger on:
  - Mission created/updated
  - Document processed (after chunking)
  - Insight created/updated

**PEDR Webhook Handler**:
```python
@app.post("/webhooks/tracelab")
async def handle_tracelab_webhook(event: TracelabEvent):
    if event.type == "mission.updated":
        sync_mission(event.data.mission_id)
    elif event.type == "document.processed":
        sync_document(event.data.document_id)
    # etc
```

**Benefit**: Near-real-time indexing (sub-minute latency)

**Decision**: Start with scheduled polling (simpler), add webhooks in Sprint 2-3

---

## Open Design Questions

### 1. URN Format

**Current Proposal**: `urn:research:{entity_type}:{id}`

**Examples**:
- `urn:research:mission:DRM.0.5`
- `urn:research:document:uuid-123`
- `urn:research:insight:uuid-456`

**Question**: Should we namespace by project?
- Option: `urn:research:{project_id}:mission:{mission_id}`
- Pro: Clear project boundaries
- Con: Longer URNs, more complex

### 2. Chunk Indexing

**Should we index chunks separately or aggregate at document level?**

**Option A: Aggregate (Simpler)**
- Index documents only
- Chunk content contributes to document embedding
- Search returns document URN
- User retrieves full document via Tracelab API

**Option B: Granular (More precise)**
- Index each chunk as separate entry
- Search returns chunk URN
- User can fetch specific relevant chunk
- More index entries (100x if avg 100 chunks/doc)

**Recommendation**: Start with Option A, measure precision, add Option B if needed

### 3. Mission Status Filtering

**Should PEDR filter by mission status?**

**Options**:
- Index only `complete` missions (highest quality)
- Index all missions, add `status` facet for filtering
- Index all, but boost `complete` missions in ranking

**Recommendation**: Index all, add status facet, let users filter

### 4. Project Boundaries

**Should PEDR index projects as first-class entities?**

**Option A: Projects are Facets**
- Don't create project URNs
- Use `project_id` in bindings for filtering
- Graph edges: `mission → project`

**Option B: Projects are Searchable**
- Create `urn:research:project:{id}`
- Index project metadata (name, description)
- Search can return project URNs

**Recommendation**: Start with Option A (facet), add Option B if users search for projects

### 5. Quality Gate Reflection

**Should quality gate results influence ranking/governance?**

**Ideas**:
- Missions with all gates passing → higher `governance_impact`
- Failing `traceability` gate → lower ranking
- `contradictions_resolved` status → affects search results

**Proposal**:
```python
governance_impact = base_impact(5)
if all_gates_pass(quality_gates):
    governance_impact += 2  # 7
if specific_gates_critical(quality_gates):
    governance_impact += 1  # 8
```

---

## Implementation Checklist

### Sprint 1: Basic Ingestion
- [ ] Read Tracelab PostgreSQL connection string from env
- [ ] Query missions table, map to protocol_catalog
- [ ] Query documents table, map to protocol_catalog
- [ ] Query insights table, map to protocol_catalog
- [ ] Generate embeddings for semantic layer
- [ ] Implement scheduled polling (every 15 min)

### Sprint 2: Full 6-Layer Indexing
- [ ] Build Typesense/FTS5 index (lexical layer)
- [ ] Build hnswsqlite index (semantic layer)
- [ ] Implement element_type filtering (syntactic layer)
- [ ] Implement intent mapping (pragmatic layer)
- [ ] Implement governance scoring (governance layer)
- [ ] Build NetworkX graph (relational layer)

### Sprint 3: Search & Fusion
- [ ] Implement query orchestrator (fan-out to layers)
- [ ] Implement RRF fusion engine
- [ ] Add governance filtering post-fusion
- [ ] Expose `/api/v1/search` endpoint
- [ ] Test with sample DeepSearch queries

### Sprint 4: Polish & Optimization
- [ ] Add webhook support (optional)
- [ ] Implement incremental updates
- [ ] Add chunk-level indexing (if needed)
- [ ] Performance optimization (<500ms p95)
- [ ] Integration testing with DeepSearch

---

## Next Steps

1. **Review this mapping with team** - Validate assumptions
2. **Get actual Tracelab PostgreSQL schema DDL** - Confirm field names
3. **Define PEDR environment variables**:
   ```bash
   TRACELAB_POSTGRES_URI=postgresql://user:pass@localhost:5432/tracelab
   PEDR_SYNC_INTERVAL=900  # 15 minutes
   PEDR_DATA_ROOT=/path/to/.data
   ```
4. **Create sample queries** - Test typical DeepSearch searches
5. **Define success metrics** - Search precision, recall, latency

---

**Status**: Draft mapping based on Tracelab Q&A document  
**Next Review**: After team validation and DDL confirmation

