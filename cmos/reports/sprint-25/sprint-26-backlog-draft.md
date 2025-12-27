# Sprint 26 Backlog Draft: Graph Layer Hardening + UX

## Objectives
- Stabilize graph layer performance and telemetry in production.
- Expand edge coverage and improve UX visibility.
- Close remaining health backlog items from the graph plan.

## Candidate Missions

### B26.1 Graph Telemetry + Benchmarking
- Capture graph layer latency, adjacency cache hit rate, and memory usage in telemetry.
- Add a repeatable benchmark script + docs update with production baselines.
- Success: telemetry dashboard shows graph_ms + cache hit rate; benchmark report committed.

### B26.2 Graph Layer Tuning
- Evaluate default depth/decay/weight with real workloads.
- Tune graph_top_k_seeds (internal config) and seed selection strategy.
- Success: updated defaults with documented latency/quality tradeoffs.

### B26.3 Edge Type Expansion + Validation
- Add missing edge types (report -> project, insight -> mission, etc.).
- Update manifest transformer and validation tests.
- Success: new edge types materialized and covered by tests.

### B26.4 Graph Visualization in Console
- Add a minimal graph expansion view for debugging (UI or API endpoint).
- Success: engineers can inspect graph traversal for a URN.

### B26.5 PEDR Docs Alignment
- Update `docs/architecture/PEDR-search.md` to reflect L6 graph layer.
- Add a brief L6 section and reference `docs/pedr-search.md`.
- Success: architecture docs match current six-layer implementation.

### B26.6 Health Backlog Closure
- Add missing DB indexes (ingestion_jobs, documents processed/chunked/embedded).
- Replace ingestion BackgroundTasks with persistent queue.
- Implement document deduplication via content hash.
- Success: health backlog items resolved or promoted with estimates.

### B26.7 Graph RAG Reliability
- Add `tiktoken` availability check + fallback for GraphRAGHelper tests.
- Success: Graph RAG tests run in CI without skips.
