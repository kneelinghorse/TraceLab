# PEDR Benchmark Report - Quality-Aware Search vs Standard RAG
Version: 1.0
Date: 2025-12-28
Status: Draft for internal review
Audience: Search engineers, research platform engineers, product leads, and applied research teams

## Table of Contents
- [Executive Summary](#executive-summary)
- [1. Benchmark Objectives](#1-benchmark-objectives)
- [2. Experimental Design](#2-experimental-design)
  - [2.1 Corpus Composition and Provenance](#21-corpus-composition-and-provenance)
  - [2.2 Query Design and Relevance Grading](#22-query-design-and-relevance-grading)
  - [2.3 Baseline Retrieval Configuration](#23-baseline-retrieval-configuration)
  - [2.4 PEDR Quality-Aware Configuration](#24-pedr-quality-aware-configuration)
  - [2.5 Benchmark Pipeline](#25-benchmark-pipeline)
  - [2.6 Quality Scoring Model and Governance Filters](#26-quality-scoring-model-and-governance-filters)
- [3. Metrics and Statistical Testing](#3-metrics-and-statistical-testing)
  - [3.1 Ranking Metrics](#31-ranking-metrics)
  - [3.2 Latency Metrics](#32-latency-metrics)
  - [3.3 Sign Test and Effect Sizing](#33-sign-test-and-effect-sizing)
- [4. Results Summary](#4-results-summary)
  - [4.1 Summary Metrics](#41-summary-metrics)
  - [4.2 Sign Test](#42-sign-test)
  - [4.3 Charts](#43-charts)
- [5. Ranking Quality Analysis](#5-ranking-quality-analysis)
  - [5.1 Per-Query Outcomes](#51-per-query-outcomes)
  - [5.2 Query Category Breakdown](#52-query-category-breakdown)
  - [5.3 Failure Mode Highlights](#53-failure-mode-highlights)
  - [5.4 Case Study Snapshots](#54-case-study-snapshots)
- [6. Quality Boost Validation](#6-quality-boost-validation)
  - [6.1 Quality Metadata Distribution](#61-quality-metadata-distribution)
  - [6.2 Boost Behavior](#62-boost-behavior)
- [7. Governance Filtering Effectiveness](#7-governance-filtering-effectiveness)
  - [7.1 PII Tagging and Filter Policy](#71-pii-tagging-and-filter-policy)
  - [7.2 Outcome Analysis](#72-outcome-analysis)
- [8. Relationship Enrichment Coverage](#8-relationship-enrichment-coverage)
  - [8.1 Relationship Map Construction](#81-relationship-map-construction)
  - [8.2 Coverage Interpretation](#82-coverage-interpretation)
  - [8.3 Relationship Enrichment Examples](#83-relationship-enrichment-examples)
- [9. Latency Characteristics](#9-latency-characteristics)
  - [9.1 Latency Distribution](#91-latency-distribution)
  - [9.2 Production Expectations](#92-production-expectations)
  - [9.3 Latency Impact Scenarios](#93-latency-impact-scenarios)
- [10. Interpretation and Recommendations](#10-interpretation-and-recommendations)
  - [10.1 Decision Framing](#101-decision-framing)
  - [10.2 Tuning Roadmap](#102-tuning-roadmap)
- [11. Limitations and Threats to Validity](#11-limitations-and-threats-to-validity)
- [12. Next Steps](#12-next-steps)
- [Appendix A: Reproducibility](#appendix-a-reproducibility)
- [Appendix B: Benchmark Artifacts](#appendix-b-benchmark-artifacts)
- [Appendix C: Per-Query nDCG Deltas](#appendix-c-per-query-ndcg-deltas)
- [Appendix D: Query Set](#appendix-d-query-set)
- [Appendix E: Metric Definitions](#appendix-e-metric-definitions)
- [Appendix F: Corpus Manifest Summary](#appendix-f-corpus-manifest-summary)

---

## Executive Summary

This benchmark compares PEDR quality-aware search against the standard RAG/hybrid baseline defined in R27.1. The benchmark uses a fixed corpus of 12 TraceLab documents and a 12-query graded relevance set. All experiments are offline and CPU-only to remove external dependencies and isolate ranking effects.

The baseline hybrid retrieval (TF-IDF + BM25 fusion) outperforms PEDR quality-aware ranking on precision, recall, and nDCG. PEDR quality-aware ranking records Precision@5 = 0.233, Recall@5 = 0.750, and nDCG@5 = 0.643 compared to the hybrid baseline Precision@5 = 0.283, Recall@5 = 0.875, and nDCG@5 = 0.813. A paired sign test indicates that the observed differences are not statistically significant in this small sample (n = 12 queries), but the deltas are directionally consistent and large enough to warrant tuning.

Despite the ranking dip, PEDR-specific features validate as designed. The quality scoring multiplier matches the expected 2x boost between complete and draft missions (1.25 vs 0.60; 2.08x ratio). Governance filtering removes 100% of PII-flagged results in top-k without removing any non-PII items. Relationship enrichment is strong, with 85% of results receiving related-document context and an average of 18.33 related documents per query.

Latency remains low because the benchmark is offline. P50 latency for the hybrid baseline is 0.130 ms versus 0.176 ms for PEDR quality-aware, and 0.078 ms for the governance-filtered variant (shorter due to filtering). These numbers should not be interpreted as production latency, but they confirm the overhead of additional ranking logic is measurable even on a small corpus.

Overall, the benchmark confirms PEDR's governance and quality signals work as intended, while highlighting a ranking-quality tradeoff that must be tuned before claiming superiority over standard hybrid retrieval. The recommended next step is to re-run the benchmark using production-quality metadata and a larger candidate pool to allow quality-aware reranking to operate with more headroom.

Key findings at a glance:

- Hybrid baseline remains best for raw ranking metrics on this corpus.
- Quality-aware scoring delivers the intended 2x boost for completed work.
- Governance filters are precise under PII-tagged scenarios.
- Relationship enrichment coverage is high and consistent.
- Tuning is needed to mitigate quality-driven relevance losses.

---

## 1. Benchmark Objectives

The objective of this benchmark is to quantify the tradeoff between PEDR quality-aware search and standard RAG/hybrid retrieval on a fixed corpus with graded relevance judgments. The study is designed to answer four core questions:

1. Does PEDR quality-aware ranking improve or degrade retrieval quality compared to the hybrid baseline?
2. Do PEDR quality multipliers align with the intended 2x boost between complete and draft missions?
3. Are governance filters effective at removing PII-flagged content without over-filtering?
4. Does relationship enrichment supply additional context at high coverage rates?

Success criteria for the benchmark are not binary; instead, this report aims to surface the directional tradeoff and quantify the tuning space. A minor ranking decline is acceptable if it is offset by higher quality compliance, but the decline observed here is large enough to require calibration before any claim of ranking superiority.

The benchmark is a continuation of R27.1 (baseline capture) and R27.2 (PEDR validation), consolidated into a publication-ready comparison report.

---

## 2. Experimental Design

### 2.1 Corpus Composition and Provenance

The benchmark corpus is the same for baseline and PEDR runs:

- **Corpus size:** 12 documents
- **Corpus source:** TraceLab documentation and sprint research reports
- **Corpus path:** `artifacts/benchmarks/benchmark-corpus/`
- **Query set:** 12 queries with graded relevance judgments (2 = primary, 1 = secondary)
- **Queries path:** `artifacts/benchmarks/benchmark-corpus/queries.json`

Corpus characteristics:

- **Total word count:** 11,709
- **Average word count:** 975.8
- **Min word count:** 167
- **Max word count:** 4,073

Category distribution:

| Category | Documents | Notes |
| --- | --- | --- |
| docs | 6 | Core architecture and subsystem documentation |
| reports | 4 | Sprint retrospectives and research reports |
| overview | 1 | README and system overview |
| scripts | 1 | Operational scripts reference |

The corpus emphasizes internal technical documentation because the benchmark target is internal research workflows rather than broad web-scale retrieval. This also reduces variance introduced by topic drift and focuses evaluation on system-specific relevance.

### 2.2 Query Design and Relevance Grading

The query set contains 12 queries covering the core functional areas of TraceLab and PEDR:

- PEDR search architecture and telemetry
- Hybrid search weighting and fusion
- Qdrant optimization and resilience guidance
- Quality gates and mission validation
- Sprint outcomes and benchmark scripts

Each query is graded with 1 to 2 relevant documents (primary relevance = 2, secondary relevance = 1). This structure mirrors common internal research searches, where a small number of authoritative documents should surface first and secondary documents provide supplementary context.

Relevance grading rules:

- A **primary document** directly answers the query.
- A **secondary document** provides supporting context.
- Non-matching documents are not graded.

This grading approach keeps the benchmark simple and interpretable while preserving a meaningful distinction between top-ranked and supporting results.

### 2.3 Baseline Retrieval Configuration

The hybrid baseline mirrors the production weighting described in `docs/hybrid-search.md`:

- **Semantic retrieval:** TF-IDF cosine similarity
- **Keyword retrieval:** BM25
- **Fusion:** Min-max normalization with weighted sum
- **Weights:** 0.7 semantic, 0.3 keyword
- **Top-K:** 5 results per query

The baseline is deterministic and offline, serving as a proxy for the production hybrid search pipeline without requiring Qdrant or external embeddings. It establishes the reference point for comparing PEDR ranking shifts.

### 2.4 PEDR Quality-Aware Configuration

PEDR evaluation reuses the hybrid candidate pool and applies quality-aware and governance-aware reranking:

- **Candidate pool:** top_k * 2 (candidate multiplier = 2)
- **Quality scoring:** `QualityScoringService` with synthetic mission metadata
- **Governance filters:** `min_quality_gates=3`, `allow_pii=False`
- **Relationship enrichment:** relationship mapping from `benchmark-corpus/relationships.json`

PEDR results are reported for two configurations:

1. **PEDR quality-aware:** Quality boost applied, no governance filtering.
2. **PEDR governance-filtered:** Quality boost plus governance filtering.

The synthetic metadata mirrors common mission states (draft, in_progress, review, complete) and gate coverage, allowing the benchmark to stress the quality-aware logic even on a small corpus.

### 2.5 Benchmark Pipeline

The benchmark pipeline executes the following steps:

1. Load corpus manifest and query set.
2. Run TF-IDF + BM25 retrieval to build a hybrid candidate pool.
3. Apply PEDR quality scoring to the candidate pool.
4. Apply governance filters for the governance-filtered variant.
5. Compute per-query metrics and aggregate summaries.
6. Generate comparison analysis and output artifacts.

This pipeline is fully reproducible with the scripts listed in Appendix A.

### 2.6 Quality Scoring Model and Governance Filters

PEDR quality-aware ranking is driven by `QualityScoringService`, which converts mission metadata into a quality multiplier that scales the hybrid combined score. The model is defined by five expected quality gates:

- research_statement
- evidence_links
- synthesis_quality
- traceability
- contradictions_resolved

Each document receives a base score of 0.60, plus boosts based on mission status and gate validation. Status boosts are tiered (complete, review, in_progress, draft), and a small validation boost is applied when gates are explicitly validated. Scores are bounded between 0.10 and 1.50 to prevent extreme amplification or suppression.

Governance filtering is applied through `QualityFilters` with `min_quality_gates=3` and `allow_pii=False`. Documents that fail the minimum gate threshold or are tagged with PII metadata are excluded from the governance-filtered variant. This strict policy is designed to represent compliance-sensitive contexts and is expected to reduce recall on queries whose primary documents are PII-tagged or still in draft status.

---

## 3. Metrics and Statistical Testing

### 3.1 Ranking Metrics

Metrics are computed per query and averaged across the query set:

- **Precision@5:** Relevant results in top-5 divided by 5.
- **Recall@5:** Relevant results in top-5 divided by all relevant results.
- **nDCG@5:** Normalized discounted cumulative gain at rank 5.

The combination of precision, recall, and nDCG balances relevance coverage with rank position. nDCG is emphasized because it reflects how PEDR shifts the ordering of relevant content.

### 3.2 Latency Metrics

Latency is measured as the offline compute time to score and rank each query. This is not a production latency metric; it is a deterministic measurement of algorithmic overhead in a CPU-only environment. It is used here to compare relative overhead between baseline and PEDR paths.

### 3.3 Sign Test and Effect Sizing

A paired sign test is applied to per-query deltas between the hybrid baseline and PEDR quality-aware results. The test is two-sided, uses per-query wins and losses, and reports a p-value for each metric. Because of the small query set, the sign test is treated as directional evidence rather than definitive statistical proof.

Effect sizing is expressed as absolute deltas in the summary table, which is the primary lens for evaluating tuning impact.

---

## 4. Results Summary

### 4.1 Summary Metrics

| Method | Precision@5 | Recall@5 | nDCG@5 | P50 Latency (ms) |
| --- | --- | --- | --- | --- |
| Hybrid baseline | 0.283 | 0.875 | 0.813 | 0.130 |
| PEDR quality-aware | 0.233 | 0.750 | 0.643 | 0.176 |
| PEDR governance-filtered | 0.267 | 0.792 | 0.644 | 0.078 |

### 4.2 Sign Test

| Metric | Wins | Losses | Ties | p-value |
| --- | --- | --- | --- | --- |
| Precision@5 | 0 | 2 | 10 | 0.5000 |
| Recall@5 | 0 | 2 | 10 | 0.5000 |
| nDCG@5 | 2 | 6 | 4 | 0.2891 |

### 4.3 Charts

![Benchmark quality metrics](../../../artifacts/benchmarks/final-comparison-charts/metrics-comparison.png)

![Latency distribution](../../../artifacts/benchmarks/final-comparison-charts/latency-comparison.png)

---

## 5. Ranking Quality Analysis

The hybrid baseline demonstrates higher aggregate ranking quality than PEDR quality-aware retrieval on this dataset. Precision and recall drop by 0.050 and 0.125 respectively, while nDCG declines by 0.170. The sign test shows mostly ties, indicating that many queries are unaffected, but the losses are concentrated in a subset of queries where PEDR applies large quality penalties or governance filters.

Key observations:

- **High-tie rate:** 10 of 12 queries show no change in precision or recall between baseline and PEDR quality-aware, suggesting that PEDR reranking only shifts outcomes when quality metadata is decisive.
- **nDCG sensitivity:** nDCG shows larger declines because it is sensitive to rank position changes, especially when top-ranked relevant items receive quality penalties.
- **Candidate pool pressure:** Using a candidate multiplier of 2 may be insufficient when quality-aware reranking demotes otherwise relevant items. Increasing the candidate pool should give PEDR more room to recover relevant results after applying quality and governance logic.

### 5.1 Per-Query Outcomes

The per-query nDCG deltas highlight which queries are most affected by quality-aware scoring:

- **Largest drops:** Q07 (implementation guide), Q08 (scripts README), Q10 (PEDR baseline capture), Q11 (graph optimization), and Q05 (Qdrant resilience).
- **Improvements:** Q04 (Qdrant parameter sweep) and Q12 (Qdrant optimization research) show small gains.
- **Stable cases:** Q02, Q03, Q06, and Q09 remain unchanged, indicating that quality metadata did not materially reorder these results.

The drops align with documents marked as draft or in_progress, which receive lower quality multipliers. This is by design but illustrates that the quality-aware system can demote high-relevance documents if their validation status is incomplete.

### 5.2 Query Category Breakdown

Grouping queries by category reveals patterns:

- **Architecture and system context:** Queries that map to complete documents (PEDR search, hybrid search) show stable performance.
- **Operational guidance:** Queries that map to draft or in_progress documentation show the largest decline.
- **Benchmark and sprint history:** Mixed results, with some report-backed queries holding steady and others dropping due to draft status.

This suggests that PEDR is more effective when the underlying content is fully validated, reinforcing its purpose as a quality-first retrieval system.

### 5.3 Failure Mode Highlights

Failure modes observed in this benchmark are not bugs but expected consequences of strict quality signaling:

- **Draft gating override:** Draft documents with high lexical relevance can be demoted below less relevant but fully validated content.
- **PII tagged documents:** Two documents are tagged with PII metadata and are removed in governance-filtered mode, which can sharply reduce recall for queries that depend on them.
- **Limited candidate pool:** When the candidate list is short, reranking has fewer opportunities to recover alternative relevant documents.

These are tuning targets rather than structural failures. The benchmark provides a clear map of which queries are most sensitive to quality signals, supporting targeted calibration.

### 5.4 Case Study Snapshots

The following snapshots illustrate how quality metadata changes ranking outcomes on specific queries:

**Q07 (Implementation guide):** The primary document is a draft with three passed gates and a PII tag. In quality-aware mode, it is demoted below completed reports with weaker lexical match; in governance-filtered mode, it is removed entirely. This produces the largest nDCG drop and represents an intentional compliance-first tradeoff.

**Q08 (Scripts README):** The primary document is also PII-tagged and draft. The hybrid baseline places it first, while the governance-filtered mode drops it. This highlights how operational documentation can be suppressed when metadata is incomplete.

**Q10 (PEDR baseline capture):** The baseline capture report is marked in_progress with three passed gates. It remains in the candidate pool, but the quality multiplier demotes it below more complete documents, lowering nDCG without changing precision.

**Q04 and Q12 (Qdrant optimization topics):** These queries map to complete or review documents with higher gate coverage, so quality-aware reranking either preserves or slightly improves the baseline order.

These snapshots demonstrate that PEDR is consistent with its mission: prioritize validated work. The challenge is balancing this priority against the reality that high-value technical documentation is often still in review or draft status.

---

## 6. Quality Boost Validation

The quality boost mechanism is one of PEDR's central design features. In this benchmark, it behaves as expected:

- **Complete average multiplier:** 1.25
- **Draft average multiplier:** 0.60
- **Complete vs draft ratio:** 2.08x

This validates the target behavior: completed missions with high gate coverage are approximately twice as influential as draft missions. The multiplier aligns with the quality-aware ranking claim, confirming that the scoring implementation matches design intent.

![Quality boost validation](../../../artifacts/benchmarks/final-comparison-charts/quality-boost.png)

### 6.1 Quality Metadata Distribution

The synthetic quality metadata was generated from explicit assignments in `scripts/pedr_validation_benchmark.py`. The distribution is intentionally balanced to surface differences between quality states:

| Status | Count |
| --- | --- |
| complete | 4 |
| draft | 4 |
| review | 2 |
| in_progress | 2 |

Gate pass distribution (out of 5 gates):

| Passed Gates | Documents |
| --- | --- |
| 5 | 4 |
| 4 | 2 |
| 3 | 6 |

Two documents are tagged with PII metadata in the synthetic mission data to test governance filtering (see Section 7).

### 6.2 Boost Behavior

Implications of the observed boost behavior:

- The boost is strong enough to create material ranking shifts, particularly when high-relevance documents are in draft status.
- The complete vs draft ratio aligns with the intended 2x policy, suggesting the boost formula itself is functioning correctly.
- The calibration question is not whether the multiplier works, but how aggressively it should be applied when relevance and quality conflict.

A recommended tuning path is to apply a smoother curve for mid-quality documents, preserving the 2x boost for truly complete work while softening penalties for in_progress or review items.

---

## 7. Governance Filtering Effectiveness

PEDR governance filtering is designed to remove sensitive or low-trust content from retrieval. In this benchmark it performs perfectly on the synthetic PII tags:

- **PII flagged in top-k:** 6
- **PII removed:** 6
- **Non-PII removed:** 0
- **Removal rate:** 1.00

![Governance filtering outcomes](../../../artifacts/benchmarks/final-comparison-charts/governance-filtering.png)

### 7.1 PII Tagging and Filter Policy

PII tags are injected through the synthetic metadata loader. Two documents are tagged with PII in mission metadata:

- `doc-007-implementation-guide`
- `doc-008-scripts-readme`

Governance filters are configured with `allow_pii=False`, which enforces hard exclusion of PII-tagged content. This strict configuration is appropriate for compliance-sensitive use cases but may be too aggressive for internal-only research contexts.

### 7.2 Outcome Analysis

The governance filter removes all tagged items without any false positives. This demonstrates that the filter pipeline correctly interprets mission metadata and enforces the policy. It also explains why some queries (notably Q07 and Q08) experience large recall drops in the governance-filtered variant, as their primary documents are excluded.

A staged governance approach is recommended for future tuning, where PII tags can apply a strong penalty rather than a full exclusion in scenarios where policy allows a compliance reviewer to override.

---

## 8. Relationship Enrichment Coverage

Relationship enrichment adds contextual edges between missions, documents, and reports. The benchmark confirms strong coverage:

- **Avg related docs per query:** 18.33
- **Avg unique related docs per query:** 9.83
- **Avg results with related docs:** 0.85

![Relationship enrichment coverage](../../../artifacts/benchmarks/final-comparison-charts/relationship-enrichment.png)

### 8.1 Relationship Map Construction

Relationship mappings are built from two sources:

1. **Category-based relationships:** Documents sharing the same category (docs, reports, overview, scripts) are linked.
2. **Explicit relationships:** Additional links are injected for known cross-references (e.g., PEDR search to hybrid search, Qdrant optimization to Qdrant research).

Across the corpus, the average number of related documents per item is 3.75, with a maximum of 6 and a minimum of 0. The highest relationship density appears in the PEDR search and Qdrant optimization documents, reflecting their central role in the documentation graph.

### 8.2 Coverage Interpretation

High relationship coverage does not directly boost ranking metrics in this benchmark, but it materially improves the context available to downstream synthesis. In production, these relationships are critical for surfacing adjacent evidence and enabling graph-based exploration in the PEDR L6 layer.

### 8.3 Relationship Enrichment Examples

Examples of explicit enrichment links include:

- **PEDR search -> hybrid search:** Ensures that the PEDR search overview is contextualized with hybrid scoring mechanics.
- **Qdrant optimization -> Qdrant research report:** Pairs operational guidance with empirical findings.
- **Hybrid search -> PEDR baseline capture:** Connects foundational search guidance with baseline evaluation artifacts.

These links create a higher confidence evidence trail for users who need to validate claims or trace the origin of a recommendation.

---

## 9. Latency Characteristics

Latency measurements are algorithmic and offline. They represent CPU-only scoring time, not production round-trip latency.

### 9.1 Latency Distribution

| Method | Mean (ms) | P50 (ms) | P95 (ms) |
| --- | --- | --- | --- |
| Hybrid baseline | 0.150 | 0.130 | 0.227 |
| PEDR quality-aware | 0.226 | 0.176 | 0.686 |
| PEDR governance-filtered | 0.107 | 0.078 | 0.259 |

The PEDR quality-aware path incurs extra overhead due to scoring and relationship enrichment. Governance filtering shortens latency because it reduces the candidate list before scoring completes.

### 9.2 Production Expectations

In production, latency will be dominated by IO (PostgreSQL, Qdrant) and orchestration overhead. The relative differences observed here should still hold, but absolute values will be much higher. For example, a 0.050 ms offline delta could translate to a 10 to 20 ms delta once network calls and cache lookups are included.

A practical deployment target is to keep PEDR quality-aware latency within 2x of hybrid search for interactive workflows, while allowing higher latency for deep research or asynchronous retrieval.

### 9.3 Latency Impact Scenarios

To ground the offline results, consider three practical scenarios:

1. **Interactive search (user-facing):** PEDR quality-aware should be optional or cached. The hybrid baseline should remain the default unless the user explicitly requests quality-aware ranking.
2. **Analyst deep-dive:** A 2x latency increase is acceptable if it yields higher-confidence evidence with governance guarantees.
3. **Automated agents:** Agents can tolerate higher latency if the results improve reuse detection or reduce redundant research.

These scenarios reinforce the need for configurable tradeoffs rather than a single universal search mode.

---

## 10. Interpretation and Recommendations

The benchmark indicates that PEDR's quality and governance features are working, but the ranking tradeoff is significant enough to prevent claiming superiority over the hybrid baseline at current settings. The results support a tuning phase rather than a go/no-go decision.

### 10.1 Decision Framing

- **If the objective is highest raw relevance:** the hybrid baseline remains the best default.
- **If the objective is quality-compliant retrieval:** PEDR quality-aware is already aligned with the protocol, but tuning is required to minimize relevance loss.
- **If the objective is compliance-first retrieval:** governance-filtered PEDR is appropriate, but should be paired with fallback options to avoid recall cliffs.

### 10.2 Tuning Roadmap

1. **Increase candidate multiplier (3-4x):** Allow the reranker to recover relevant items after quality penalties.
2. **Tune quality multiplier curves:** Consider a gentler slope for mid-quality items instead of a strict 2x ratio.
3. **Use production metadata:** Replace synthetic quality metadata with real mission data from PostgreSQL to reflect realistic gate distributions.
4. **Add soft governance penalties:** Apply score penalties before hard filtering to avoid sudden recall drops.
5. **Expand corpus and query set:** Increase to 50+ documents and 50+ queries to reduce variance and support stronger statistical testing.
6. **Track per-query failures:** The largest drops in nDCG are clustered in specific queries; inspect those cases to identify metadata-driven biases.

---

## 11. Limitations and Threats to Validity

- **Small corpus size:** 12 documents limits both precision and statistical power.
- **Synthetic metadata:** Quality gates are simulated; real data may reduce or amplify observed effects.
- **Offline retrieval:** Does not capture production latency or ranking signals from embeddings.
- **Short query set:** 12 queries is insufficient for strong statistical conclusions; results are directional.
- **No user interaction metrics:** The benchmark focuses on retrieval metrics, not downstream research impact.
- **Topic bias:** The corpus is heavy on architecture and operations documentation and may not reflect broader research topics.

These limitations do not invalidate the findings but they require caution when interpreting PEDR quality claims.

---

## 12. Next Steps

1. Build a larger, production-representative benchmark corpus and query set.
2. Run the same evaluation on Qdrant embeddings with the full PEDR stack.
3. Tune quality scoring with a calibration set derived from real mission metadata.
4. Establish recurring benchmark runs to track regression and improvements.
5. Incorporate user-facing evaluation (task success, time to insight) to complement ranking metrics.

---

## Appendix A: Reproducibility

To regenerate the baseline metrics:

```bash
python scripts/rag_baseline_benchmark.py --build-corpus --overwrite
```

To regenerate PEDR validation metrics:

```bash
python scripts/pedr_validation_benchmark.py --rebuild-metadata --rebuild-relationships
```

---

## Appendix B: Benchmark Artifacts

- Baseline metrics: `artifacts/benchmarks/rag-baseline-metrics.json`
- PEDR benchmark results: `artifacts/benchmarks/pedr-benchmark-results.json`
- Comparison analysis: `artifacts/benchmarks/comparison-analysis.md`
- Corpus manifest: `artifacts/benchmarks/benchmark-corpus/corpus_manifest.json`
- Query set: `artifacts/benchmarks/benchmark-corpus/queries.json`
- Quality metadata: `artifacts/benchmarks/benchmark-corpus/quality_metadata.json`
- Relationship mapping: `artifacts/benchmarks/benchmark-corpus/relationships.json`
- Charts: `artifacts/benchmarks/final-comparison-charts/`

---

## Appendix C: Per-Query nDCG Deltas

| Query | Hybrid nDCG@5 | PEDR nDCG@5 | Delta |
| --- | --- | --- | --- |
| Q01 | 0.760 | 0.480 | -0.281 |
| Q02 | 0.760 | 0.760 | +0.000 |
| Q03 | 0.760 | 0.760 | +0.000 |
| Q04 | 0.907 | 0.950 | +0.043 |
| Q05 | 0.950 | 0.643 | -0.307 |
| Q06 | 1.000 | 1.000 | +0.000 |
| Q07 | 0.458 | 0.000 | -0.458 |
| Q08 | 1.000 | 0.631 | -0.369 |
| Q09 | 1.000 | 1.000 | +0.000 |
| Q10 | 0.544 | 0.190 | -0.354 |
| Q11 | 1.000 | 0.631 | -0.369 |
| Q12 | 0.620 | 0.670 | +0.050 |

---

## Appendix D: Query Set

| Query | Text |
| --- | --- |
| Q01 | What components make up TraceLab and what is the high level architecture? |
| Q02 | How does PEDR search work and which telemetry baseline is referenced? |
| Q03 | How does hybrid search combine semantic and keyword scores and what weights are used? |
| Q04 | How do we run Qdrant parameter sweep benchmarks and what metrics are recorded? |
| Q05 | What resilience checks and recovery steps are recommended for Qdrant? |
| Q06 | How are quality gates evaluated and logged? |
| Q07 | What is the step by step implementation guide for deploying TraceLab? |
| Q08 | Which benchmark scripts exist for PEDR latency and hybrid rerank? |
| Q09 | What were the key outcomes of Sprint 19 latency optimization? |
| Q10 | What metrics are captured in the PEDR baseline capture report? |
| Q11 | What graph parameter optimization baselines and telemetry were used in Sprint 26? |
| Q12 | What were the main findings from the Qdrant optimization research report? |

---

## Appendix E: Metric Definitions

Precision@K:

```
Precision@K = (# of relevant items in top K) / K
```

Recall@K:

```
Recall@K = (# of relevant items in top K) / (total relevant items)
```

nDCG@K:

```
DCG@K = sum((2^rel_i - 1) / log2(i + 1)) for i = 1..K
nDCG@K = DCG@K / IDCG@K
```

The benchmark uses graded relevance scores (2 for primary, 1 for secondary), which are reflected in the DCG calculation.

---

## Appendix F: Corpus Manifest Summary

| Doc ID | Title | Category | Source | Word Count |
| --- | --- | --- | --- | --- |
| doc-001-readme | TraceLab README | overview | README.md | 1332 |
| doc-002-pedr-search | PEDR Search | docs | docs/pedr-search.md | 167 |
| doc-003-hybrid-search | Hybrid Search | docs | docs/hybrid-search.md | 483 |
| doc-004-qdrant-optimization | Qdrant Optimization | docs | docs/qdrant-optimization.md | 565 |
| doc-005-qdrant-resilience | Qdrant Resilience | docs | docs/qdrant-resilience.md | 1230 |
| doc-006-quality-gates | Quality Gates | docs | docs/quality_gates.md | 407 |
| doc-007-implementation-guide | Implementation Guide | docs | docs/implementation_guide.md | 4073 |
| doc-008-scripts-readme | Scripts README | scripts | scripts/README.md | 535 |
| doc-009-sprint-19-retrospective | Sprint 19 Retrospective | reports | cmos/reports/sprint-19/retrospective.md | 752 |
| doc-010-pedr-baseline-capture | PEDR Baseline Capture (Sprint 18) | reports | cmos/reports/sprint-18/pedr-baseline-capture.md | 912 |
| doc-011-graph-parameter-optimization | Graph Parameter Optimization (Sprint 26) | reports | cmos/reports/sprint-26/graph-parameter-optimization.md | 267 |
| doc-012-qdrant-optimization-research | Qdrant Optimization Research (Sprint 19) | reports | cmos/reports/sprint-19/qdrant-optimization-research.md | 986 |
