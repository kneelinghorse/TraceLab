# PEDR Search Architecture

**Protocol-Enhanced Deep Research (PEDR)** is TraceLab's unified search architecture that combines six specialized search layers (including the optional L6 graph expansion) with Reciprocal Rank Fusion (RRF) to deliver accurate, context-aware results.

## Overview

PEDR replaces traditional single-mode search with a multi-layer approach:

```
Query → [Pre-Analysis] → [Parallel Retrieval] → [Graph Expansion] → [RRF Fusion] → [Post-Processing] → Results
              ↓                    ↓                   ↓               ↓               ↓
         Syntactic +          Lexical +            BFS +           Weighted        Governance +
         Pragmatic            Semantic             Decay           Ranking         Quality Gates
```

**Key Reference**: `app/services/pedr/search_orchestrator.py`
**Graph Layer Reference**: `app/services/pedr/graph_layer.py`

---

## The 6 Layers

Weights listed below are base weights; effective weights are normalized across enabled layers and rescaled when the graph layer is enabled.

### 1. Lexical Layer (Weight: 0.25)

**Purpose**: Keyword matching via PostgreSQL full-text search (FTS).

**How it works**:
- Uses PostgreSQL's `tsvector` and `tsquery` for efficient text matching
- Handles exact phrases, boolean operators, and stemming
- Fast baseline retrieval (<50ms typical)

**When it shines**:
- Exact term matches (product names, codes, identifiers)
- Boolean queries ("user AND authentication NOT OAuth")
- Low-latency requirements

**Implementation**: `app/services/hybrid_search.py` → `_keyword_search()`

---

### 2. Semantic Layer (Weight: 0.35)

**Purpose**: Vector similarity search via Qdrant.

**How it works**:
- Embeds queries using sentence-transformers
- Searches Qdrant collection with HNSW indexing
- Returns chunks ranked by cosine similarity

**Key configuration**:
```python
hnsw_ef: int = 64  # Search accuracy vs speed trade-off
ef_search: int = 64  # Default tuned for 100% recall at <50ms
```

**When it shines**:
- Semantic similarity ("user login problems" finds "authentication issues")
- Concept search across paraphrased content
- Research questions requiring understanding, not just keywords

**Implementation**: `app/services/retrieval_service.py`

---

### 3. Syntactic Layer (Weight: 0.15)

**Purpose**: Detect and boost results matching specific element types.

**Element types detected**:
- `quote` - Direct quotations from sources
- `statistic` - Numerical data, metrics, percentages
- `recommendation` - Actionable suggestions
- `finding` - Research conclusions
- `method` - Methodology descriptions
- `observation` - Observational notes

**How it works**:
1. **Auto-detection**: Analyzes query to infer expected type
2. **Boosting**: Applies score multiplier to matching element types
3. **Filtering**: Can restrict results to specific types

```python
# Example: Query "what percentage of users..." triggers statistic detection
SyntacticFilters(
    detected_type=ElementType.STATISTIC,
    detection_confidence=0.85,
    type_boost=1.5
)
```

**Implementation**: `app/services/pedr/syntactic.py`

---

### 4. Pragmatic Layer (Weight: 0.10)

**Purpose**: Classify query intent and adjust retrieval strategy.

**Intent classifications**:
- `factual` - Seeking specific facts or data
- `exploratory` - Open-ended research
- `comparative` - Comparing options or approaches
- `procedural` - How-to guidance
- `evaluative` - Assessment or judgment

**How it works**:
1. Analyzes query structure and keywords
2. Classifies intent with confidence score
3. Applies intent-specific boosts to relevant results

```python
PragmaticFilters(
    intent=QueryIntent.COMPARATIVE,
    confidence=0.78,
    boost_factor=1.2
)
```

**Implementation**: `app/services/pedr/pragmatic.py`

---

### 5. Governance Layer (Weight: 0.15)

**Purpose**: Quality gates and PII handling for compliance.

**Quality gates**:
- `quality_gates_passed`: Count of passing quality checkpoints
- `quality_status`: Overall status (pending/pass/fail)
- `quality_score`: Composite quality score (0.0-1.0)

**PII handling**:
- `allow_pii`: Toggle inclusion of PII-flagged chunks
- Redaction service integration for sensitive content

**Filters**:
```python
QualityFilters(
    min_quality_gates=3,     # Require 3+ passing gates
    statuses=("pass",),      # Only fully validated content
    allow_pii=False          # Exclude PII-flagged chunks
)
```

**Implementation**: `app/services/pedr/quality_scoring.py`

---

### 6. Graph Layer (L6) (Weight: 0.08, optional)

**Purpose**: Expand retrieval results through the relationship graph to surface related entities beyond direct lexical/semantic matches.

**Graph traversal flow**:
1. **Seed selection**: Interleave top lexical + semantic results; use the top `graph_top_k_seeds` as seeds.
2. **URN resolution**: Prefer explicit `urn` values; fall back to `document_id` + `chunk_index` or `chunk_id`.
3. **BFS expansion**: Traverse `graph_edges` breadth-first up to `graph_depth`, optionally filtering by `graph_edge_types`.
4. **Decay scoring**: Assign `score = seed_score * (graph_decay ** depth)` per hop; keep best score per candidate.
5. **Chunk resolution**: Resolve chunk URNs to `chunk_id` so RRF can rank them; preserve `urn` for provenance.

**Configuration (API)**:
- `enable_graph` (bool) - Toggle graph expansion
- `graph_depth` (1-5) - Max BFS depth
- `graph_decay` (0.1-1.0) - Score decay per hop
- `graph_edge_types` (list or null) - Edge type filter
- `graph_weight` (0.0-0.5) - Graph layer weight in RRF

**Internal defaults**:
- `graph_top_k_seeds`: 5 (top retrieval seeds)
- `max_candidates`: 100 (cap on expanded candidates)

**Implementation**: `app/services/pedr/graph_layer.py`

---

## RRF Fusion

Reciprocal Rank Fusion combines results from multiple retrieval systems into a unified ranking.

### Formula

```
RRF_score(d) = Σ (weight_i / (k + rank_i(d)))
```

Where:
- `d` = document/chunk
- `weight_i` = layer weight (default weights sum to 1.0)
- `rank_i(d)` = rank of d in layer i's results
- `k` = smoothing constant (default: 60)

### Default Layer Weights

```python
BASE_LAYER_WEIGHTS = {
    "lexical": 0.25,
    "semantic": 0.35,
    "syntactic": 0.15,
    "pragmatic": 0.10,
    "governance": 0.15,
}
DEFAULT_GRAPH_WEIGHT = 0.08

# When graph is enabled, base weights are scaled by (1 - graph_weight)
# and then normalized across enabled layers.
DEFAULT_LAYER_WEIGHTS = {
    "lexical": 0.23,
    "semantic": 0.322,
    "syntactic": 0.138,
    "pragmatic": 0.092,
    "governance": 0.138,
    "graph": 0.08,
}
```

If the graph layer is disabled, its weight is set to 0 and the remaining enabled layers are normalized to sum to 1.

### Why RRF?

1. **Robust to outliers**: Single-layer anomalies don't dominate
2. **No score normalization needed**: Works on ranks, not raw scores
3. **Tunable**: Weights can be adjusted per use case

**Implementation**: `app/services/pedr/fusion.py`

---

## Search Modes

### Full Mode (Default)

Standard PEDR search with complete analysis. The graph layer is opt-in.

```
POST /api/v1/pedr/search
{
  "query": "user authentication patterns",
  "top_k": 10,
  "rerank_mode": "full"
}
```

**Latency**: 100-300ms typical

### Hybrid Mode

FTS-first with semantic reranking for faster results.

```
POST /api/v1/pedr/search
{
  "query": "user authentication patterns",
  "top_k": 10,
  "rerank_mode": "hybrid",
  "candidate_pool": 100
}
```

**Flow**:
1. PostgreSQL FTS retrieves `candidate_pool` results (<50ms)
2. Semantic model reranks candidates (<100ms)
3. Top-k returned to client

**Latency**: <200ms typical (target: <300ms)

**Implementation**: `app/services/pedr/hybrid_rerank.py`

---

## Filter Parameters

### Core Filters

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | UUID | Filter by project |
| `document_id` | UUID | Filter by specific document |
| `source_type` | string | Filter by source type (interview, survey, etc.) |
| `source_origin` | string | Filter by origin: `upload`, `synthesized`, `imported` |

### Content Filters

| Parameter | Type | Description |
|-----------|------|-------------|
| `document_types` | list[string] | Filter by document MIME types |
| `source_types` | list[string] | Filter by source types |
| `date_from` | date | Documents from this date |
| `date_to` | date | Documents until this date |
| `tags` | list[string] | Filter by tags (OR semantics) |

### PEDR-Specific Filters

| Parameter | Type | Description |
|-----------|------|-------------|
| `element_type` | string | Single element type filter |
| `element_types` | list[string] | Multiple element types |
| `auto_detect_type` | bool | Auto-detect type from query |
| `type_boost_enabled` | bool | Enable type-based boosting |
| `intent_boost_enabled` | bool | Enable intent-based boosting |
| `min_quality_gates` | int | Minimum passing gates required |
| `status_filters` | list[string] | Allowed quality statuses |
| `allow_pii` | bool | Include PII-flagged content |

### Layer Control

| Parameter | Type | Description |
|-----------|------|-------------|
| `enable_lexical` | bool | Enable/disable lexical layer |
| `enable_semantic` | bool | Enable/disable semantic layer |
| `enable_syntactic` | bool | Enable/disable syntactic layer |
| `enable_pragmatic` | bool | Enable/disable pragmatic layer |
| `enable_governance` | bool | Enable/disable governance layer |
| `layer_weights` | object | Custom layer weights |

### Graph Layer Options (L6)

| Parameter | Type | Description |
|-----------|------|-------------|
| `enable_graph` | bool | Enable/disable graph expansion |
| `graph_depth` | int | Max BFS traversal depth (1-5) |
| `graph_decay` | float | Score decay per hop (0.1-1.0) |
| `graph_edge_types` | list[string] | Optional edge type filter |
| `graph_weight` | float | Graph layer weight in RRF (0.0-0.5) |

---

## Caching

PEDR implements query result caching for latency optimization.

### Configuration

```python
# app/core/config.py
pedr_cache_enabled: bool = True
pedr_cache_ttl_seconds: int = 300  # 5 minutes
pedr_cache_max_size: int = 1000    # LRU entries
```

### Cache Key

Cache keys are built from:
- Query text
- `top_k` value
- All filter parameters (project_id, source_type, etc.)

### Cache Invalidation

- **TTL expiry**: 5-minute default
- **LRU eviction**: When max size exceeded
- **Document changes**: Invalidated when documents updated

### Performance Impact

| Scenario | Latency |
|----------|---------|
| Cache hit | <10ms |
| Cache miss (full) | 100-300ms |
| Cache miss (hybrid) | <200ms |

**Implementation**: `app/services/pedr/cache.py`

---

## Response Structure

```json
{
  "results": [
    {
      "chunk_id": "f6c9...f1d8",
      "content": "The chunk text content...",
      "document_id": "08be...2fd5",
      "project_id": "1ee7...0bc3",
      "rrf_score": 0.0234,
      "rrf_rank": 1,
      "layer_ranks": {"lexical": 3, "semantic": 1, "graph": 4},
      "layer_scores": {"lexical": 0.78, "semantic": 0.92, "graph": 0.12},
      "urn": "urn:tracelab:chunk:f6c9...f1d8",
      "element_type": "finding",
      "query_intent": "factual",
      "quality_score": 0.85,
      "quality_gates_passed": 4,
      "contributing_layers": ["lexical", "semantic", "graph"],
      "source_type": "interview",
      "source_origin": "upload"
    }
  ],
  "metadata": {
    "query": "user authentication patterns",
    "intent": "factual",
    "intent_confidence": 0.82,
    "detected_type": "finding",
    "type_confidence": 0.75,
    "layers_used": ["lexical", "semantic", "graph"],
    "layer_weights": {"lexical": 0.23, "semantic": 0.322, "graph": 0.08, ...},
    "timings": {
      "lexical_ms": 45.2,
      "semantic_ms": 89.1,
      "graph_ms": 12.4,
      "syntactic_ms": 2.3,
      "pragmatic_ms": 1.8,
      "governance_ms": 5.4,
      "fusion_ms": 3.2,
      "total_ms": 147.0
    },
    "graph_enabled": true,
    "graph_candidates_expanded": 82,
    "total_candidates": 60,
    "result_count": 10,
    "cache_hit": false
  }
}
```

---

## Related Documentation

- [API Overview](../api/README.md) - Full endpoint reference
- [Graph Layer Addendum](../pedr-search.md) - L6 telemetry and benchmarks
- [Mission Protocol](./mission-protocol.md) - Evidence and synthesis schemas
- [DeepSearch Integration](../integration/deepsearch.md) - Agent integration patterns
- [Quality-Aware Search](../quality-aware-search.md) - Quality gate details
- [Qdrant Optimization](../qdrant-optimization.md) - Vector search tuning
