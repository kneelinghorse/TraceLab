# PEDR Search (Graph Layer Addendum)

**Status**: L6 graph layer delivered (Sprint 25)
**Primary reference**: docs/architecture/PEDR-search.md
**Plan reference**: cmos/foundational-docs/pedr-graph-search-plan.md

## Scope

This addendum captures L6 graph layer telemetry and tuning notes.
Architecture, traversal flow, and configuration options live in `docs/architecture/PEDR-search.md`.

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
