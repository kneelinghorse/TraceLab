# PEDR Graph Search Plan and Semantic Protocol Alignment

References:
- cmos/foundational-docs/technical_architecture.md
- cmos/foundational-docs/roadmap.md
- cmos/planning/PEDR-docs/protocol-enhanced-deep-research/COMPREHENSIVE_REPORT.md
- pedr/protocols/Updated-Semantic-Protocol.md
- pedr/protocols/Semantic Protocol v3.3.0 (graph-ready) file in pedr/protocols (filename uses an em dash)

## Goals
- Align TraceLab PEDR semantic protocol with v3.3.0 graph-ready semantics.
- Add a first-class graph search capability as the missing L6 layer.
- Preserve backward compatibility for existing manifests and API consumers.
- Deliver a durable, observable implementation suitable for long-term use.

## Current State (Summary)
- PEDR search is 5-layer with optional relational expansion for display.
- Semantic protocol is Python v3.2.0, with relationships as lists but no explicit edges array.
- Graph expansion is available via SQL joins (RelationalService) and exposed via `pedr/related`.
- No graph scoring layer is integrated into ranking.

## Recommendations (Decisions)
1) Graph storage: Start with Postgres-backed edges to avoid new infrastructure and keep joins local.
   - Create a `graph_edges` table with indexes on `from_urn`, `to_urn`, and `type`.
   - Materialize edges from existing relations plus explicit edges from manifests.
   - Reassess external graph DB only if query latency or graph size demands it.
2) Graph proximity scoring: Implement as a dedicated L6 layer and fuse with RRF.
   - Reason: consistent with PEDR architecture, tunable weights, and stable ranking behavior.
   - Alternative (post-fusion boost) is simpler but less interpretable and harder to tune.
3) MVP edge types:
   - mission -> evidence (chunk)
   - project -> document
   - document -> chunk
   - mission -> project
   - report -> chunk
   - insight -> chunk

## Semantic Protocol Alignment (v3.3.0)
- Deterministic identity and signature: exclude timestamps from stable hashes.
- Add `relationships.edges[]` with normalized, deduped edges.
- Maintain legacy `relationships` keys for compatibility.
- Canonical JSON serialization for signature inputs.

## Graph Search Architecture (Target)
- Edge materialization:
  - Explicit edges emitted by Semantic Protocol and manifest transformer.
  - Implicit edges derived from existing relational joins for core entities.
- Graph layer retrieval:
  - Build candidate nodes via seed URNs (top K from lexical/semantic) or explicit user seeds.
  - BFS with depth cap (default 2), edge type filters, and decay scoring.
  - Output a scored candidate list for RRF fusion as the L6 layer.
- API:
  - Extend PEDR search payload with graph options (enable_graph, seeds, depth, edge_types, graph_weight).
  - Keep `pedr/related` for explicit expansion and debugging.

## Workstreams and Phases

Phase 0: Alignment and Specs ✅ COMPLETE (Sprint 24)
- Map v3.3.0 JS spec to Python implementation (fields, signature rules, edge schema).
- Define canonical edge types and directionality.
- Define graph scoring formula and default weights.

Phase 1: Semantic Protocol Update ✅ COMPLETE (Sprint 24)
- Update `app/services/pedr/semantic_protocol.py` to v3.3.0 semantics.
- Add edge normalization and stable signature calculation.
- Update `app/services/pedr/manifest_transformer.py` to emit edges from bindings.
- Add backward compatibility tests for legacy manifests.
- **74 tests passing** covering edge normalization, manifest transformation, and materialization.

Phase 2: Graph Storage and Materialization ✅ COMPLETE (Sprint 24)
- Add `graph_edges` model and migration (`022_graph_edges.py`).
- Implement `EdgeMaterializationService` with implicit (FK-derived) and explicit (manifest) edge creation.
- Upsert logic prevents duplicates; composite indexes support BFS traversal.
- **Migration ready** for graph_edges table creation.

Phase 3: Graph Retrieval and Scoring (L6) ✅ COMPLETE (Sprint 25)
- Implemented GraphLayerService BFS traversal with decay scoring and adjacency cache.
- Integrated graph layer into `app/services/pedr/search_orchestrator.py` between retrieval and RRF.
- Added graph layer timings + telemetry; defaults: depth=1, decay=0.7, weight=0.08 (graph opt-in).
- Added graph-layer tests in unified search suite.

Phase 4: API and RAG Integration ✅ COMPLETE (Sprint 25)
- Extended `app/schemas/pedr_search.py` and `app/api/v1/pedr_search.py` with graph params.
- Added graph metadata (graph_ms, candidates expanded) to responses.
- Implemented GraphRAGHelper (subgraph -> prune -> linearize) and optional integration in `app/services/rag_service.py`.

Phase 5: Validation and Documentation ✅ COMPLETE (Sprint 25)
- Integration tests: graph layer correctness, ranking stability, cache invalidation.
- End-to-end PEDR search validated with graph enabled.
- Performance baseline recorded at `cmos/telemetry/events/sprint-25-graph-baseline.json`.
- Documentation updated with graph search behavior and Sprint 25 retrospective.

## Validation Plan
- Unit tests: deterministic signatures, edge normalization, graph traversal.
- Integration tests: PEDR search with graph enabled.
- Telemetry: graph layer timing, candidates expanded, and cache hit rate.

## Risks and Mitigations
- Graph explosion: enforce depth/limit caps and cache adjacency.
- Signature drift: strict stable field list; keep runtime metadata separate.
- Backward compatibility: keep legacy `relationships` keys and default graph off.

## Related Health Backlog (from code review)
- Add missing DB indexes (ingestion_jobs, documents processed/chunked/embedded).
- Replace ingestion BackgroundTasks with a persistent queue.
- Expand CI to run full test suites.
- Document deduplication via content hash.
- Model/schema index alignment (document_chunks.content_tsv).

## Open Questions
- None. Decisions above cover storage, scoring, and MVP edge types.
