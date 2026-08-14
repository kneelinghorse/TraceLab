# TraceLab Scripts

Utility scripts for development, benchmarking, and operations.

## PEDR Latency Benchmark

The `pedr_latency_benchmark.py` script measures PEDR search performance against standardized queries.

### Quick Start

```bash
# Basic run (requires server on localhost:8000)
python scripts/pedr_latency_benchmark.py

# Save results for tracking
python scripts/pedr_latency_benchmark.py -o cmos/telemetry/events/pedr-benchmark-$(date +%Y%m%d).json

# Compare to Sprint 18 baseline
python scripts/pedr_latency_benchmark.py -c cmos/reports/sprint-18/pedr-baseline-capture.json
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-o, --output` | Save results to JSON file | None |
| `-c, --compare` | Compare to baseline JSON | None |
| `-r, --runs` | Runs per query | 3 |
| `-m, --mode` | `full` or `hybrid` | `full` |
| `--api-base` | API URL | `http://localhost:8000/api/v1` |
| `--top-k` | Results per query | 10 |
| `--hnsw-ef` | Qdrant HNSW ef parameter | 128 |
| `-q, --quiet` | Suppress progress output | False |
| `--queries` | Custom queries (comma-separated) | Standard 10 |

### Targets (Sprint 19)

| Metric | Target | Description |
|--------|--------|-------------|
| P50 | < 500ms | Interactive use threshold |
| P95 | < 1000ms | Tail latency bound |
| Improvement | >= 50% | vs Sprint 18 baseline |

### Rerank Modes

- **full**: Standard 5-layer PEDR search (lexical, semantic, syntactic, pragmatic, governance)
- **hybrid**: FTS-first with semantic reranking (<300ms target latency)

### Environment Variables

```bash
# Authentication (optional if running locally with test user)
export TRACELAB_JWT_TOKEN="your-jwt-token"

# Or username/password for auto-auth
export TRACELAB_USERNAME="<production-test-user>"
export TRACELAB_PASSWORD="<production-test-password>"

# API base URL override
export TRACELAB_API_BASE="http://localhost:8000/api/v1"
```

### Output Format

Results are saved as JSON with this structure:

```json
{
  "timestamp": "2025-12-10T12:00:00Z",
  "sprint": "sprint-19",
  "benchmark_type": "pedr_latency",
  "rerank_mode": "full",
  "queries": [
    {
      "query": "usability testing best practices",
      "runs": 3,
      "p50_ms": 245.0,
      "mean_ms": 250.0,
      "layer_timings": {
        "lexical_ms": 45.0,
        "semantic_ms": 150.0,
        "syntactic_ms": 5.0,
        "pragmatic_ms": 10.0,
        "governance_ms": 8.0,
        "fusion_ms": 12.0
      }
    }
  ],
  "aggregate": {
    "p50_ms": 280.0,
    "p95_ms": 450.0,
    "p99_ms": 520.0,
    "mean_ms": 295.0
  },
  "comparison": {
    "baseline_p50_ms": 600.0,
    "improvement_pct": 53.3,
    "targets": {
      "p50_target_met": true,
      "improvement_target_met": true
    }
  }
}
```

### CI/CD Integration

The script returns exit codes for CI integration:
- `0`: All targets met
- `1`: P50 target not met
- `2`: Regression detected (>10% worse than baseline)

Example GitHub Actions step:

```yaml
- name: Run PEDR benchmark
  run: |
    python scripts/pedr_latency_benchmark.py \
      -c cmos/reports/sprint-18/pedr-baseline-capture.json \
      -o benchmark-results.json
```

---

## PEDR Benchmark Regression

`pedr_benchmark_regression.py` runs the offline PEDR benchmark, appends a
benchmark history entry, and flags regressions when nDCG drops more than 5% from
the stored baseline.

Outputs:
- `telemetry/events/benchmark-history.jsonl` (run history)
- `telemetry/events/benchmark-baseline.json` (regression baseline)
- `telemetry/events/.artifacts/pedr-benchmark-comparison.json` (comparison snapshot)

Example usage:

```bash
# First run: generate corpus/queries and set baseline
python scripts/pedr_benchmark_regression.py --rebuild-corpus --rebuild-queries --rebuild-baseline --init-baseline

# Subsequent runs: compare to baseline
python scripts/pedr_benchmark_regression.py --rebuild-corpus --rebuild-queries --rebuild-baseline
```

Exit codes:
- `0`: No regression detected
- `1`: Baseline missing (use --init-baseline)
- `2`: Regression detected (>5% nDCG drop)

---

## Other Scripts

### Baseline Capture

`pedr_baseline_capture.py` - Captures baseline metrics using direct DB access (Sprint 18).

### Graph Tuning Baseline

`pedr_graph_tuning_baseline.py` - Runs recent search history queries through PEDR with graph telemetry enabled and writes JSONL output for tuning analysis.

```bash
python scripts/pedr_graph_tuning_baseline.py \
  --output cmos/telemetry/events/graph-tuning-baseline.jsonl
```

### PEDR Benchmark

`pedr_benchmark.py` - Direct orchestrator benchmark without HTTP layer.

### Mission Map Generator

`generate_mission_map.py` - Generates a `mission_map.json` mapping the benchmark
corpus doc IDs to real mission IDs/UUIDs for production metadata scoring.

### Hybrid Rerank Benchmark

`hybrid_rerank_benchmark.py` - Benchmarks hybrid FTS+semantic reranking specifically.

### Qdrant Parameter Sweep

`qdrant_parameter_sweep.py` - Tests different HNSW parameters to optimize recall/latency tradeoff.

### Ingestion

- `ingest_cli.py` - CLI for document ingestion
- `upload_corpus.py` - Batch upload documents to TraceLab
- `verify_ingestion_parity.py` - Verify ingestion consistency

### Development

- `dev-setup.sh` - Initial development environment setup
- `bump-version.sh` - Version bumping for releases
