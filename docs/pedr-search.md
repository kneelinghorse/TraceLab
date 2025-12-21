# PEDR Search (Graph Layer Addendum)

**Status**: L6 graph layer delivered (Sprint 25)
**Primary reference**: docs/architecture/PEDR-search.md
**Plan reference**: cmos/foundational-docs/pedr-graph-search-plan.md

## Scope

This document covers the L6 graph layer (GraphLayerService) and its API surface.
Layers 1-5 remain documented in `docs/architecture/PEDR-search.md`.

## L6 Graph Layer Overview

- Graph edges are materialized in `graph_edges` and traversed via BFS.
- Seeds come from explicit URNs or the top lexical/semantic results.
- Scores decay per hop (`graph_decay`) and are fused via RRF (`graph_weight`).
- Results include `chunk_id` (for RRF) and `urn` (for provenance).
- Optional graph context can be appended to RAG prompts via GraphRAGHelper.

## API Usage

Request fields (see `app/schemas/pedr_search.py`):
- `enable_graph` (bool)
- `graph_depth` (1-5)
- `graph_decay` (0.1-1.0)
- `graph_edge_types` (list or null)
- `graph_weight` (0.0-0.5)

Example:

```bash
curl -X POST /api/v1/pedr/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "governance risk",
    "enable_graph": true,
    "graph_depth": 2,
    "graph_decay": 0.7,
    "graph_edge_types": ["contains", "references"],
    "graph_weight": 0.12
  }'
```

## Response Metadata

Graph execution surfaces in `metadata`:
- `graph_enabled`
- `graph_candidates_expanded`
- `timings.graph_ms`

## Telemetry and Benchmarks

Baseline latency for 1K edges (SQLite):
- Depth 1: 21.95 ms (500 candidates)
- Depth 2: 41.73 ms (1000 candidates)
- Depth 3: 280.66 ms (1000 candidates)

Reference: `cmos/telemetry/events/sprint-25-graph-baseline.json`.

Cache effectiveness (adjacency cache):
- Dual-seed micro-benchmark: ~0.50 hit rate (750 hits / 1502 lookups) at depth 2.
- Single-seed expansions typically see near-zero hit rates because each URN is fetched once.

Memory usage (Python heap):
- ~0.9 MB peak for depth 2 micro-benchmark (1000 edges, 2 seeds, 750 candidates).

## References

- `docs/architecture/PEDR-search.md`
- `cmos/foundational-docs/pedr-graph-search-plan.md`
- `cmos/telemetry/events/sprint-25-graph-baseline.json`
