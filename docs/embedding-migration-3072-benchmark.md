# Embedding Migration Benchmark (1536d -> 3072d)

Date: 2026-03-01

## Scope

This report compares semantic retrieval behavior before and after the embedding migration:

- Baseline: `research_chunks` + `text-embedding-3-small` (`1536d`)
- Migrated: `research_chunks_v2_3072d` + `text-embedding-3-large` (`3072d`)

Corpus source: existing PostgreSQL `document_chunks` corpus (`13068` chunk rows).  
Query set: `150` sampled chunk-derived queries (`top_k=5`).

## Commands

```bash
DEBUG=false ./.venv/bin/python scripts/embedding_collection_benchmark.py \
  --collection research_chunks \
  --model text-embedding-3-small \
  --dimension 1536 \
  --sample-size 150 \
  --top-k 5 \
  --output artifacts/benchmarks/embedding-benchmark-1536-small.json

DEBUG=false ./.venv/bin/python scripts/embedding_collection_benchmark.py \
  --collection research_chunks_v2_3072d \
  --model text-embedding-3-large \
  --dimension 3072 \
  --sample-size 150 \
  --top-k 5 \
  --output artifacts/benchmarks/embedding-benchmark-3072-large.json
```

## Results

| Metric | 1536d Small | 3072d Large | Delta |
| --- | ---: | ---: | ---: |
| Precision@5 | 0.5573 | 0.5840 | +0.0267 |
| Recall@5 | 0.9467 | 0.9200 | -0.0267 |
| nDCG@5 | 0.8715 | 0.8579 | -0.0136 |
| Search latency avg (ms) | 48.996 | 62.731 | +13.735 |
| Search latency P95 (ms) | 55.884 | 131.309 | +75.425 |
| Search latency P99 (ms) | 68.423 | 142.597 | +74.174 |

## Validation Notes

- Latency guardrail (`P95 < 200ms`) is satisfied after migration (`131.309ms`).
- HNSW defaults were retained (`m=16`, `ef_construct=100`, `ef_search default=64`) and remain within latency target on current corpus.
- HNSW sweep (`ef=[48,64,96,128]`) against `research_chunks_v2_3072d` produced `P99 <= 71.594ms` with `recall=1.0` across tested values.
- Benchmark artifacts:
  - `artifacts/benchmarks/embedding-benchmark-1536-small.json`
  - `artifacts/benchmarks/embedding-benchmark-3072-large.json`
  - `artifacts/qdrant_parameter_sweep_3072d.json`

## Interpretation

- Larger embeddings improved precision in this benchmark.
- Recall and nDCG were slightly lower in this sample; this should be tracked with domain-labeled query sets in future evaluation runs.
