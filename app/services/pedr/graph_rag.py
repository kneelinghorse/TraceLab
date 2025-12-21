"""GraphRAG helper for extracting, pruning, and linearizing graph context."""
from __future__ import annotations

import re
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Collection,
    Document,
    DocumentChunk,
    GraphEdge,
    Insight,
    Mission,
    Project,
    Report,
)
from app.services.pedr.graph_layer import URNParser
from app.services.pedr.semantic_protocol import URN

try:  # pragma: no cover - exercised in environments with optional deps
    import tiktoken
except ModuleNotFoundError:  # pragma: no cover
    tiktoken = None  # type: ignore


@dataclass
class GraphNode:
    urn: str
    content: str
    entity_type: str
    depth: int
    relevance_score: float = 0.0


@dataclass
class GraphSubgraph:
    nodes: List[GraphNode]
    edges: List[Tuple[str, str, str]]  # (from, to, type)


@dataclass(frozen=True)
class EdgeRecord:
    to_urn: str
    edge_type: str


class GraphRAGHelper:
    """Extract and format graph context for RAG prompts."""

    PREFETCH_BATCH_SIZE = 200
    DEFAULT_MAX_NODES = 50
    DEFAULT_DEPTH = 2
    DEFAULT_MAX_TOKENS = 4000
    DEFAULT_ENCODING = "cl100k_base"
    MAX_SNIPPET_CHARS = 600
    RELEVANCE_WEIGHT = 0.7
    DEPTH_WEIGHT = 0.3

    _WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

    def __init__(
        self,
        *,
        session: Optional[Session] = None,
        session_factory: Optional[Callable[[], Session]] = None,
        encoding_name: str = DEFAULT_ENCODING,
        model_name: Optional[str] = None,
    ) -> None:
        if session and session_factory:
            raise ValueError("Provide either session or session_factory, not both.")
        self._session = session
        self._session_factory = session_factory or SessionLocal
        self._encoding_name = encoding_name
        self._model_name = model_name
        self._encoding = None

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

    def extract_subgraph(
        self,
        seeds: List[str],
        depth: int = DEFAULT_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
    ) -> GraphSubgraph:
        """Expand the graph from seed URNs and return nodes + edges."""
        seed_list = _dedupe_preserve_order(seeds)
        if not seed_list or depth <= 0 or max_nodes <= 0:
            return GraphSubgraph(nodes=[], edges=[])

        nodes: Dict[str, GraphNode] = {}
        edges: Dict[Tuple[str, str, str], None] = {}
        queue: Deque[Tuple[str, int]] = deque()
        for seed in seed_list:
            nodes[seed] = GraphNode(
                urn=seed,
                content="",
                entity_type=_entity_type(seed),
                depth=0,
            )
            queue.append((seed, 0))

        adjacency_cache: Dict[str, List[EdgeRecord]] = {}
        with self._session_scope() as session:
            while queue:
                batch = _drain_queue(queue, self.PREFETCH_BATCH_SIZE)
                urns = [item[0] for item in batch]
                self._prefetch_edges(
                    session=session,
                    from_urns=urns,
                    cache=adjacency_cache,
                )

                for current_urn, current_depth in batch:
                    if current_depth >= depth:
                        continue
                    for edge in adjacency_cache.get(current_urn, []):
                        next_urn = edge.to_urn
                        next_depth = current_depth + 1
                        if next_depth > depth:
                            continue

                        if next_urn not in nodes:
                            if len(nodes) >= max_nodes:
                                continue
                            nodes[next_urn] = GraphNode(
                                urn=next_urn,
                                content="",
                                entity_type=_entity_type(next_urn),
                                depth=next_depth,
                            )
                            queue.append((next_urn, next_depth))
                        edges[(current_urn, next_urn, edge.edge_type)] = None

            self._hydrate_nodes(session=session, nodes=nodes)

        return GraphSubgraph(
            nodes=list(nodes.values()),
            edges=list(edges.keys()),
        )

    def prune_by_relevance(
        self,
        subgraph: GraphSubgraph,
        query: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> GraphSubgraph:
        """Prune a subgraph to fit within a token budget."""
        if not subgraph.nodes:
            return subgraph
        if max_tokens <= 0:
            return GraphSubgraph(nodes=[], edges=[])

        query_tokens = _tokenize(query, self._WORD_RE)
        scored_nodes = [
            GraphNode(
                urn=node.urn,
                content=node.content,
                entity_type=node.entity_type,
                depth=node.depth,
                relevance_score=self._score_node(node, query_tokens),
            )
            for node in subgraph.nodes
        ]
        node_map = {node.urn: node for node in scored_nodes}
        filtered_edges = _filter_edges(subgraph.edges, set(node_map.keys()))
        candidate = GraphSubgraph(nodes=list(node_map.values()), edges=filtered_edges)

        if self._count_tokens(self.linearize(candidate)) <= max_tokens:
            return candidate

        ordered = sorted(
            candidate.nodes,
            key=lambda node: (-node.relevance_score, node.depth, node.urn),
        )

        while ordered:
            pruned = GraphSubgraph(
                nodes=list(ordered),
                edges=_filter_edges(candidate.edges, {node.urn for node in ordered}),
            )
            if self._count_tokens(self.linearize(pruned)) <= max_tokens:
                return pruned
            ordered.pop()

        return GraphSubgraph(nodes=[], edges=[])

    def linearize(self, subgraph: GraphSubgraph) -> str:
        """Render a subgraph into a readable prompt segment."""
        if not subgraph.nodes:
            return ""

        node_map = {node.urn: node for node in subgraph.nodes}
        edges = _filter_edges(subgraph.edges, set(node_map.keys()))
        edges_by_from: Dict[str, List[Tuple[str, str]]] = {}
        for from_urn, to_urn, edge_type in edges:
            edges_by_from.setdefault(from_urn, []).append((to_urn, edge_type))

        order = _topological_order(node_map, edges)
        lines: List[str] = ["## Related Context (via graph expansion)", ""]

        for urn in order:
            node = node_map[urn]
            lines.append(f"### {_format_heading(node)}")
            if node.entity_type == "chunk":
                evidence = _format_chunk_evidence(node.urn)
                if evidence:
                    lines.append(f"Evidence from: {evidence}")
                if node.content:
                    quote = _sanitize_quote(node.content)
                    lines.append(f"> \"{quote}\"")
            else:
                if node.content:
                    lines.append(node.content.strip())

            related = edges_by_from.get(urn, [])
            if related:
                related_sorted = sorted(
                    related,
                    key=lambda item: (_format_reference(node_map.get(item[0])), item[1]),
                )
                for to_urn, edge_type in related_sorted:
                    target = node_map.get(to_urn)
                    if not target:
                        continue
                    lines.append(f"Related: {_format_reference(target)} ({edge_type})")

            lines.append("")

        return "\n".join(lines).strip()

    def _prefetch_edges(
        self,
        *,
        session: Session,
        from_urns: Iterable[str],
        cache: Dict[str, List[EdgeRecord]],
    ) -> None:
        urn_list = [urn for urn in from_urns if urn]
        if not urn_list:
            return
        unique_urns = list(dict.fromkeys(urn_list))
        missing = [urn for urn in unique_urns if urn not in cache]
        if not missing:
            return

        for batch in _chunked(missing, self.PREFETCH_BATCH_SIZE):
            query = session.query(
                GraphEdge.from_urn,
                GraphEdge.to_urn,
                GraphEdge.edge_type,
            ).filter(GraphEdge.from_urn.in_(batch))

            edges_by_from: Dict[str, List[EdgeRecord]] = {urn: [] for urn in batch}
            for row in query.all():
                from_urn = str(row.from_urn)
                edges_by_from.setdefault(from_urn, []).append(
                    EdgeRecord(
                        to_urn=str(row.to_urn),
                        edge_type=str(row.edge_type),
                    )
                )
            for urn in batch:
                cache[urn] = edges_by_from.get(urn, [])

    def _hydrate_nodes(
        self,
        *,
        session: Session,
        nodes: Dict[str, GraphNode],
    ) -> None:
        chunk_pairs: Dict[Tuple[str, int], List[str]] = {}
        document_ids: Dict[str, List[str]] = {}
        mission_ids: Dict[str, List[str]] = {}
        project_ids: Dict[str, List[str]] = {}
        report_ids: Dict[str, List[str]] = {}
        insight_ids: Dict[str, List[str]] = {}
        collection_ids: Dict[str, List[str]] = {}

        for urn, node in nodes.items():
            parsed = URN.parse(urn)
            if not parsed:
                continue
            entity_id = parsed.entity_id
            node.entity_type = parsed.entity_type
            if parsed.entity_type == "chunk":
                parsed_chunk = URNParser.parse_chunk_urn(urn)
                if parsed_chunk and _is_valid_uuid(parsed_chunk[0]):
                    chunk_pairs.setdefault(parsed_chunk, []).append(urn)
            elif parsed.entity_type == "document":
                if _is_valid_uuid(entity_id):
                    document_ids.setdefault(entity_id, []).append(urn)
            elif parsed.entity_type == "mission":
                mission_ids.setdefault(entity_id, []).append(urn)
            elif parsed.entity_type == "project":
                if _is_valid_uuid(entity_id):
                    project_ids.setdefault(entity_id, []).append(urn)
            elif parsed.entity_type == "report":
                if _is_valid_uuid(entity_id):
                    report_ids.setdefault(entity_id, []).append(urn)
            elif parsed.entity_type == "insight":
                if _is_valid_uuid(entity_id):
                    insight_ids.setdefault(entity_id, []).append(urn)
            elif parsed.entity_type == "collection":
                if _is_valid_uuid(entity_id):
                    collection_ids.setdefault(entity_id, []).append(urn)

        if chunk_pairs:
            pairs = list(chunk_pairs.keys())
            query = session.query(
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
            ).filter(
                tuple_(DocumentChunk.document_id, DocumentChunk.chunk_index).in_(pairs)
            )
            for row in query.all():
                key = (str(row.document_id), int(row.chunk_index))
                for urn in chunk_pairs.get(key, []):
                    nodes[urn].content = _truncate(row.content, self.MAX_SNIPPET_CHARS)

        if document_ids:
            query = session.query(Document.id, Document.name).filter(
                Document.id.in_(document_ids.keys())
            )
            for row in query.all():
                for urn in document_ids.get(str(row.id), []):
                    nodes[urn].content = _truncate(row.name, self.MAX_SNIPPET_CHARS)

        if mission_ids:
            query = session.query(Mission.mission_id, Mission.title, Mission.objective).filter(
                Mission.mission_id.in_(mission_ids.keys())
            )
            for row in query.all():
                label = row.title or row.objective or row.mission_id
                for urn in mission_ids.get(str(row.mission_id), []):
                    nodes[urn].content = _truncate(label, self.MAX_SNIPPET_CHARS)

        if project_ids:
            query = session.query(Project.id, Project.name).filter(
                Project.id.in_(project_ids.keys())
            )
            for row in query.all():
                for urn in project_ids.get(str(row.id), []):
                    nodes[urn].content = _truncate(row.name, self.MAX_SNIPPET_CHARS)

        if report_ids:
            query = session.query(Report.id, Report.title).filter(
                Report.id.in_(report_ids.keys())
            )
            for row in query.all():
                for urn in report_ids.get(str(row.id), []):
                    nodes[urn].content = _truncate(row.title, self.MAX_SNIPPET_CHARS)

        if insight_ids:
            query = session.query(Insight.id, Insight.title, Insight.content).filter(
                Insight.id.in_(insight_ids.keys())
            )
            for row in query.all():
                label = row.title or row.content or str(row.id)
                for urn in insight_ids.get(str(row.id), []):
                    nodes[urn].content = _truncate(label, self.MAX_SNIPPET_CHARS)

        if collection_ids:
            query = session.query(Collection.id, Collection.name, Collection.description).filter(
                Collection.id.in_(collection_ids.keys())
            )
            for row in query.all():
                label = row.name or row.description or str(row.id)
                for urn in collection_ids.get(str(row.id), []):
                    nodes[urn].content = _truncate(label, self.MAX_SNIPPET_CHARS)

        for urn, node in nodes.items():
            if not node.content:
                fallback = _fallback_label(urn)
                node.content = _truncate(fallback, self.MAX_SNIPPET_CHARS)

    def _score_node(
        self,
        node: GraphNode,
        query_tokens: Sequence[str],
    ) -> float:
        if not query_tokens:
            depth_score = 1.0 / (node.depth + 1)
            return round(depth_score, 4)
        content_tokens = _tokenize(node.content, self._WORD_RE)
        if content_tokens:
            overlap = len(set(query_tokens).intersection(content_tokens)) / len(set(query_tokens))
        else:
            overlap = 0.0
        depth_score = 1.0 / (node.depth + 1)
        return round(
            (overlap * self.RELEVANCE_WEIGHT) + (depth_score * self.DEPTH_WEIGHT),
            4,
        )

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        encoder = self._get_encoder()
        return len(encoder.encode(text))

    def _get_encoder(self):
        if self._encoding is not None:
            return self._encoding
        if tiktoken is None:
            raise RuntimeError("tiktoken is required for GraphRAGHelper token counting.")
        if self._model_name:
            try:
                self._encoding = tiktoken.encoding_for_model(self._model_name)
                return self._encoding
            except KeyError:
                pass
        self._encoding = tiktoken.get_encoding(self._encoding_name)
        return self._encoding


def _tokenize(text: str, pattern: re.Pattern[str]) -> List[str]:
    return [match.group(0).lower() for match in pattern.finditer(text or "")]


def _entity_type(urn: str) -> str:
    parsed = URN.parse(urn or "")
    return parsed.entity_type if parsed else "unknown"


def _fallback_label(urn: str) -> str:
    parsed = URN.parse(urn or "")
    if parsed:
        return parsed.entity_id or urn
    return urn or "unknown"


def _format_heading(node: GraphNode) -> str:
    parsed = URN.parse(node.urn or "")
    entity_id = parsed.entity_id if parsed else node.urn
    entity_type = node.entity_type or (parsed.entity_type if parsed else "entity")
    if entity_type == "chunk":
        evidence = _format_chunk_evidence(node.urn)
        return f"Chunk: {evidence or entity_id}"
    if entity_type == "mission":
        if node.content and node.content != entity_id:
            return f"Mission: {entity_id} - {node.content}"
        return f"Mission: {entity_id}"
    if node.content:
        return f"{entity_type.title()}: {node.content}"
    return f"{entity_type.title()}: {entity_id}"


def _format_reference(node: Optional[GraphNode]) -> str:
    if node is None:
        return "unknown"
    parsed = URN.parse(node.urn or "")
    entity_id = parsed.entity_id if parsed else node.urn
    entity_type = node.entity_type or (parsed.entity_type if parsed else "entity")
    if entity_type == "chunk":
        return _format_chunk_evidence(node.urn) or entity_id
    label = node.content or entity_id or "unknown"
    return f"{entity_type}:{label}"


def _format_chunk_evidence(urn: str) -> Optional[str]:
    parsed = URNParser.parse_chunk_urn(urn)
    if not parsed:
        return None
    document_id, chunk_index = parsed
    return f"{document_id}/chunk-{chunk_index}"


def _sanitize_quote(text: str) -> str:
    cleaned = " ".join((text or "").split())
    cleaned = cleaned.replace('"', "'")
    return _truncate(cleaned, GraphRAGHelper.MAX_SNIPPET_CHARS)


def _truncate(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for idx in range(0, len(items), size):
        yield list(items[idx : idx + size])


def _drain_queue(
    queue: Deque[Tuple[str, int]],
    size: int,
) -> List[Tuple[str, int]]:
    batch: List[Tuple[str, int]] = []
    while queue and len(batch) < size:
        batch.append(queue.popleft())
    return batch


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _filter_edges(
    edges: Sequence[Tuple[str, str, str]],
    allowed_nodes: set[str],
) -> List[Tuple[str, str, str]]:
    return [
        edge
        for edge in edges
        if edge[0] in allowed_nodes and edge[1] in allowed_nodes
    ]


def _topological_order(
    nodes: Dict[str, GraphNode],
    edges: Sequence[Tuple[str, str, str]],
) -> List[str]:
    in_degree: Dict[str, int] = {urn: 0 for urn in nodes}
    adjacency: Dict[str, List[str]] = {urn: [] for urn in nodes}
    for from_urn, to_urn, _edge_type in edges:
        if from_urn not in nodes or to_urn not in nodes:
            continue
        adjacency[from_urn].append(to_urn)
        in_degree[to_urn] += 1

    def sort_key(urn: str) -> Tuple[int, str]:
        node = nodes[urn]
        return (node.depth, urn)

    queue = sorted([urn for urn, degree in in_degree.items() if degree == 0], key=sort_key)
    order: List[str] = []

    while queue:
        urn = queue.pop(0)
        order.append(urn)
        for neighbor in sorted(adjacency.get(urn, []), key=sort_key):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                queue.sort(key=sort_key)

    if len(order) < len(nodes):
        remaining = sorted((urn for urn in nodes if urn not in order), key=sort_key)
        order.extend(remaining)

    return order


__all__ = [
    "GraphNode",
    "GraphSubgraph",
    "GraphRAGHelper",
]
