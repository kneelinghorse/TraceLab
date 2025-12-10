#!/usr/bin/env python3
"""PEDR Baseline Capture - R18.0

Captures baseline search quality metrics before PEDR enhancements.
Runs representative queries through PostgreSQL full-text search and records:
- Precision (relevance of top results)
- Quality awareness (complete vs draft content ranking)
- Latency (p50)

Usage:
    python scripts/pedr_baseline_capture.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select
from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document


# Representative queries covering different research topics
BASELINE_QUERIES = [
    # UX/Research queries
    "user research interview methodology",
    "usability testing best practices",
    "participant recruitment strategy",

    # Technical queries
    "API integration authentication",
    "database schema design patterns",
    "embedding service configuration",

    # Process/Workflow queries
    "sprint planning backlog prioritization",
    "code review quality checklist",
    "deployment pipeline CI/CD",

    # Domain-specific queries
    "mission protocol validation",
]


def keyword_search(session, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Execute PostgreSQL full-text search."""
    if not query.strip():
        return []

    ts_query = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(DocumentChunk.content_tsv, ts_query).label("score")
    stmt = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            DocumentChunk.document_id,
            Document.project_id.label("project_id"),
            Document.source_type,
            Document.name.label("document_name"),
            rank,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.content_tsv.op("@@")(ts_query))
        .order_by(rank.desc())
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    results: List[Dict[str, Any]] = []
    for row in rows:
        mapping = row._mapping
        results.append({
            "chunk_id": str(mapping["chunk_id"]),
            "content": mapping["content"],
            "document_id": str(mapping["document_id"]),
            "document_name": mapping["document_name"],
            "project_id": str(mapping["project_id"]) if mapping["project_id"] else None,
            "chunk_index": mapping["chunk_index"],
            "source_type": mapping["source_type"],
            "score": float(mapping["score"] or 0.0),
            "keyword_score": float(mapping["score"] or 0.0),
            "semantic_score": 0.0,
            "search_mode": "keyword",
        })
    return results


def run_baseline_capture() -> Dict[str, Any]:
    """Run baseline queries and capture metrics."""
    session = SessionLocal()

    results: List[Dict[str, Any]] = []
    latencies: List[float] = []

    print("=" * 60)
    print("PEDR BASELINE CAPTURE - R18.0")
    print("=" * 60)
    print(f"Running {len(BASELINE_QUERIES)} representative queries...\n")

    for i, query in enumerate(BASELINE_QUERIES, 1):
        print(f"\n[{i}/{len(BASELINE_QUERIES)}] Query: '{query}'")
        print("-" * 50)

        # Time the search
        start = time.perf_counter()
        try:
            chunks = keyword_search(session, query, limit=5)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

            print(f"  Latency: {latency_ms:.1f}ms")
            print(f"  Results: {len(chunks)} chunks")

            # Analyze top results
            query_result = {
                "query": query,
                "latency_ms": latency_ms,
                "result_count": len(chunks),
                "top_results": [],
            }

            for j, chunk in enumerate(chunks[:3], 1):
                score = chunk.get("combined_score", chunk.get("score", 0))
                semantic = chunk.get("semantic_score", 0)
                keyword = chunk.get("keyword_score", 0)
                content_preview = chunk.get("content", "")[:100].replace("\n", " ")
                doc_id = chunk.get("document_id", "unknown")
                search_mode = chunk.get("search_mode", "unknown")

                print(f"  [{j}] Score: {score:.3f} (sem:{semantic:.2f}, kw:{keyword:.2f}) - {search_mode}")
                print(f"      Preview: {content_preview}...")

                query_result["top_results"].append({
                    "rank": j,
                    "score": score,
                    "semantic_score": semantic,
                    "keyword_score": keyword,
                    "search_mode": search_mode,
                    "document_id": doc_id,
                    "document_name": chunk.get("document_name", "unknown"),
                    "content_preview": content_preview,
                })

            results.append(query_result)

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "query": query,
                "error": str(e),
                "latency_ms": None,
            })

    session.close()

    # Calculate summary statistics
    valid_latencies = [r["latency_ms"] for r in results if r.get("latency_ms")]

    summary = {
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "query_count": len(BASELINE_QUERIES),
        "successful_queries": len(valid_latencies),
        "latency_p50_ms": statistics.median(valid_latencies) if valid_latencies else None,
        "latency_p90_ms": sorted(valid_latencies)[int(len(valid_latencies) * 0.9)] if len(valid_latencies) > 1 else None,
        "latency_mean_ms": statistics.mean(valid_latencies) if valid_latencies else None,
        "avg_results_per_query": statistics.mean([r.get("result_count", 0) for r in results if r.get("result_count")]),
    }

    print("\n" + "=" * 60)
    print("BASELINE SUMMARY")
    print("=" * 60)
    print(f"Queries run: {summary['query_count']}")
    print(f"Successful: {summary['successful_queries']}")
    print(f"Latency P50: {summary['latency_p50_ms']:.1f}ms" if summary['latency_p50_ms'] else "Latency P50: N/A")
    print(f"Latency P90: {summary['latency_p90_ms']:.1f}ms" if summary['latency_p90_ms'] else "Latency P90: N/A")
    print(f"Latency Mean: {summary['latency_mean_ms']:.1f}ms" if summary['latency_mean_ms'] else "Latency Mean: N/A")
    print(f"Avg results/query: {summary['avg_results_per_query']:.1f}")

    return {
        "summary": summary,
        "results": results,
        "search_config": {
            "search_mode": "keyword (PostgreSQL full-text)",
            "top_k": 5,
            "semantic_weight": 0.0,
            "keyword_weight": 1.0,
            "note": "Baseline using keyword-only search; hybrid/semantic available in production",
        },
    }


def main() -> int:
    """Main entry point."""
    baseline = run_baseline_capture()

    # Save to telemetry
    telemetry_path = Path("cmos/telemetry/events/sprint-18-pedr-baseline.jsonl")
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    with open(telemetry_path, "a") as f:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": "pedr_baseline_capture",
            "mission_id": "R18.0",
            "data": baseline["summary"],
        }
        f.write(json.dumps(event) + "\n")
    print(f"\nTelemetry logged to: {telemetry_path}")

    # Save detailed report
    report_path = Path("cmos/reports/sprint-18/pedr-baseline-capture.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(baseline, f, indent=2, default=str)
    print(f"Detailed report saved to: {report_path}")

    # Also create a markdown summary
    md_path = Path("cmos/reports/sprint-18/pedr-baseline-capture.md")
    with open(md_path, "w") as f:
        f.write("# PEDR Baseline Capture - R18.0\n\n")
        f.write(f"**Captured**: {baseline['summary']['capture_timestamp']}\n\n")
        f.write("## Summary Metrics\n\n")
        f.write(f"- **Queries**: {baseline['summary']['query_count']}\n")
        f.write(f"- **Latency P50**: {baseline['summary']['latency_p50_ms']:.1f}ms\n" if baseline['summary']['latency_p50_ms'] else "- **Latency P50**: N/A\n")
        f.write(f"- **Latency P90**: {baseline['summary']['latency_p90_ms']:.1f}ms\n" if baseline['summary']['latency_p90_ms'] else "- **Latency P90**: N/A\n")
        f.write(f"- **Average Results**: {baseline['summary']['avg_results_per_query']:.1f} per query\n\n")
        f.write("## Search Configuration\n\n")
        f.write(f"- Mode: {baseline['search_config']['search_mode']}\n")
        f.write(f"- Top K: {baseline['search_config']['top_k']}\n")
        f.write(f"- Semantic Weight: {baseline['search_config']['semantic_weight']:.2f}\n")
        f.write(f"- Keyword Weight: {baseline['search_config']['keyword_weight']:.2f}\n\n")
        f.write("## Query Results\n\n")
        for result in baseline["results"]:
            if result.get("error"):
                f.write(f"### {result['query']}\n**ERROR**: {result['error']}\n\n")
                continue
            f.write(f"### {result['query']}\n")
            f.write(f"- Latency: {result['latency_ms']:.1f}ms\n")
            f.write(f"- Results: {result['result_count']}\n\n")
            f.write("| Rank | Score | Semantic | Keyword | Mode | Preview |\n")
            f.write("|------|-------|----------|---------|------|--------|\n")
            for top in result.get("top_results", []):
                preview = top["content_preview"][:60] + "..." if len(top["content_preview"]) > 60 else top["content_preview"]
                f.write(f"| {top['rank']} | {top['score']:.3f} | {top['semantic_score']:.2f} | {top['keyword_score']:.2f} | {top['search_mode']} | {preview} |\n")
            f.write("\n")
        f.write("## Notes\n\n")
        f.write("This baseline establishes the 'before' picture for PEDR enhancements.\n")
        f.write("Key areas to improve after B18.4:\n")
        f.write("- Precision: Are top results highly relevant?\n")
        f.write("- Quality awareness: Do complete/validated items rank higher?\n")
        f.write("- Latency: Target P50 < 500ms for interactive use\n")
    print(f"Markdown summary saved to: {md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
