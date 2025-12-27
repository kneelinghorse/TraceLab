# Sprint 26: Graph Parameter Optimization (B26.3)

## Summary
- Baseline telemetry captured from recent production search history (28 queries).
- Graph layer expanded **0 candidates** across all queries.
- Graph layer added ~110-130 ms per request (p50 ~113 ms).
- A smaller seed run (depth=1, top_k_seeds=5) also produced 0 graph candidates and similar graph_ms.

## Telemetry Artifacts
- Baseline: `cmos/telemetry/events/graph-tuning-baseline.jsonl`
- Depth=1, seeds=5: `cmos/telemetry/events/graph-tuning-depth1-seeds5.jsonl`

## Key Findings
- **Graph impact**: 0% of results had graph contribution (0/28 queries).
- **Graph candidates**: total_candidates=0 for all events.
- **Latency**: graph_ms avg ~114 ms; total_ms avg ~1148 ms on baseline run.
- **Cache**: adjacency cache hit rate 0.0 (no edges retrieved).

## Decision and Updated Defaults
Given zero graph contribution but consistent latency cost, defaults are tuned to reduce overhead
until edge coverage is expanded (B26.4):

- `enable_graph`: **false** (opt-in)
- `graph_depth`: **1** (was 2)
- `graph_top_k_seeds`: **5** (was 10)
- `graph_weight`: **0.08** (was 0.12)
- `graph_decay`: **0.7** (unchanged)

Rationale: with no graph candidates and no impact on ranking, the safest optimization is to
make the graph layer opt-in and keep traversal conservative. Re-evaluate after edge type
expansion populates `graph_edges` with richer connectivity.

## Re-run Commands
```bash
DEBUG=false python scripts/pedr_graph_tuning_baseline.py \
  --output cmos/telemetry/events/graph-tuning-baseline.jsonl \
  --limit 100 --quiet

DEBUG=false python scripts/pedr_graph_tuning_baseline.py \
  --output cmos/telemetry/events/graph-tuning-depth1-seeds5.jsonl \
  --limit 100 --graph-depth 1 --graph-top-k-seeds 5 --quiet
```
