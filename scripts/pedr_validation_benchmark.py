#!/usr/bin/env python3
"""PEDR validation benchmark using the R27.1 baseline corpus and queries.

This script reuses the baseline corpus/query set and applies PEDR quality scoring
and governance filters to validate quality-aware ranking effects.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pedr import QualityFilters, QualityScoringService

from rag_baseline_benchmark import (  # noqa: E402
    DEFAULT_CORPUS_DIR,
    DEFAULT_QUERIES_PATH,
    bm25_scores,
    build_index,
    load_corpus,
    load_queries,
    hybrid_scores,
    ndcg_at_k,
    precision_at_k,
    rank_scores,
    recall_at_k,
    summarize_metric,
    tfidf_scores,
    tokenize,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "artifacts/benchmarks/pedr-benchmark-results.json"
DEFAULT_COMPARISON_MD = PROJECT_ROOT / "artifacts/benchmarks/comparison-analysis.md"
DEFAULT_QUALITY_METADATA_PATH = DEFAULT_CORPUS_DIR / "quality_metadata.json"
DEFAULT_RELATIONSHIPS_PATH = DEFAULT_CORPUS_DIR / "relationships.json"
DEFAULT_BASELINE_METRICS_PATH = PROJECT_ROOT / "artifacts/benchmarks/rag-baseline-metrics.json"

DEFAULT_TOP_K = 5
DEFAULT_SEMANTIC_WEIGHT = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.3


QUALITY_ASSIGNMENTS = {
    "doc-001-readme": {"status": "draft", "passed_gates": 3, "validated": False, "pii": False},
    "doc-002-pedr-search": {"status": "complete", "passed_gates": 5, "validated": True, "pii": False},
    "doc-003-hybrid-search": {"status": "complete", "passed_gates": 5, "validated": True, "pii": False},
    "doc-004-qdrant-optimization": {"status": "review", "passed_gates": 4, "validated": False, "pii": False},
    "doc-005-qdrant-resilience": {"status": "review", "passed_gates": 4, "validated": False, "pii": False},
    "doc-006-quality-gates": {"status": "in_progress", "passed_gates": 3, "validated": False, "pii": False},
    "doc-007-implementation-guide": {"status": "draft", "passed_gates": 3, "validated": False, "pii": True},
    "doc-008-scripts-readme": {"status": "draft", "passed_gates": 3, "validated": False, "pii": True},
    "doc-009-sprint-19-retrospective": {"status": "complete", "passed_gates": 5, "validated": True, "pii": False},
    "doc-010-pedr-baseline-capture": {"status": "in_progress", "passed_gates": 3, "validated": False, "pii": False},
    "doc-011-graph-parameter-optimization": {"status": "draft", "passed_gates": 3, "validated": False, "pii": False},
    "doc-012-qdrant-optimization-research": {"status": "complete", "passed_gates": 5, "validated": True, "pii": False},
}


EXPLICIT_RELATIONSHIPS = {
    "doc-002-pedr-search": ["doc-003-hybrid-search", "doc-010-pedr-baseline-capture"],
    "doc-003-hybrid-search": ["doc-002-pedr-search"],
    "doc-004-qdrant-optimization": ["doc-012-qdrant-optimization-research"],
    "doc-005-qdrant-resilience": ["doc-004-qdrant-optimization"],
    "doc-010-pedr-baseline-capture": ["doc-002-pedr-search"],
}


def build_quality_gates(passed_gates: int, validated: bool) -> Dict[str, Dict[str, Any]]:
    gates: Dict[str, Dict[str, Any]] = {}
    for index, gate in enumerate(QualityScoringService.EXPECTED_GATES):
        gates[gate] = {
            "status": "pass" if index < passed_gates else "pending",
            "validated": validated if index < passed_gates else False,
        }
    return gates


def build_quality_metadata(manifest: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for doc in manifest.get("documents", []):
        doc_id = doc["doc_id"]
        assignment = QUALITY_ASSIGNMENTS.get(doc_id, {})
        status = assignment.get("status", "draft")
        passed_gates = int(assignment.get("passed_gates", 2))
        validated = bool(assignment.get("validated", False))
        pii_flag = bool(assignment.get("pii", False))
        mission_data: Dict[str, Any] = {}
        if pii_flag:
            mission_data["tags"] = ["pii"]
            mission_data["governance"] = {"piiHandling": True}
        metadata[doc_id] = {
            "mission_id": f"MP-{doc_id}",
            "status": status,
            "quality_gates": build_quality_gates(passed_gates, validated),
            "mission_data": mission_data,
        }
    return metadata


def build_relationship_map(manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    category_map: Dict[str, List[str]] = {}
    for doc in manifest.get("documents", []):
        category_map.setdefault(doc["category"], []).append(doc["doc_id"])

    relationships: Dict[str, List[str]] = {}
    for doc in manifest.get("documents", []):
        doc_id = doc["doc_id"]
        related = [item for item in category_map.get(doc["category"], []) if item != doc_id]
        related.extend(EXPLICIT_RELATIONSHIPS.get(doc_id, []))
        deduped = []
        seen = set()
        for rel in related:
            if rel == doc_id or rel in seen:
                continue
            seen.add(rel)
            deduped.append(rel)
        relationships[doc_id] = deduped
    return relationships


def load_or_build_quality_metadata(
    path: Path,
    manifest: Dict[str, Any],
    *,
    rebuild: bool = False,
) -> Dict[str, Any]:
    if path.exists() and not rebuild:
        return json.loads(path.read_text(encoding="utf-8"))
    metadata = build_quality_metadata(manifest)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def load_or_build_relationships(
    path: Path,
    manifest: Dict[str, Any],
    *,
    rebuild: bool = False,
) -> Dict[str, List[str]]:
    if path.exists() and not rebuild:
        return json.loads(path.read_text(encoding="utf-8"))
    relationships = build_relationship_map(manifest)
    path.write_text(json.dumps(relationships, indent=2), encoding="utf-8")
    return relationships


def sign_test_p_value(positives: int, negatives: int) -> Optional[float]:
    n = positives + negatives
    if n == 0:
        return None
    k = min(positives, negatives)
    cumulative = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * cumulative)


def _quality_loader(metadata_map: Dict[str, Any]):
    def loader(document_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        return {
            str(doc_id): metadata_map[str(doc_id)]
            for doc_id in document_ids
            if str(doc_id) in metadata_map
        }

    return loader


def apply_quality_scoring(
    results: List[Dict[str, Any]],
    *,
    metadata_map: Dict[str, Any],
    filters: Optional[QualityFilters] = None,
) -> List[Dict[str, Any]]:
    service = QualityScoringService(metadata_loader=_quality_loader(metadata_map))
    scored = service.apply(results, filters=filters or QualityFilters())
    ranked = sorted(scored, key=lambda item: float(item.get("combined_score") or 0.0), reverse=True)
    return ranked


def evaluate_pedr_queries(
    *,
    index: Any,
    queries: List[Dict[str, Any]],
    top_k: int,
    semantic_weight: float,
    keyword_weight: float,
    candidate_multiplier: int,
    metadata_map: Dict[str, Any],
    relationships: Dict[str, List[str]],
    governance_filters: QualityFilters,
) -> Dict[str, Any]:
    pedr_quality_results: List[Dict[str, Any]] = []
    pedr_governance_results: List[Dict[str, Any]] = []

    quality_precisions: List[float] = []
    quality_recalls: List[float] = []
    quality_ndcg: List[float] = []
    quality_latencies: List[float] = []

    governance_precisions: List[float] = []
    governance_recalls: List[float] = []
    governance_ndcg: List[float] = []
    governance_latencies: List[float] = []

    relationship_counts: List[int] = []
    relationship_coverages: List[float] = []
    relationship_uniques: List[int] = []

    pii_flagged_total = 0
    pii_removed_total = 0
    gate_removed_total = 0

    for query in queries:
        query_text = query["query"]
        relevance = {item["doc_id"]: int(item.get("relevance", 1)) for item in query["relevance"]}
        query_tokens = tokenize(query_text)

        baseline_scores = tfidf_scores(query_tokens, index=index)
        keyword_scores = bm25_scores(query_tokens, index=index)
        combined_scores = hybrid_scores(
            baseline_scores,
            keyword_scores,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )
        candidate_k = max(top_k, top_k * max(1, candidate_multiplier))
        ranked = rank_scores(combined_scores, top_k=candidate_k)
        base_results = [
            {"document_id": doc_id, "combined_score": score, "score": score} for doc_id, score in ranked
        ]

        quality_start = time.perf_counter()
        quality_ranked = apply_quality_scoring(base_results, metadata_map=metadata_map)
        quality_latency = (time.perf_counter() - quality_start) * 1000

        governance_start = time.perf_counter()
        governance_ranked = apply_quality_scoring(
            base_results,
            metadata_map=metadata_map,
            filters=governance_filters,
        )
        governance_latency = (time.perf_counter() - governance_start) * 1000

        quality_docs = [item["document_id"] for item in quality_ranked[:top_k]]
        governance_docs = [item["document_id"] for item in governance_ranked[:top_k]]

        quality_precision = precision_at_k(relevance, quality_docs, top_k)
        quality_recall = recall_at_k(relevance, quality_docs, top_k)
        quality_ndcg_score = ndcg_at_k(relevance, quality_docs, top_k)
        governance_precision = precision_at_k(relevance, governance_docs, top_k)
        governance_recall = recall_at_k(relevance, governance_docs, top_k)
        governance_ndcg_score = ndcg_at_k(relevance, governance_docs, top_k)

        quality_precisions.append(quality_precision)
        quality_recalls.append(quality_recall)
        quality_ndcg.append(quality_ndcg_score)
        quality_latencies.append(quality_latency)

        governance_precisions.append(governance_precision)
        governance_recalls.append(governance_recall)
        governance_ndcg.append(governance_ndcg_score)
        governance_latencies.append(governance_latency)

        related_counts = []
        related_unique: List[str] = []
        for doc_id in quality_docs:
            related = relationships.get(doc_id, [])
            related_counts.append(len(related))
            related_unique.extend(related)
        relationship_counts.append(sum(related_counts))
        if quality_docs:
            relationship_coverages.append(sum(1 for count in related_counts if count > 0) / len(quality_docs))
        relationship_uniques.append(len(set(related_unique)))

        quality_entry = {
            "query_id": query["query_id"],
            "query": query_text,
            "relevance": relevance,
            "retrieved": [
                {"doc_id": item["document_id"], "score": item["combined_score"]} for item in quality_ranked[:top_k]
            ],
            "precision_at_k": quality_precision,
            "recall_at_k": quality_recall,
            "ndcg_at_k": quality_ndcg_score,
            "latency_ms": quality_latency,
            "relationship_enrichment": {
                "related_docs_total": sum(related_counts),
                "related_docs_unique": len(set(related_unique)),
                "results_with_related": sum(1 for count in related_counts if count > 0),
            },
        }

        governance_entry = {
            "query_id": query["query_id"],
            "query": query_text,
            "relevance": relevance,
            "retrieved": [
                {"doc_id": item["document_id"], "score": item["combined_score"]} for item in governance_ranked[:top_k]
            ],
            "precision_at_k": governance_precision,
            "recall_at_k": governance_recall,
            "ndcg_at_k": governance_ndcg_score,
            "latency_ms": governance_latency,
        }

        pedr_quality_results.append(quality_entry)
        pedr_governance_results.append(governance_entry)

        pii_flagged = sum(
            1
            for item in quality_ranked[:top_k]
            if metadata_map.get(item["document_id"], {}).get("mission_data", {}).get("governance", {}).get(
                "piiHandling"
            )
        )
        pii_flagged_total += pii_flagged

        pii_removed = sum(
            1
            for item in quality_ranked[:top_k]
            if item["document_id"] not in governance_docs
            and metadata_map.get(item["document_id"], {}).get("mission_data", {}).get("governance", {}).get(
                "piiHandling"
            )
        )
        pii_removed_total += pii_removed

        gate_removed_total += max(0, len(quality_docs) - len(governance_docs) - pii_removed)

    relationship_summary = {
        "avg_related_docs_per_query": sum(relationship_counts) / len(relationship_counts)
        if relationship_counts
        else 0.0,
        "avg_related_docs_unique": sum(relationship_uniques) / len(relationship_uniques)
        if relationship_uniques
        else 0.0,
        "avg_results_with_related_pct": sum(relationship_coverages) / len(relationship_coverages)
        if relationship_coverages
        else 0.0,
    }

    governance_summary = {
        "pii_flagged_in_top_k": pii_flagged_total,
        "pii_removed": pii_removed_total,
        "non_pii_removed": gate_removed_total,
        "pii_removal_rate": (pii_removed_total / pii_flagged_total) if pii_flagged_total else 0.0,
    }

    return {
        "pedr_quality": {
            "summary": {
                "precision_at_k": sum(quality_precisions) / len(quality_precisions) if quality_precisions else 0.0,
                "recall_at_k": sum(quality_recalls) / len(quality_recalls) if quality_recalls else 0.0,
                "ndcg_at_k": sum(quality_ndcg) / len(quality_ndcg) if quality_ndcg else 0.0,
                "latency_ms": summarize_metric(quality_latencies),
            },
            "queries": pedr_quality_results,
        },
        "pedr_governance": {
            "summary": {
                "precision_at_k": sum(governance_precisions) / len(governance_precisions)
                if governance_precisions
                else 0.0,
                "recall_at_k": sum(governance_recalls) / len(governance_recalls)
                if governance_recalls
                else 0.0,
                "ndcg_at_k": sum(governance_ndcg) / len(governance_ndcg) if governance_ndcg else 0.0,
                "latency_ms": summarize_metric(governance_latencies),
            },
            "queries": pedr_governance_results,
        },
        "relationship_enrichment": relationship_summary,
        "governance_filtering": governance_summary,
    }


def _extract_query_metrics(method: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    metrics: Dict[str, Dict[str, float]] = {}
    for item in method.get("queries", []):
        metrics[item["query_id"]] = {
            "precision_at_k": float(item.get("precision_at_k", 0.0)),
            "recall_at_k": float(item.get("recall_at_k", 0.0)),
            "ndcg_at_k": float(item.get("ndcg_at_k", 0.0)),
        }
    return metrics


def compare_methods(
    pedr_queries: Dict[str, Dict[str, float]],
    baseline_queries: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    deltas: Dict[str, List[float]] = {
        "precision_at_k": [],
        "recall_at_k": [],
        "ndcg_at_k": [],
    }
    wins: Dict[str, Counter] = {
        "precision_at_k": Counter(),
        "recall_at_k": Counter(),
        "ndcg_at_k": Counter(),
    }

    for query_id, pedr_metric in pedr_queries.items():
        baseline_metric = baseline_queries.get(query_id)
        if not baseline_metric:
            continue
        for key in deltas.keys():
            diff = pedr_metric.get(key, 0.0) - baseline_metric.get(key, 0.0)
            deltas[key].append(diff)
            if diff > 0:
                wins[key]["positive"] += 1
            elif diff < 0:
                wins[key]["negative"] += 1
            else:
                wins[key]["tie"] += 1

    summary: Dict[str, Any] = {}
    for key, values in deltas.items():
        positives = wins[key].get("positive", 0)
        negatives = wins[key].get("negative", 0)
        summary[key] = {
            "mean_delta": sum(values) / len(values) if values else 0.0,
            "wins": positives,
            "losses": negatives,
            "ties": wins[key].get("tie", 0),
            "sign_test_p_value": sign_test_p_value(positives, negatives),
        }
    return summary


def quality_boost_ratio(metadata_map: Dict[str, Any]) -> Dict[str, float]:
    service = QualityScoringService(metadata_loader=_quality_loader(metadata_map))
    results = [
        {"document_id": doc_id, "combined_score": 1.0}
        for doc_id in metadata_map.keys()
    ]
    scored = service.apply(results, filters=QualityFilters())
    complete_scores = [item["quality_score"] for item in scored if item.get("quality_status") == "complete"]
    draft_scores = [item["quality_score"] for item in scored if item.get("quality_status") == "draft"]
    ratio = (sum(complete_scores) / len(complete_scores)) / (sum(draft_scores) / len(draft_scores)) if draft_scores else 0.0
    return {
        "complete_avg": sum(complete_scores) / len(complete_scores) if complete_scores else 0.0,
        "draft_avg": sum(draft_scores) / len(draft_scores) if draft_scores else 0.0,
        "ratio_complete_vs_draft": ratio,
    }


def render_comparison_markdown(
    baseline_summary: Dict[str, Any],
    pedr_summary: Dict[str, Any],
    comparison: Dict[str, Any],
    quality_ratio: Dict[str, float],
    governance_summary: Dict[str, Any],
    relationship_summary: Dict[str, Any],
) -> str:
    def _format_p(value: Optional[float]) -> str:
        return f"{value:.4f}" if value is not None else "n/a"

    lines = [
        "# PEDR vs Baseline Comparison",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Baseline (Hybrid) | PEDR Quality | Delta |",
        "| --- | --- | --- | --- |",
        f"| Precision@{baseline_summary['top_k']} | {baseline_summary['precision_at_k']:.3f} | {pedr_summary['precision_at_k']:.3f} | {comparison['precision_at_k']['mean_delta']:.3f} |",
        f"| Recall@{baseline_summary['top_k']} | {baseline_summary['recall_at_k']:.3f} | {pedr_summary['recall_at_k']:.3f} | {comparison['recall_at_k']['mean_delta']:.3f} |",
        f"| nDCG@{baseline_summary['top_k']} | {baseline_summary['ndcg_at_k']:.3f} | {pedr_summary['ndcg_at_k']:.3f} | {comparison['ndcg_at_k']['mean_delta']:.3f} |",
        "",
        "## Sign Test (Per-Query Wins)",
        "",
        "| Metric | Wins | Losses | Ties | p-value |",
        "| --- | --- | --- | --- | --- |",
        f"| Precision@{baseline_summary['top_k']} | {comparison['precision_at_k']['wins']} | {comparison['precision_at_k']['losses']} | {comparison['precision_at_k']['ties']} | {_format_p(comparison['precision_at_k']['sign_test_p_value'])} |",
        f"| Recall@{baseline_summary['top_k']} | {comparison['recall_at_k']['wins']} | {comparison['recall_at_k']['losses']} | {comparison['recall_at_k']['ties']} | {_format_p(comparison['recall_at_k']['sign_test_p_value'])} |",
        f"| nDCG@{baseline_summary['top_k']} | {comparison['ndcg_at_k']['wins']} | {comparison['ndcg_at_k']['losses']} | {comparison['ndcg_at_k']['ties']} | {_format_p(comparison['ndcg_at_k']['sign_test_p_value'])} |",
        "",
        "## Quality Boost Validation",
        "",
        f"- Complete average multiplier: {quality_ratio['complete_avg']:.2f}",
        f"- Draft average multiplier: {quality_ratio['draft_avg']:.2f}",
        f"- Complete vs draft ratio: {quality_ratio['ratio_complete_vs_draft']:.2f}x",
        "",
        "## Governance Filtering",
        "",
        f"- PII flagged in top-k: {governance_summary['pii_flagged_in_top_k']}",
        f"- PII removed: {governance_summary['pii_removed']}",
        f"- Non-PII removed by gate filter: {governance_summary['non_pii_removed']}",
        f"- PII removal rate: {governance_summary['pii_removal_rate']:.2f}",
        "",
        "## Relationship Enrichment",
        "",
        f"- Avg related docs per query: {relationship_summary['avg_related_docs_per_query']:.2f}",
        f"- Avg unique related docs per query: {relationship_summary['avg_related_docs_unique']:.2f}",
        f"- Avg results with related docs: {relationship_summary['avg_results_with_related_pct']:.2f}",
        "",
    ]
    return "\n".join(lines)


def run_benchmark(
    *,
    corpus_dir: Path,
    queries_path: Path,
    output_path: Path,
    comparison_path: Path,
    baseline_metrics_path: Path,
    top_k: int,
    semantic_weight: float,
    keyword_weight: float,
    candidate_multiplier: int,
    rebuild_metadata: bool,
    rebuild_relationships: bool,
) -> Dict[str, Any]:
    manifest, documents = load_corpus(corpus_dir)
    index = build_index(documents)
    queries = load_queries(queries_path)

    metadata_map = load_or_build_quality_metadata(
        DEFAULT_QUALITY_METADATA_PATH,
        manifest,
        rebuild=rebuild_metadata,
    )
    relationships = load_or_build_relationships(
        DEFAULT_RELATIONSHIPS_PATH,
        manifest,
        rebuild=rebuild_relationships,
    )

    governance_filters = QualityFilters(min_quality_gates=3, allow_pii=False)

    pedr_results = evaluate_pedr_queries(
        index=index,
        queries=queries,
        top_k=top_k,
        semantic_weight=semantic_weight,
        keyword_weight=keyword_weight,
        candidate_multiplier=candidate_multiplier,
        metadata_map=metadata_map,
        relationships=relationships,
        governance_filters=governance_filters,
    )

    quality_ratio = quality_boost_ratio(metadata_map)

    baseline_payload = json.loads(baseline_metrics_path.read_text(encoding="utf-8"))
    baseline_method = baseline_payload["methods"]["hybrid_baseline"]
    baseline_summary = {
        "precision_at_k": baseline_method["summary"]["precision_at_k"],
        "recall_at_k": baseline_method["summary"]["recall_at_k"],
        "ndcg_at_k": baseline_method["summary"]["ndcg_at_k"],
        "top_k": baseline_payload["benchmark"]["top_k"],
    }

    pedr_quality_metrics = _extract_query_metrics(pedr_results["pedr_quality"])
    baseline_metrics = _extract_query_metrics(baseline_method)
    comparison = compare_methods(pedr_quality_metrics, baseline_metrics)

    output_payload = {
        "benchmark": {
            "name": "pedr-validation-offline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "corpus_manifest": str(corpus_dir / "corpus_manifest.json"),
            "queries_path": str(queries_path),
            "doc_count": manifest["document_count"],
            "query_count": len(queries),
            "top_k": top_k,
            "candidate_multiplier": candidate_multiplier,
        },
        "quality_metadata_path": str(DEFAULT_QUALITY_METADATA_PATH),
        "relationships_path": str(DEFAULT_RELATIONSHIPS_PATH),
        "quality_boost_analysis": quality_ratio,
        "pedr_results": pedr_results,
        "baseline_comparison": {
            "baseline_summary": baseline_summary,
            "pedr_summary": pedr_results["pedr_quality"]["summary"],
            "statistical_tests": comparison,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    comparison_text = render_comparison_markdown(
        baseline_summary=baseline_summary,
        pedr_summary=pedr_results["pedr_quality"]["summary"],
        comparison=comparison,
        quality_ratio=quality_ratio,
        governance_summary=pedr_results["governance_filtering"],
        relationship_summary=pedr_results["relationship_enrichment"],
    )
    comparison_path.write_text(comparison_text, encoding="utf-8")

    return output_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PEDR validation benchmark (offline).")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="Path to benchmark corpus directory.",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES_PATH,
        help="Path to benchmark query set.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output path for PEDR benchmark results JSON.",
    )
    parser.add_argument(
        "--comparison-md",
        type=Path,
        default=DEFAULT_COMPARISON_MD,
        help="Output path for comparison analysis markdown.",
    )
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        default=DEFAULT_BASELINE_METRICS_PATH,
        help="Baseline metrics JSON from R27.1.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Top-K results to evaluate.",
    )
    parser.add_argument(
        "--semantic-weight",
        type=float,
        default=DEFAULT_SEMANTIC_WEIGHT,
        help="Semantic weight for hybrid fusion.",
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=DEFAULT_KEYWORD_WEIGHT,
        help="Keyword weight for hybrid fusion.",
    )
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=2,
        help="Candidate pool multiplier before quality scoring.",
    )
    parser.add_argument(
        "--rebuild-metadata",
        action="store_true",
        help="Rebuild quality metadata mapping for the corpus.",
    )
    parser.add_argument(
        "--rebuild-relationships",
        action="store_true",
        help="Rebuild relationship mapping for the corpus.",
    )

    args = parser.parse_args()

    run_benchmark(
        corpus_dir=args.corpus_dir,
        queries_path=args.queries,
        output_path=args.output,
        comparison_path=args.comparison_md,
        baseline_metrics_path=args.baseline_metrics,
        top_k=args.top_k,
        semantic_weight=args.semantic_weight,
        keyword_weight=args.keyword_weight,
        candidate_multiplier=args.candidate_multiplier,
        rebuild_metadata=args.rebuild_metadata,
        rebuild_relationships=args.rebuild_relationships,
    )


if __name__ == "__main__":
    main()
