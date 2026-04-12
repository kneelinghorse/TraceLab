#!/usr/bin/env python3
"""Capture PEDR graph telemetry against production search history queries.

This script samples recent search history entries, runs them through the PEDR
orchestrator with graph telemetry enabled, and writes events to a JSONL file
for tuning analysis.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.search_history import SearchHistory
from app.services.pedr.pragmatic import QueryIntent, get_pragmatic_service
from app.services.pedr.search_orchestrator import create_pedr_orchestrator

DEFAULT_OUTPUT = Path("cmos/telemetry/events/graph-tuning-baseline.jsonl")


@dataclass(frozen=True)
class QuerySpec:
    query: str
    filters: Dict[str, Any]
    search_mode: Optional[str] = None


def normalize_query(query: str) -> str:
    return " ".join(query.split()).strip()


def _dedupe_key(spec: QuerySpec) -> tuple:
    filters = spec.filters or {}
    return (
        normalize_query(spec.query).lower(),
        filters.get("project_id"),
        filters.get("document_id"),
        filters.get("source_type"),
    )


def dedupe_specs(specs: Iterable[QuerySpec]) -> List[QuerySpec]:
    seen = set()
    output: List[QuerySpec] = []
    for spec in specs:
        key = _dedupe_key(spec)
        if key in seen:
            continue
        seen.add(key)
        output.append(spec)
    return output


def filters_to_search_params(filters: Mapping[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if not filters:
        return params

    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    params["project_id"] = filters.get("project_id")
    params["document_id"] = filters.get("document_id")
    params["source_type"] = filters.get("source_type")
    params["document_types"] = filters.get("document_types") or None
    params["source_types"] = filters.get("source_types") or None
    params["date_from"] = _parse_date(filters.get("date_from"))
    params["date_to"] = _parse_date(filters.get("date_to"))
    params["tags"] = filters.get("tags") or None
    params["min_quality_gates"] = filters.get("min_quality_gates")
    params["status_filters"] = filters.get("status") or None
    params["allow_pii"] = filters.get("allow_pii")
    params["element_type"] = filters.get("element_type")
    params["element_types"] = filters.get("element_types") or None
    params["auto_detect_type"] = filters.get("auto_detect_type")
    params["type_boost_enabled"] = filters.get("type_boost_enabled")
    return {k: v for k, v in params.items() if v is not None}


def load_queries_from_file(path: Path) -> List[QuerySpec]:
    specs: List[QuerySpec] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        specs.append(QuerySpec(query=raw, filters={}))
    return specs


def load_queries_from_history(
    *,
    history_limit: int,
    lookback_days: int,
    search_modes: Optional[Sequence[str]],
) -> List[QuerySpec]:
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    session = SessionLocal()
    try:
        query = session.query(SearchHistory).filter(SearchHistory.created_at >= cutoff)
        if search_modes:
            normalized = [mode.strip().lower() for mode in search_modes if mode.strip()]
            if normalized:
                query = query.filter(SearchHistory.search_mode.in_(normalized))
        rows = (
            query.order_by(SearchHistory.created_at.desc())
            .limit(max(1, history_limit))
            .all()
        )
        specs: List[QuerySpec] = []
        for row in rows:
            if not row.query_text:
                continue
            specs.append(
                QuerySpec(
                    query=row.query_text,
                    filters=dict(row.filters or {}),
                    search_mode=row.search_mode,
                )
            )
        return specs
    finally:
        session.close()


def bucket_specs_by_intent(
    specs: Sequence[QuerySpec],
) -> Dict[QueryIntent, List[QuerySpec]]:
    pragmatic = get_pragmatic_service()
    buckets: Dict[QueryIntent, List[QuerySpec]] = {intent: [] for intent in QueryIntent}
    for spec in specs:
        intent = pragmatic.classify_intent(spec.query).intent
        buckets[intent].append(spec)
    return buckets


def select_diverse_queries(
    specs: Sequence[QuerySpec],
    *,
    limit: int,
    seed: int,
) -> List[QuerySpec]:
    if limit <= 0:
        return []
    if len(specs) <= limit:
        return list(specs)

    buckets = bucket_specs_by_intent(specs)
    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    intents = [intent for intent in QueryIntent if buckets.get(intent)]
    selected: List[QuerySpec] = []
    while intents and len(selected) < limit:
        for intent in list(intents):
            bucket = buckets.get(intent, [])
            if bucket:
                selected.append(bucket.pop(0))
            if not bucket:
                intents.remove(intent)
            if len(selected) >= limit:
                break

    if len(selected) < limit:
        remaining = [
            spec
            for bucket in buckets.values()
            for spec in bucket
            if spec not in selected
        ]
        rng.shuffle(remaining)
        selected.extend(remaining[: max(0, limit - len(selected))])

    return selected[:limit]


def run_capture(
    specs: Sequence[QuerySpec],
    *,
    output_path: Path,
    top_k: int,
    graph_depth: Optional[int],
    graph_decay: Optional[float],
    graph_weight: Optional[float],
    graph_edge_types: Optional[List[str]],
    graph_top_k_seeds: Optional[int],
    disable_cache: bool,
    verbose: bool,
) -> Dict[str, Any]:
    if disable_cache:
        settings.pedr_cache_enabled = False

    orchestrator = create_pedr_orchestrator()
    orchestrator.telemetry_enabled = True
    orchestrator.telemetry_path = output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    success = 0
    failed: List[Dict[str, str]] = []

    for idx, spec in enumerate(specs, start=1):
        query_text = normalize_query(spec.query)
        if verbose:
            print(f"[{idx}/{len(specs)}] {query_text[:60]}")
        params = filters_to_search_params(spec.filters)
        params.update(
            {
                "top_k": top_k,
                "enable_graph": True,
            }
        )
        if graph_depth is not None:
            params["graph_depth"] = graph_depth
        if graph_decay is not None:
            params["graph_decay"] = graph_decay
        if graph_weight is not None:
            params["graph_weight"] = graph_weight
        if graph_edge_types is not None:
            params["graph_edge_types"] = graph_edge_types
        if graph_top_k_seeds is not None:
            params["graph_top_k_seeds"] = graph_top_k_seeds

        try:
            orchestrator.search(query=query_text, **params)
            success += 1
        except Exception as exc:  # pragma: no cover - depends on live data
            failed.append({"query": query_text, "error": str(exc)})

    return {
        "requested": len(specs),
        "succeeded": success,
        "failed": len(failed),
        "errors": failed,
    }


def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture graph telemetry baseline from production search queries."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"JSONL output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of queries to run after sampling",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=2000,
        help="Max search history rows to sample from",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="How many days of search history to consider",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=6,
        help="Minimum query length to include",
    )
    parser.add_argument(
        "--search-modes",
        type=str,
        default=None,
        help="Comma-separated search modes to include (semantic, keyword, hybrid)",
    )
    parser.add_argument(
        "--queries-file",
        type=Path,
        default=None,
        help="Load queries from a newline-delimited file",
    )
    parser.add_argument(
        "--queries",
        type=str,
        default=None,
        help="Comma-separated query list (overrides history)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=17,
        help="Random seed for sampling",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to output file instead of starting fresh",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable de-duplication of queries",
    )
    parser.add_argument(
        "--keep-cache",
        action="store_true",
        help="Keep PEDR cache enabled (default disables cache)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top-K results per query",
    )
    parser.add_argument(
        "--graph-depth",
        type=int,
        default=None,
        help="Override graph traversal depth",
    )
    parser.add_argument(
        "--graph-decay",
        type=float,
        default=None,
        help="Override graph decay factor",
    )
    parser.add_argument(
        "--graph-weight",
        type=float,
        default=None,
        help="Override graph weight in fusion",
    )
    parser.add_argument(
        "--graph-edge-types",
        type=str,
        default=None,
        help="Comma-separated graph edge types to include",
    )
    parser.add_argument(
        "--graph-top-k-seeds",
        type=int,
        default=None,
        help="Override number of retrieval seeds used for graph expansion",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-query output",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.queries:
        raw_queries = [q.strip() for q in args.queries.split(",") if q.strip()]
        specs = [QuerySpec(query=q, filters={}) for q in raw_queries]
    elif args.queries_file:
        specs = load_queries_from_file(args.queries_file)
    else:
        specs = load_queries_from_history(
            history_limit=args.history_limit,
            lookback_days=args.lookback_days,
            search_modes=_split_csv(args.search_modes),
        )

    filtered = []
    for spec in specs:
        query_text = normalize_query(spec.query)
        if len(query_text) < args.min_length:
            continue
        filtered.append(
            QuerySpec(
                query=query_text, filters=spec.filters, search_mode=spec.search_mode
            )
        )

    if not args.no_dedupe:
        filtered = dedupe_specs(filtered)

    if not filtered:
        print("No queries found to run.", file=sys.stderr)
        return 1

    selected = select_diverse_queries(filtered, limit=args.limit, seed=args.seed)

    if not args.append and args.output.exists():
        args.output.unlink()

    summary = run_capture(
        selected,
        output_path=args.output,
        top_k=args.top_k,
        graph_depth=args.graph_depth,
        graph_decay=args.graph_decay,
        graph_weight=args.graph_weight,
        graph_edge_types=_split_csv(args.graph_edge_types),
        graph_top_k_seeds=args.graph_top_k_seeds,
        disable_cache=not args.keep_cache,
        verbose=not args.quiet,
    )

    print(
        f"Graph telemetry capture complete: requested={summary['requested']}, "
        f"succeeded={summary['succeeded']}, failed={summary['failed']}"
    )
    if summary["failed"]:
        print("Failed queries (first 5):")
        for failure in summary["errors"][:5]:
            print(f"- {failure['query']}: {failure['error']}")
    print(f"Telemetry output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
