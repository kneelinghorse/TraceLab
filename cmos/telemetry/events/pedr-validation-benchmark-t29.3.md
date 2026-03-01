# PEDR vs Baseline Comparison

## Summary Metrics

| Metric | Baseline (Hybrid) | PEDR Quality | Delta |
| --- | --- | --- | --- |
| Precision@5 | 0.161 | 0.161 | 0.000 |
| Recall@5 | 0.807 | 0.807 | 0.000 |
| nDCG@5 | 0.658 | 0.658 | 0.000 |

## Sign Test (Per-Query Wins)

| Metric | Wins | Losses | Ties | p-value |
| --- | --- | --- | --- | --- |
| Precision@5 | 0 | 0 | 57 | n/a |
| Recall@5 | 0 | 0 | 57 | n/a |
| nDCG@5 | 0 | 0 | 57 | n/a |

## Quality Boost Validation

- Complete average multiplier: 0.10
- Draft average multiplier: 0.00
- Complete vs draft ratio: 0.00x

## Governance Filtering

- PII flagged in top-k: 0
- PII removed: 0
- Non-PII removed by gate filter: 285
- PII removal rate: 0.00

## Relationship Enrichment

- Avg related docs per query: 222.28
- Avg unique related docs per query: 51.86
- Avg results with related docs: 0.96
