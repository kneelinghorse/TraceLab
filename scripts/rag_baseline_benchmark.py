#!/usr/bin/env python3
"""RAG/hybrid baseline benchmark with offline corpus and relevance judgments.

This script builds a small, reproducible benchmark corpus from TraceLab
documentation and evaluates two baseline retrieval modes:
- semantic (TF-IDF cosine similarity)
- hybrid (TF-IDF + BM25 with min-max normalization and weighted fusion)

Outputs precision@k, recall@k, nDCG@k, and latency metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = PROJECT_ROOT / "artifacts/benchmarks/benchmark-corpus"
DEFAULT_MANIFEST_PATH = DEFAULT_CORPUS_DIR / "corpus_manifest.json"
DEFAULT_QUERIES_PATH = DEFAULT_CORPUS_DIR / "queries.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "artifacts/benchmarks/rag-baseline-metrics.json"

DEFAULT_TOP_K = 5
DEFAULT_SEMANTIC_WEIGHT = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.3

TOKEN_RE = re.compile(r"[a-z0-9]+")


SOURCE_DOCS = [
    {
        "doc_id": "doc-001-readme",
        "title": "TraceLab README",
        "category": "overview",
        "source_path": "README.md",
    },
    {
        "doc_id": "doc-002-pedr-search",
        "title": "PEDR Search",
        "category": "docs",
        "source_path": "docs/pedr-search.md",
    },
    {
        "doc_id": "doc-003-hybrid-search",
        "title": "Hybrid Search",
        "category": "docs",
        "source_path": "docs/hybrid-search.md",
    },
    {
        "doc_id": "doc-004-qdrant-optimization",
        "title": "Qdrant Optimization",
        "category": "docs",
        "source_path": "docs/qdrant-optimization.md",
    },
    {
        "doc_id": "doc-005-qdrant-resilience",
        "title": "Qdrant Resilience",
        "category": "docs",
        "source_path": "docs/qdrant-resilience.md",
    },
    {
        "doc_id": "doc-006-quality-gates",
        "title": "Quality Gates",
        "category": "docs",
        "source_path": "docs/quality_gates.md",
    },
    {
        "doc_id": "doc-007-implementation-guide",
        "title": "Implementation Guide",
        "category": "docs",
        "source_path": "docs/implementation_guide.md",
    },
    {
        "doc_id": "doc-008-scripts-readme",
        "title": "Scripts README",
        "category": "scripts",
        "source_path": "scripts/README.md",
    },
    {
        "doc_id": "doc-009-sprint-19-retrospective",
        "title": "Sprint 19 Retrospective",
        "category": "reports",
        "source_path": "cmos/reports/sprint-19/retrospective.md",
    },
    {
        "doc_id": "doc-010-pedr-baseline-capture",
        "title": "PEDR Baseline Capture (Sprint 18)",
        "category": "reports",
        "source_path": "cmos/reports/sprint-18/pedr-baseline-capture.md",
    },
    {
        "doc_id": "doc-011-graph-parameter-optimization",
        "title": "Graph Parameter Optimization (Sprint 26)",
        "category": "reports",
        "source_path": "cmos/reports/sprint-26/graph-parameter-optimization.md",
    },
    {
        "doc_id": "doc-012-qdrant-optimization-research",
        "title": "Qdrant Optimization Research (Sprint 19)",
        "category": "reports",
        "source_path": "cmos/reports/sprint-19/qdrant-optimization-research.md",
    },
    {
        "doc_id": "doc-013-docs-readme",
        "title": "Docs README",
        "category": "docs",
        "source_path": "docs/README.md",
    },
    {
        "doc_id": "doc-014-architecture-health-check",
        "title": "Architecture Health Check",
        "category": "docs",
        "source_path": "docs/architecture-health-check.md",
    },
    {
        "doc_id": "doc-015-auth-cors-guidance",
        "title": "Auth and CORS Guidance",
        "category": "docs",
        "source_path": "docs/auth_and_cors_guidance.md",
    },
    {
        "doc_id": "doc-016-authentication",
        "title": "Authentication",
        "category": "docs",
        "source_path": "docs/authentication.md",
    },
    {
        "doc_id": "doc-017-best-practices",
        "title": "Best Practices",
        "category": "docs",
        "source_path": "docs/best-practices.md",
    },
    {
        "doc_id": "doc-018-caching-strategy",
        "title": "Caching Strategy",
        "category": "docs",
        "source_path": "docs/caching-strategy.md",
    },
    {
        "doc_id": "doc-019-cli-architecture",
        "title": "CLI Architecture",
        "category": "docs",
        "source_path": "docs/cli_architecture.md",
    },
    {
        "doc_id": "doc-020-cli-usage",
        "title": "CLI Usage",
        "category": "docs",
        "source_path": "docs/cli_usage.md",
    },
    {
        "doc_id": "doc-021-console-guide",
        "title": "Console Guide",
        "category": "docs",
        "source_path": "docs/console-guide.md",
    },
    {
        "doc_id": "doc-022-correction-loop",
        "title": "Correction Loop",
        "category": "docs",
        "source_path": "docs/correction-loop.md",
    },
    {
        "doc_id": "doc-023-data-protection-audit",
        "title": "Data Protection Audit",
        "category": "docs",
        "source_path": "docs/data-protection-audit.md",
    },
    {
        "doc_id": "doc-024-database-optimization",
        "title": "Database Optimization",
        "category": "docs",
        "source_path": "docs/database-optimization.md",
    },
    {
        "doc_id": "doc-025-deepsearch-common-errors",
        "title": "DeepSearch Common Errors",
        "category": "docs",
        "source_path": "docs/deepsearch-common-errors.md",
    },
    {
        "doc_id": "doc-026-deepsearch-integration-testing",
        "title": "DeepSearch Integration Testing",
        "category": "docs",
        "source_path": "docs/deepsearch-integration-testing.md",
    },
    {
        "doc_id": "doc-027-deepsearch-integration",
        "title": "DeepSearch Integration",
        "category": "docs",
        "source_path": "docs/deepsearch-integration.md",
    },
    {
        "doc_id": "doc-028-deployment",
        "title": "Deployment",
        "category": "docs",
        "source_path": "docs/deployment.md",
    },
    {
        "doc_id": "doc-029-document-processing",
        "title": "Document Processing",
        "category": "docs",
        "source_path": "docs/document-processing.md",
    },
    {
        "doc_id": "doc-030-environment-setup",
        "title": "Environment Setup",
        "category": "docs",
        "source_path": "docs/environment-setup.md",
    },
    {
        "doc_id": "doc-031-frontend-architecture",
        "title": "Frontend Architecture",
        "category": "docs",
        "source_path": "docs/frontend_architecture.md",
    },
    {
        "doc_id": "doc-032-frontend-deployment-decisions",
        "title": "Frontend Deployment Decisions",
        "category": "docs",
        "source_path": "docs/frontend_deployment_decisions.md",
    },
    {
        "doc_id": "doc-033-getting-started",
        "title": "Getting Started",
        "category": "docs",
        "source_path": "docs/getting-started.md",
    },
    {
        "doc_id": "doc-034-ingestion-onboarding-runbook",
        "title": "Ingestion Onboarding Runbook",
        "category": "docs",
        "source_path": "docs/ingestion_onboarding_runbook.md",
    },
    {
        "doc_id": "doc-035-ingestion-pipeline-developer-guide",
        "title": "Ingestion Pipeline Developer Guide",
        "category": "docs",
        "source_path": "docs/ingestion_pipeline_developer_guide.md",
    },
    {
        "doc_id": "doc-036-local-development",
        "title": "Local Development",
        "category": "docs",
        "source_path": "docs/local-development.md",
    },
    {
        "doc_id": "doc-037-mcp-tools",
        "title": "MCP Tools",
        "category": "docs",
        "source_path": "docs/mcp-tools.md",
    },
    {
        "doc_id": "doc-038-mission-protocol-tutorial",
        "title": "Mission Protocol Tutorial",
        "category": "docs",
        "source_path": "docs/mission-protocol-tutorial.md",
    },
    {
        "doc_id": "doc-039-mission-protocol-api",
        "title": "Mission Protocol API",
        "category": "docs",
        "source_path": "docs/mission_protocol_api.md",
    },
    {
        "doc_id": "doc-040-mission-protocol-validation",
        "title": "Mission Protocol Validation",
        "category": "docs",
        "source_path": "docs/mission_protocol_validation.md",
    },
    {
        "doc_id": "doc-041-monitoring-dashboard",
        "title": "Monitoring Dashboard",
        "category": "docs",
        "source_path": "docs/monitoring-dashboard.md",
    },
    {
        "doc_id": "doc-042-pedr-sync",
        "title": "PEDR Sync",
        "category": "docs",
        "source_path": "docs/pedr-sync.md",
    },
    {
        "doc_id": "doc-043-preflight-queries",
        "title": "Preflight Queries",
        "category": "docs",
        "source_path": "docs/preflight-queries.md",
    },
    {
        "doc_id": "doc-044-qdrant-railway-setup",
        "title": "Qdrant Railway Setup",
        "category": "docs",
        "source_path": "docs/qdrant-railway-setup.md",
    },
    {
        "doc_id": "doc-045-quality-aware-search",
        "title": "Quality Aware Search",
        "category": "docs",
        "source_path": "docs/quality-aware-search.md",
    },
    {
        "doc_id": "doc-046-quality-automation",
        "title": "Quality Automation",
        "category": "docs",
        "source_path": "docs/quality_automation.md",
    },
    {
        "doc_id": "doc-047-relationship-api",
        "title": "Relationship API",
        "category": "docs",
        "source_path": "docs/relationship-api.md",
    },
    {
        "doc_id": "doc-048-report-metadata-analysis",
        "title": "Report Metadata Analysis",
        "category": "docs",
        "source_path": "docs/report-metadata-analysis.md",
    },
    {
        "doc_id": "doc-049-report-export",
        "title": "Report Export",
        "category": "docs",
        "source_path": "docs/report_export.md",
    },
    {
        "doc_id": "doc-050-saved-searches",
        "title": "Saved Searches",
        "category": "docs",
        "source_path": "docs/saved-searches.md",
    },
    {
        "doc_id": "doc-051-schema-evolution-guide",
        "title": "Schema Evolution Guide",
        "category": "docs",
        "source_path": "docs/schema-evolution-guide.md",
    },
    {
        "doc_id": "doc-052-schema-package",
        "title": "Schema Package",
        "category": "docs",
        "source_path": "docs/schema-package.md",
    },
    {
        "doc_id": "doc-053-schema-versioning",
        "title": "Schema Versioning",
        "category": "docs",
        "source_path": "docs/schema-versioning.md",
    },
    {
        "doc_id": "doc-054-search-filters",
        "title": "Search Filters",
        "category": "docs",
        "source_path": "docs/search-filters.md",
    },
    {
        "doc_id": "doc-055-search-history",
        "title": "Search History",
        "category": "docs",
        "source_path": "docs/search-history.md",
    },
    {
        "doc_id": "doc-056-telemetry-automation",
        "title": "Telemetry Automation",
        "category": "docs",
        "source_path": "docs/telemetry-automation.md",
    },
    {
        "doc_id": "doc-057-workflows",
        "title": "Workflows",
        "category": "docs",
        "source_path": "docs/workflows.md",
    },
]


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    text: str
    tokens: List[str]
    term_freq: Counter
    length: int


@dataclass(frozen=True)
class CorpusIndex:
    documents: List[CorpusDocument]
    doc_freqs: Counter
    avg_doc_len: float
    doc_count: int
    tfidf_idf: Dict[str, float]
    tfidf_doc_norms: Dict[str, float]


def sanitize_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def build_documents_from_texts(texts: Dict[str, str]) -> List[CorpusDocument]:
    documents: List[CorpusDocument] = []
    for doc_id, text in texts.items():
        tokens = tokenize(text)
        term_freq = Counter(tokens)
        documents.append(
            CorpusDocument(
                doc_id=doc_id,
                text=text,
                tokens=tokens,
                term_freq=term_freq,
                length=sum(term_freq.values()),
            )
        )
    return documents


def build_corpus(
    corpus_dir: Path,
    *,
    sources: List[Dict[str, str]],
    overwrite: bool = False,
) -> Dict[str, Any]:
    documents_dir = corpus_dir / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)

    manifest_docs: List[Dict[str, Any]] = []
    for source in sources:
        source_path = PROJECT_ROOT / source["source_path"]
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source document: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8", errors="ignore")
        sanitized = sanitize_ascii(raw_text)
        text_path = documents_dir / f"{source['doc_id']}.txt"
        if text_path.exists() and not overwrite:
            raise FileExistsError(f"{text_path} exists. Use --overwrite to replace.")

        text_path.write_text(sanitized, encoding="utf-8")
        sha256 = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
        word_count = len(tokenize(sanitized))

        manifest_docs.append(
            {
                "doc_id": source["doc_id"],
                "title": source["title"],
                "category": source["category"],
                "source_path": source["source_path"],
                "text_path": f"documents/{source['doc_id']}.txt",
                "word_count": word_count,
                "sha256": sha256,
            }
        )

    manifest = {
        "corpus_id": "tracelab-rag-baseline-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(manifest_docs),
        "documents": manifest_docs,
    }
    manifest_path = corpus_dir / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_corpus(corpus_dir: Path) -> Tuple[Dict[str, Any], List[CorpusDocument]]:
    manifest_path = corpus_dir / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    texts: Dict[str, str] = {}
    for doc in manifest["documents"]:
        text_path = corpus_dir / doc["text_path"]
        texts[doc["doc_id"]] = text_path.read_text(encoding="utf-8")
    documents = build_documents_from_texts(texts)
    return manifest, documents


def build_index(documents: List[CorpusDocument]) -> CorpusIndex:
    doc_freqs: Counter = Counter()
    for doc in documents:
        for term in doc.term_freq.keys():
            doc_freqs[term] += 1

    doc_count = len(documents)
    avg_doc_len = sum(doc.length for doc in documents) / doc_count if doc_count else 0.0

    tfidf_idf = {
        term: math.log((1 + doc_count) / (1 + df)) + 1 for term, df in doc_freqs.items()
    }
    tfidf_doc_norms = _compute_tfidf_doc_norms(documents, tfidf_idf)

    return CorpusIndex(
        documents=documents,
        doc_freqs=doc_freqs,
        avg_doc_len=avg_doc_len,
        doc_count=doc_count,
        tfidf_idf=tfidf_idf,
        tfidf_doc_norms=tfidf_doc_norms,
    )


def _compute_tfidf_doc_norms(
    documents: List[CorpusDocument],
    idf: Dict[str, float],
) -> Dict[str, float]:
    norms: Dict[str, float] = {}
    for doc in documents:
        norm_sq = 0.0
        for term, count in doc.term_freq.items():
            tf = count / doc.length if doc.length else 0.0
            weight = tf * idf.get(term, 0.0)
            norm_sq += weight * weight
        norms[doc.doc_id] = math.sqrt(norm_sq) or 1.0
    return norms


def bm25_scores(
    query_tokens: Iterable[str],
    *,
    index: CorpusIndex,
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    query_terms = list(query_tokens)
    for doc in index.documents:
        score = 0.0
        doc_len = doc.length or 1
        for term in query_terms:
            if term not in doc.term_freq:
                continue
            df = index.doc_freqs.get(term, 0)
            idf = math.log((index.doc_count - df + 0.5) / (df + 0.5) + 1)
            tf = doc.term_freq[term]
            denom = tf + k1 * (1 - b + b * doc_len / index.avg_doc_len)
            score += idf * (tf * (k1 + 1) / denom)
        scores[doc.doc_id] = score
    return scores


def tfidf_scores(
    query_tokens: Iterable[str],
    *,
    index: CorpusIndex,
) -> Dict[str, float]:
    query_counts = Counter(query_tokens)
    query_len = sum(query_counts.values()) or 1
    query_weights: Dict[str, float] = {}
    for term, count in query_counts.items():
        tf = count / query_len
        query_weights[term] = tf * index.tfidf_idf.get(term, 0.0)

    query_norm_sq = sum(weight * weight for weight in query_weights.values())
    query_norm = math.sqrt(query_norm_sq) or 1.0

    scores: Dict[str, float] = {}
    for doc in index.documents:
        dot = 0.0
        for term, q_weight in query_weights.items():
            if term not in doc.term_freq:
                continue
            tf = doc.term_freq[term] / doc.length if doc.length else 0.0
            d_weight = tf * index.tfidf_idf.get(term, 0.0)
            dot += q_weight * d_weight
        scores[doc.doc_id] = dot / (index.tfidf_doc_norms[doc.doc_id] * query_norm)
    return scores


def min_max_normalize(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    normalized: Dict[str, float] = {}
    for doc_id, score in scores.items():
        if span <= 0:
            normalized[doc_id] = 1.0 if score > 0 or score == maximum else 0.0
        else:
            normalized[doc_id] = (score - minimum) / span
    return normalized


def hybrid_scores(
    semantic_scores: Dict[str, float],
    keyword_scores: Dict[str, float],
    *,
    semantic_weight: float,
    keyword_weight: float,
) -> Dict[str, float]:
    semantic_norm = min_max_normalize(semantic_scores)
    keyword_norm = min_max_normalize(keyword_scores)
    combined: Dict[str, float] = {}
    for doc_id in set(semantic_norm) | set(keyword_norm):
        combined[doc_id] = (
            semantic_norm.get(doc_id, 0.0) * semantic_weight
            + keyword_norm.get(doc_id, 0.0) * keyword_weight
        )
    return combined


def rank_scores(scores: Dict[str, float], *, top_k: int) -> List[Tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]


def precision_at_k(relevant: Dict[str, int], retrieved: List[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for doc_id in retrieved[:k] if doc_id in relevant)
    return hits / k


def recall_at_k(relevant: Dict[str, int], retrieved: List[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for doc_id in retrieved[:k] if doc_id in relevant)
    return hits / len(relevant)


def ndcg_at_k(relevant: Dict[str, int], retrieved: List[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0

    def _dcg(items: List[str]) -> float:
        score = 0.0
        for idx, doc_id in enumerate(items[:k], start=1):
            rel = relevant.get(doc_id, 0)
            if rel:
                score += rel / math.log2(idx + 1)
        return score

    dcg = _dcg(retrieved)
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = 0.0
    for idx, rel in enumerate(ideal, start=1):
        idcg += rel / math.log2(idx + 1)
    return dcg / idcg if idcg > 0 else 0.0


def summarize_metric(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    sorted_values = sorted(values)
    count = len(sorted_values)
    mean = sum(sorted_values) / count
    p50 = sorted_values[int(count * 0.5)]
    p95 = sorted_values[int(count * 0.95)] if count > 1 else sorted_values[0]
    return {"mean": mean, "p50": p50, "p95": p95}


def evaluate_queries(
    *,
    index: CorpusIndex,
    queries: List[Dict[str, Any]],
    top_k: int,
    semantic_weight: float,
    keyword_weight: float,
) -> Dict[str, Any]:
    semantic_results: List[Dict[str, Any]] = []
    hybrid_results: List[Dict[str, Any]] = []
    semantic_metrics: List[float] = []
    hybrid_metrics: List[float] = []
    semantic_recalls: List[float] = []
    hybrid_recalls: List[float] = []
    semantic_ndcg: List[float] = []
    hybrid_ndcg: List[float] = []
    semantic_latencies: List[float] = []
    hybrid_latencies: List[float] = []

    for query in queries:
        query_text = query["query"]
        relevance = {
            item["doc_id"]: int(item.get("relevance", 1)) for item in query["relevance"]
        }
        query_tokens = tokenize(query_text)

        semantic_start = time.perf_counter()
        semantic_scores = tfidf_scores(query_tokens, index=index)
        semantic_ranked = rank_scores(semantic_scores, top_k=top_k)
        semantic_latency = (time.perf_counter() - semantic_start) * 1000

        hybrid_start = time.perf_counter()
        hybrid_semantic = tfidf_scores(query_tokens, index=index)
        keyword_scores = bm25_scores(query_tokens, index=index)
        combined_scores = hybrid_scores(
            hybrid_semantic,
            keyword_scores,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )
        hybrid_ranked = rank_scores(combined_scores, top_k=top_k)
        hybrid_latency = (time.perf_counter() - hybrid_start) * 1000

        semantic_docs = [doc_id for doc_id, _ in semantic_ranked]
        hybrid_docs = [doc_id for doc_id, _ in hybrid_ranked]

        semantic_precision = precision_at_k(relevance, semantic_docs, top_k)
        semantic_recall = recall_at_k(relevance, semantic_docs, top_k)
        semantic_ndcg_score = ndcg_at_k(relevance, semantic_docs, top_k)

        hybrid_precision = precision_at_k(relevance, hybrid_docs, top_k)
        hybrid_recall = recall_at_k(relevance, hybrid_docs, top_k)
        hybrid_ndcg_score = ndcg_at_k(relevance, hybrid_docs, top_k)

        semantic_metrics.append(semantic_precision)
        hybrid_metrics.append(hybrid_precision)
        semantic_recalls.append(semantic_recall)
        hybrid_recalls.append(hybrid_recall)
        semantic_ndcg.append(semantic_ndcg_score)
        hybrid_ndcg.append(hybrid_ndcg_score)
        semantic_latencies.append(semantic_latency)
        hybrid_latencies.append(hybrid_latency)

        semantic_results.append(
            {
                "query_id": query["query_id"],
                "query": query_text,
                "relevance": relevance,
                "retrieved": [
                    {"doc_id": doc_id, "score": score}
                    for doc_id, score in semantic_ranked
                ],
                "precision_at_k": semantic_precision,
                "recall_at_k": semantic_recall,
                "ndcg_at_k": semantic_ndcg_score,
                "latency_ms": semantic_latency,
            }
        )
        hybrid_results.append(
            {
                "query_id": query["query_id"],
                "query": query_text,
                "relevance": relevance,
                "retrieved": [
                    {"doc_id": doc_id, "score": score}
                    for doc_id, score in hybrid_ranked
                ],
                "precision_at_k": hybrid_precision,
                "recall_at_k": hybrid_recall,
                "ndcg_at_k": hybrid_ndcg_score,
                "latency_ms": hybrid_latency,
            }
        )

    return {
        "rag_semantic": {
            "summary": {
                "precision_at_k": sum(semantic_metrics) / len(semantic_metrics)
                if semantic_metrics
                else 0.0,
                "recall_at_k": sum(semantic_recalls) / len(semantic_recalls)
                if semantic_recalls
                else 0.0,
                "ndcg_at_k": sum(semantic_ndcg) / len(semantic_ndcg)
                if semantic_ndcg
                else 0.0,
                "latency_ms": summarize_metric(semantic_latencies),
            },
            "queries": semantic_results,
        },
        "hybrid_baseline": {
            "summary": {
                "precision_at_k": sum(hybrid_metrics) / len(hybrid_metrics)
                if hybrid_metrics
                else 0.0,
                "recall_at_k": sum(hybrid_recalls) / len(hybrid_recalls)
                if hybrid_recalls
                else 0.0,
                "ndcg_at_k": sum(hybrid_ndcg) / len(hybrid_ndcg)
                if hybrid_ndcg
                else 0.0,
                "latency_ms": summarize_metric(hybrid_latencies),
            },
            "queries": hybrid_results,
        },
    }


def load_queries(queries_path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    return payload["queries"]


def build_queries(
    *,
    sources: List[Dict[str, str]],
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    queries = []
    for index, source in enumerate(sources, start=1):
        queries.append(
            {
                "query_id": f"Q{index:02d}",
                "query": f"What does {source['title']} cover?",
                "relevance": [{"doc_id": source["doc_id"], "relevance": 2}],
            }
        )
    return {"version": "1.0", "top_k": top_k, "queries": queries}


def write_queries(
    queries_path: Path,
    *,
    sources: List[Dict[str, str]],
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    payload = build_queries(sources=sources, top_k=top_k)
    queries_path.parent.mkdir(parents=True, exist_ok=True)
    queries_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def run_benchmark(
    *,
    corpus_dir: Path,
    queries_path: Path,
    output_path: Path,
    top_k: int,
    semantic_weight: float,
    keyword_weight: float,
) -> Dict[str, Any]:
    manifest, documents = load_corpus(corpus_dir)
    index = build_index(documents)
    queries = load_queries(queries_path)

    results = evaluate_queries(
        index=index,
        queries=queries,
        top_k=top_k,
        semantic_weight=semantic_weight,
        keyword_weight=keyword_weight,
    )

    payload = {
        "benchmark": {
            "name": "rag-hybrid-baseline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "corpus_manifest": str(corpus_dir / "corpus_manifest.json"),
            "queries_path": str(queries_path),
            "doc_count": manifest["document_count"],
            "query_count": len(queries),
            "top_k": top_k,
        },
        "methods": {
            "rag_semantic": {
                "description": "TF-IDF cosine similarity (semantic-only baseline).",
                "summary": results["rag_semantic"]["summary"],
                "queries": results["rag_semantic"]["queries"],
            },
            "hybrid_baseline": {
                "description": "Min-max normalized TF-IDF + BM25 fusion (weights aligned to hybrid_search defaults).",
                "config": {
                    "semantic_weight": semantic_weight,
                    "keyword_weight": keyword_weight,
                },
                "summary": results["hybrid_baseline"]["summary"],
                "queries": results["hybrid_baseline"]["queries"],
            },
        },
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG/hybrid baseline benchmark.")
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
        help="Output path for benchmark metrics JSON.",
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
        help="Weight for semantic scores in hybrid fusion.",
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=DEFAULT_KEYWORD_WEIGHT,
        help="Weight for keyword scores in hybrid fusion.",
    )
    parser.add_argument(
        "--build-corpus",
        action="store_true",
        help="Build corpus manifest and document snapshots.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing corpus documents if present.",
    )

    args = parser.parse_args()

    if args.build_corpus:
        build_corpus(
            args.corpus_dir,
            sources=SOURCE_DOCS,
            overwrite=args.overwrite,
        )

    run_benchmark(
        corpus_dir=args.corpus_dir,
        queries_path=args.queries,
        output_path=args.output,
        top_k=args.top_k,
        semantic_weight=args.semantic_weight,
        keyword_weight=args.keyword_weight,
    )


if __name__ == "__main__":
    main()
