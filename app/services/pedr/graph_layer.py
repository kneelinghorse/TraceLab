"""Graph layer service for PEDR L6 graph search."""
from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import DocumentChunk, GraphEdge
from app.services.pedr.fusion import LayerResult
from app.services.pedr.score_utils import summarize_scores
from app.services.pedr.semantic_protocol import URN, URNGenerator


@dataclass(frozen=True)
class GraphLayerConfig:
    """Configuration for graph layer traversal and scoring."""

    max_depth: int = 1
    decay_factor: float = 0.7
    allowed_edge_types: Optional[Tuple[str, ...]] = None
    max_candidates: int = 100


@dataclass(frozen=True)
class EdgeRecord:
    """Lightweight edge payload for traversal."""

    to_urn: str
    edge_type: str


@dataclass
class CandidateInfo:
    """Candidate metadata tracked during traversal."""

    score: float
    depth: int
    seed_urn: str
    edge_type: Optional[str]


class URNParser:
    """URN parsing helpers for graph traversal."""

    _CHUNK_MARKER = "-chunk-"

    @staticmethod
    def parse_chunk_urn(urn: str) -> Optional[Tuple[str, int]]:
        """Parse a chunk URN into (document_id, chunk_index)."""
        parsed = URN.parse(urn)
        if not parsed or parsed.entity_type != "chunk":
            return None
        entity_id = parsed.entity_id
        if URNParser._CHUNK_MARKER not in entity_id:
            return None
        document_id, chunk_index = entity_id.rsplit(URNParser._CHUNK_MARKER, 1)
        if not document_id:
            return None
        try:
            index_value = int(chunk_index)
        except ValueError:
            return None
        return document_id, index_value


class GraphLayerService:
    """Service for graph traversal and scoring for PEDR L6 layer."""

    LAYER_NAME = "graph"
    PREFETCH_BATCH_SIZE = 200

    def __init__(
        self,
        *,
        session: Optional[Session] = None,
        session_factory: Optional[Callable[[], Session]] = None,
    ) -> None:
        if session and session_factory:
            raise ValueError("Provide either session or session_factory, not both.")
        self._session = session
        self._session_factory = session_factory or SessionLocal

    @contextmanager
    def _session_scope(self) -> Iterable[Session]:
        if self._session is not None:
            yield self._session
            return
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def search(
        self,
        seeds: List[str],
        config: Optional[GraphLayerConfig] = None,
    ) -> LayerResult:
        """Run graph expansion from explicit URN seeds."""
        config = config or GraphLayerConfig()
        seed_list = _dedupe_preserve_order(seeds)
        if not seed_list or config.max_depth <= 0 or config.max_candidates <= 0:
            return LayerResult(layer_name=self.LAYER_NAME, results=[])

        seed_scores = {seed: 1.0 for seed in seed_list}

        start = time.perf_counter()
        with self._session_scope() as session:
            results, metadata = self._bfs(
                session=session,
                seeds=seed_list,
                seed_scores=seed_scores,
                config=config,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return LayerResult(
            layer_name=self.LAYER_NAME,
            results=results,
            latency_ms=round(elapsed_ms, 2),
            metadata=metadata,
        )

    def expand_from_results(
        self,
        results: List[Dict[str, Any]],
        top_k: int,
        config: Optional[GraphLayerConfig] = None,
    ) -> LayerResult:
        """Expand graph from top-k retrieval results."""
        config = config or GraphLayerConfig()
        if not results or top_k <= 0 or config.max_depth <= 0 or config.max_candidates <= 0:
            return LayerResult(layer_name=self.LAYER_NAME, results=[])

        start = time.perf_counter()
        with self._session_scope() as session:
            seeds, seed_scores = self._derive_seeds_from_results(
                session=session,
                results=results,
                top_k=top_k,
            )
            if not seeds:
                return LayerResult(layer_name=self.LAYER_NAME, results=[])
            results_out, metadata = self._bfs(
                session=session,
                seeds=seeds,
                seed_scores=seed_scores,
                config=config,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return LayerResult(
            layer_name=self.LAYER_NAME,
            results=results_out,
            latency_ms=round(elapsed_ms, 2),
            metadata=metadata,
        )

    def _derive_seeds_from_results(
        self,
        *,
        session: Session,
        results: List[Dict[str, Any]],
        top_k: int,
    ) -> Tuple[List[str], Dict[str, float]]:
        seed_entries: List[Tuple[str, float]] = []
        chunk_id_scores: Dict[str, float] = {}
        chunk_id_order: List[str] = []

        for result in results[:top_k]:
            score = _extract_seed_score(result)
            urn = result.get("urn")
            if urn:
                seed_entries.append((str(urn), score))
                continue

            document_id = result.get("document_id")
            chunk_index = result.get("chunk_index")
            if document_id is not None and chunk_index is not None:
                seed_entries.append(
                    (
                        str(URNGenerator.for_chunk(str(document_id), int(chunk_index))),
                        score,
                    )
                )
                continue

            chunk_id = result.get("chunk_id")
            if chunk_id:
                chunk_id_value = str(chunk_id)
                chunk_id_order.append(chunk_id_value)
                existing = chunk_id_scores.get(chunk_id_value)
                if existing is None or score > existing:
                    chunk_id_scores[chunk_id_value] = score

        if chunk_id_scores:
            chunk_id_map = self._resolve_chunk_ids_to_urns(session, chunk_id_scores.keys())
            for chunk_id in chunk_id_order:
                urn = chunk_id_map.get(chunk_id)
                if urn:
                    seed_entries.append((urn, chunk_id_scores[chunk_id]))

        seeds, seed_scores = _dedupe_seed_entries(seed_entries)
        return seeds, seed_scores

    def _bfs(
        self,
        *,
        session: Session,
        seeds: List[str],
        seed_scores: Dict[str, float],
        config: GraphLayerConfig,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        allowed_edge_types = _normalize_edge_types(config.allowed_edge_types)
        seed_score_stats = _build_score_stats(seed_scores.values())
        if allowed_edge_types == ():
            return [], {
                "seed_count": len(seeds),
                "total_candidates": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "depth_stats": {},
                "edge_type_usage": {},
                "seed_score_stats": seed_score_stats,
            }

        adjacency_cache: Dict[str, List[EdgeRecord]] = {}
        stats = {"cache_hits": 0, "cache_misses": 0}
        edge_type_usage: Dict[str, int] = {}
        candidates: Dict[str, CandidateInfo] = {}

        seed_set = set(seeds)
        queue: Deque[Tuple[str, int, str]] = deque((seed, 0, seed) for seed in seeds)
        visited = set(seeds)

        while queue:
            batch = _drain_queue(queue, self.PREFETCH_BATCH_SIZE)
            urns = [item[0] for item in batch]
            self._prefetch_edges(
                session=session,
                from_urns=urns,
                allowed_edge_types=allowed_edge_types,
                cache=adjacency_cache,
                stats=stats,
            )

            for current_urn, depth, seed_urn in batch:
                if depth >= config.max_depth:
                    continue
                for edge in adjacency_cache.get(current_urn, []):
                    if edge.edge_type:
                        edge_type_usage[edge.edge_type] = edge_type_usage.get(edge.edge_type, 0) + 1
                    next_urn = edge.to_urn
                    hop_depth = depth + 1
                    if hop_depth > config.max_depth:
                        continue
                    if next_urn not in seed_set:
                        self._update_candidate(
                            candidates=candidates,
                            urn=next_urn,
                            depth=hop_depth,
                            seed_urn=seed_urn,
                            edge_type=edge.edge_type,
                            seed_scores=seed_scores,
                            decay_factor=config.decay_factor,
                            max_candidates=config.max_candidates,
                        )
                    if next_urn not in visited:
                        if len(candidates) < config.max_candidates or next_urn in candidates:
                            visited.add(next_urn)
                            queue.append((next_urn, hop_depth, seed_urn))

        results = self._build_results(session, candidates, config.max_candidates)
        depth_stats = _build_depth_stats(candidates)
        metadata = {
            "seed_count": len(seeds),
            "total_candidates": len(candidates),
            "cache_hits": stats["cache_hits"],
            "cache_misses": stats["cache_misses"],
            "depth_stats": depth_stats,
            "edge_type_usage": edge_type_usage,
            "seed_score_stats": seed_score_stats,
        }
        return results, metadata

    def _prefetch_edges(
        self,
        *,
        session: Session,
        from_urns: Iterable[str],
        allowed_edge_types: Optional[Tuple[str, ...]],
        cache: Dict[str, List[EdgeRecord]],
        stats: Dict[str, int],
    ) -> None:
        urn_list = [urn for urn in from_urns if urn]
        if not urn_list:
            return

        unique_urns = list(dict.fromkeys(urn_list))
        duplicate_hits = len(urn_list) - len(unique_urns)
        missing = [urn for urn in unique_urns if urn not in cache]
        stats["cache_hits"] += duplicate_hits + (len(unique_urns) - len(missing))
        if not missing:
            return
        stats["cache_misses"] += len(missing)

        if allowed_edge_types == ():
            for urn in missing:
                cache[urn] = []
            return

        for batch in _chunked(missing, self.PREFETCH_BATCH_SIZE):
            query = session.query(
                GraphEdge.from_urn,
                GraphEdge.to_urn,
                GraphEdge.edge_type,
            ).filter(GraphEdge.from_urn.in_(batch))
            if allowed_edge_types is not None:
                query = query.filter(GraphEdge.edge_type.in_(allowed_edge_types))

            edges_by_from: Dict[str, List[EdgeRecord]] = {urn: [] for urn in batch}
            for row in query.all():
                from_urn = str(row.from_urn)
                edges_by_from.setdefault(from_urn, []).append(
                    EdgeRecord(to_urn=str(row.to_urn), edge_type=str(row.edge_type))
                )
            for urn in batch:
                cache[urn] = edges_by_from.get(urn, [])

    def _update_candidate(
        self,
        *,
        candidates: Dict[str, CandidateInfo],
        urn: str,
        depth: int,
        seed_urn: str,
        edge_type: Optional[str],
        seed_scores: Dict[str, float],
        decay_factor: float,
        max_candidates: int,
    ) -> None:
        if urn not in candidates and len(candidates) >= max_candidates:
            return
        base_score = seed_scores.get(seed_urn, 1.0)
        score = base_score * (decay_factor ** depth)
        existing = candidates.get(urn)
        if existing is None or score > existing.score or (
            score == existing.score and depth < existing.depth
        ):
            candidates[urn] = CandidateInfo(
                score=score,
                depth=depth,
                seed_urn=seed_urn,
                edge_type=edge_type,
            )

    def _build_results(
        self,
        session: Session,
        candidates: Dict[str, CandidateInfo],
        max_candidates: int,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        chunk_urns = {urn for urn in candidates if URNParser.parse_chunk_urn(urn)}
        chunk_id_map = self._resolve_chunk_urns(session, chunk_urns)

        sorted_candidates = sorted(
            candidates.items(),
            key=lambda item: (-item[1].score, item[0]),
        )
        results: List[Dict[str, Any]] = []
        for urn, info in sorted_candidates[:max_candidates]:
            entry: Dict[str, Any] = {
                "urn": urn,
                "score": float(info.score),
                "combined_score": float(info.score),
                "depth": info.depth,
                "seed_urn": info.seed_urn,
            }
            if info.edge_type:
                entry["edge_type"] = info.edge_type

            parsed = URN.parse(urn)
            if parsed:
                entry["entity_type"] = parsed.entity_type
                entry["entity_id"] = parsed.entity_id

            chunk_id = chunk_id_map.get(urn)
            if chunk_id:
                entry["chunk_id"] = chunk_id

            results.append(entry)
        return results

    def _resolve_chunk_urns(
        self,
        session: Session,
        chunk_urns: Iterable[str],
    ) -> Dict[str, str]:
        pair_to_urns: Dict[Tuple[str, int], List[str]] = {}
        for urn in chunk_urns:
            parsed = URNParser.parse_chunk_urn(urn)
            if not parsed:
                continue
            pair_to_urns.setdefault(parsed, []).append(urn)

        if not pair_to_urns:
            return {}

        pairs = list(pair_to_urns.keys())
        query = session.query(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
        ).filter(
            tuple_(DocumentChunk.document_id, DocumentChunk.chunk_index).in_(pairs)
        )

        resolved: Dict[str, str] = {}
        for row in query.all():
            key = (str(row.document_id), int(row.chunk_index))
            for urn in pair_to_urns.get(key, []):
                resolved[urn] = str(row.id)
        return resolved

    def _resolve_chunk_ids_to_urns(
        self,
        session: Session,
        chunk_ids: Iterable[str],
    ) -> Dict[str, str]:
        ids = [str(chunk_id) for chunk_id in set(chunk_ids)]
        if not ids:
            return {}

        query = session.query(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
        ).filter(DocumentChunk.id.in_(ids))

        resolved: Dict[str, str] = {}
        for row in query.all():
            resolved[str(row.id)] = str(
                URNGenerator.for_chunk(str(row.document_id), int(row.chunk_index))
            )
        return resolved


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _dedupe_seed_entries(
    seed_entries: Sequence[Tuple[str, float]],
) -> Tuple[List[str], Dict[str, float]]:
    seen: Dict[str, float] = {}
    ordered: List[str] = []
    for urn, score in seed_entries:
        if urn not in seen:
            ordered.append(urn)
            seen[urn] = score
        elif score > seen[urn]:
            seen[urn] = score
    return ordered, seen


def _normalize_edge_types(
    allowed_edge_types: Optional[Sequence[str]],
) -> Optional[Tuple[str, ...]]:
    if allowed_edge_types is None:
        return None
    normalized = tuple(str(edge_type) for edge_type in allowed_edge_types if edge_type)
    return normalized


def _extract_seed_score(result: Dict[str, Any]) -> float:
    for key in ("score", "combined_score", "rrf_score"):
        value = result.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 1.0


def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for idx in range(0, len(items), size):
        yield list(items[idx : idx + size])


def _drain_queue(
    queue: Deque[Tuple[str, int, str]],
    size: int,
) -> List[Tuple[str, int, str]]:
    batch: List[Tuple[str, int, str]] = []
    while queue and len(batch) < size:
        batch.append(queue.popleft())
    return batch


def _build_score_stats(scores: Sequence[float]) -> Dict[str, Any]:
    values = [float(value) for value in scores if value is not None]
    return {
        "count": len(values),
        "score_stats": summarize_scores(values),
    }


def _build_depth_stats(candidates: Dict[str, CandidateInfo]) -> Dict[str, Dict[str, Any]]:
    depth_scores: Dict[int, List[float]] = {}
    for info in candidates.values():
        depth_scores.setdefault(info.depth, []).append(info.score)

    depth_stats: Dict[str, Dict[str, Any]] = {}
    for depth, scores in depth_scores.items():
        depth_stats[str(depth)] = _build_score_stats(scores)
    return depth_stats


__all__ = [
    "GraphLayerConfig",
    "GraphLayerService",
    "URNParser",
]
