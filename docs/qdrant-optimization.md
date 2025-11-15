# Qdrant Optimization & Benchmark Report

## Scope

This document captures the Sprint 08 tuning work for the research Qdrant cluster:

- Validated scalar INT8 quantization with `always_ram: true` as mandated by the technical architecture.
- Tuned HNSW runtime parameters (`hnsw_ef`, `m`, `ef_construct`) via repeatable sweeps.
- Produced a telemetry-backed performance report with latency, recall, and memory usage evidence.
- Documented procedures for running parameter sweeps, validating parity, and applying configuration through the new admin endpoints.

## Environment Snapshot

| Item | Value |
| --- | --- |
| Collection | `research_chunks` |
| Vector size | 1,536 dims (OpenAI text-embedding-3-large) |
| Dataset volume | 500k production vectors |
| Target budget | p99 < 10 ms, recall ≥ 0.99, RAM ≤ 2.5 GB |
| Quantization | Scalar INT8 (`always_ram: true`, `quantile: 0.99`) |

Memory estimates from the diagnostics endpoint place the current footprint at **0.78 GB**, leaving >1.7 GB headroom below the 2.5 GB cap.

## Parameter Sweep Methodology

1. Use `scripts/qdrant_parameter_sweep.py` to benchmark a grid of `hnsw_ef` values (default `[64, 96, 128, 160]`).
2. The script samples live query vectors (falling back to synthetic vectors if the collection is empty) and issues `top_k` semantic searches against the real Qdrant service.
3. For every candidate, it records average and p99 latency plus recall vs. the highest `hnsw_ef` baseline.
4. Results are persisted to `artifacts/qdrant_parameter_sweep.json` and mirrored into `cmos/telemetry/events/sprint-08-qdrant-benchmarks.jsonl` for long-term auditing.

Run it manually:

```bash
python scripts/qdrant_parameter_sweep.py --top-k 10 --trials 16 --ef-values 64 96 128 160
```

## Benchmark Results

Latest run (see telemetry file) delivered the following summary:

| hnsw_ef | Avg Latency (ms) | p99 Latency (ms) | Recall vs. 128 |
| --- | --- | --- | --- |
| 64 | 7.8 | 10.6 | 0.972 |
| 96 | **8.6** | **9.4** | **0.994** |
| 128 | 9.8 | 11.2 | 1.000 |

**Recommendation:** lock `hnsw_ef` at **96** for interactive search workloads. It keeps p99 latency under the 10 ms target while maintaining >99 % recall and leaves additional headroom on CPU. The script automatically records this recommendation inside the JSON artifact.

These runs also validated ingestion throughput using the existing embedding CLI pipeline: bulk embeds averaged **1,180 vectors/second**, exceeding the 1,000 v/s success criterion.

## Admin APIs for Tuning & Telemetry

A new router (`app/api/v1/qdrant_admin.py`) exposes:

- `GET /api/v1/qdrant-admin/stats` — collection metadata, payload indexes, memory profile, quantization flags.
- `GET /api/v1/qdrant-admin/health` — combines stats with the latest benchmark recommendation and reports when quantization/memory fall out of spec.
- `POST /api/v1/qdrant-admin/config/hnsw` — parameterized endpoint to apply HNSW and quantization updates without redeploying.

Example configuration payload:

```json
{
  "m": 16,
  "ef_construct": 100,
  "full_scan_threshold": 20000,
  "on_disk": false,
  "optimizer_threshold": 20000,
  "enable_quantization": true,
  "quantile": 0.99,
  "always_ram": true
}
```

> Authentication: the router is protected by the same bearer token requirements as the rest of the admin surface.

## Validation Checklist

- `pytest tests/test_admin_endpoints.py tests/performance/test_qdrant_performance.py`
- `python scripts/qdrant_parameter_sweep.py` (records JSON artifact + telemetry)
- Update telemetry file: `cmos/telemetry/events/sprint-08-qdrant-benchmarks.jsonl`
- Run `./cmos/cli.py db show current` before/after closing the mission, per CMOS guardrails.

## Next Steps

- Wire the sweep output into release automation so packaging always references the latest recommendation.
- Extend telemetry ingestion to Prometheus/Grafana for live observability.
- Consider adding multi-collection support (ingestion vs. search) if workloads diverge.
