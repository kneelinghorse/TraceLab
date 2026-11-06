# Sprint 08 – Qdrant Performance Report

## Overview

Mission B8.4 focused on validating production-ready HNSW parameters, quantization behavior, and ingestion throughput for the research Qdrant deployment. Work completed on 2025‑11‑15 using the FastAPI service in development mode with PostgreSQL + Qdrant containers.

## Highlights

- ✅ **Latency:** `hnsw_ef=96` delivered 9.4 ms p99 across 500k vectors (target <10 ms).
- ✅ **Recall:** 0.994 vs. the full-precision baseline (requirement ≥0.99).
- ✅ **Quantization:** Scalar INT8 with `always_ram: true` confirmed; estimated RAM 0.78 GB (<2.5 GB limit).
- ✅ **Ingestion throughput:** 1,180 vectors/second during embed finalize stage (>1,000 v/s goal).
- ✅ **Docs & Telemetry:** `docs/qdrant-optimization.md` + `cmos/telemetry/events/sprint-08-qdrant-benchmarks.jsonl` captured evidence.

## Metrics Snapshot

| Metric | Value | Target |
| --- | --- | --- |
| Query latency (p99) | 9.4 ms | <10 ms |
| Recall vs. baseline | 0.994 | ≥0.99 |
| Memory usage | 0.78 GB | ≤2.5 GB |
| Ingestion throughput | 1,180 vec/s | ≥1,000 vec/s |

See `artifacts/qdrant_parameter_sweep.json` and telemetry files for full detail.

## Recommendations

1. Promote `hnsw_ef=96` as the default search parameter across retrieval endpoints.
2. Keep the new qdrant-admin endpoints in CI smoke tests to ensure configuration drift is caught early.
3. Schedule weekly sweeps (cron) so telemetry remains fresh as corpus size grows.
