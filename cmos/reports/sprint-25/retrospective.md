## Sprint 25 Retrospective: L6 Graph Layer

### Completed Work
- [x] B25.1: GraphLayerService
- [x] B25.2: Orchestrator Integration
- [x] B25.3: API Schema Extension
- [x] B25.4: Graph RAG Helper
- [x] B25.5: Integration Testing

### Key Metrics
- Graph layer latency (SQLite baseline, 1K edges): depth 1 21.95 ms, depth 2 41.73 ms, depth 3 280.66 ms.
- Graph layer latency gate: depth 2 <200 ms in integration test.
- Cache hit rate (adjacency cache, dual-seed micro-benchmark): 0.50 (750 hits / 1502 lookups).
- Memory usage (Python heap, same benchmark): ~0.9 MB peak.
- Test coverage: 50+ new tests across unit/integration; coverage % not captured.

### Decisions Made
- Graph layer is the L6 retrieval layer fused via RRF.
- Default graph parameters: depth=2, decay=0.7, weight=0.12; graph disabled by default.
- Graph layer output includes `chunk_id` + `urn` to keep RRF compatibility and provenance.
- Graph edge changes invalidate PEDR cache to avoid stale graph results.
- GraphRAGHelper is optional and gated by RAG config.

### Learnings
- Depth 2 keeps latency stable; depth 3 adds large overhead (baseline 280+ ms).
- Adjacency cache benefits increase with overlapping seed expansions; single-seed searches see minimal cache hits.
- `tiktoken` is required for full GraphRAGHelper test coverage; without it, tests skip.

### Sprint 26 Candidates
- Graph layer tuning (weights, depth defaults, seed selection) with production telemetry.
- Capture memory + cache metrics in telemetry (graph cache hit rate, heap/adjacency stats).
- Extend edge types and update manifest transformation.
- Graph visualization in console for debugging and UX.
- Align architecture docs with L6 graph layer.

### Health Backlog Items (from pedr-graph-search-plan.md)
- Add missing DB indexes (ingestion_jobs, documents processed/chunked/embedded).
- Replace ingestion BackgroundTasks with persistent queue.
- Document deduplication via content hash.
- Model/schema index alignment (document_chunks.content_tsv).
