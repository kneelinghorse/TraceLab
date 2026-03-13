"""Materialize Semantic Protocol edges into graph_edges storage."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, tuple_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    CollectionItem,
    Document,
    DocumentChunk,
    GraphEdge,
    Insight,
    InsightSource,
    Mission,
    Project,
    Report,
    ReportSource,
)
from app.services.pedr.semantic_protocol import (
    Edge,
    EntityType,
    ProtocolManifest,
    URNGenerator,
)


@dataclass(frozen=True)
class EdgeSpec:
    """Normalized edge payload for persistence."""

    edge_type: str
    from_urn: str
    to_urn: str
    direction: str = "out"
    weight: float = 1.0
    reason: str | None = None
    via: str | None = None
    evidence: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.from_urn, self.to_urn, self.edge_type, self.direction)


@dataclass
class MaterializationResult:
    """Result summary for edge materialization."""

    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.inserted_count + self.updated_count + self.skipped_count


class EdgeMaterializationService:
    """Persist explicit and implicit edges into graph_edges."""

    DEFAULT_BATCH_SIZE: int = 1000

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size

    def materialize_from_manifest(
        self,
        manifest: ProtocolManifest,
        session: Session | None = None,
    ) -> MaterializationResult:
        """Persist explicit edges from a ProtocolManifest."""
        session, managed = self._get_session(session)
        try:
            edges = self._edges_from_manifest(manifest)
            return self._upsert_edges(edges, session=session, commit=managed)
        finally:
            if managed:
                session.close()

    def materialize_implicit_edges(
        self,
        session: Session | None = None,
        *,
        mode: str = "full",
        project_id: str | None = None,
    ) -> MaterializationResult:
        """Persist implicit edges derived from FK relationships."""
        session, managed = self._get_session(session)
        try:
            since = None
            if mode == "incremental":
                since = self._resolve_incremental_cutoff(session)
            # Materialize all specs before upserting so yield_per cursors
            # complete before any mid-batch commits invalidate them.
            edges = list(
                self._implicit_edge_specs(
                    session,
                    project_id=project_id,
                    since=since,
                )
            )
            return self._upsert_edges(edges, session=session, commit=managed)
        finally:
            if managed:
                session.close()

    def _get_session(self, session: Session | None) -> tuple[Session, bool]:
        if session is not None:
            return session, False
        return self.session_factory(), True

    @staticmethod
    def _resolve_incremental_cutoff(session: Session) -> datetime | None:
        return session.query(func.max(GraphEdge.updated_at)).scalar()

    def _edges_from_manifest(
        self,
        manifest: ProtocolManifest,
    ) -> Iterable[EdgeSpec]:
        edges: list[Edge] = []

        if getattr(manifest, "edges", None):
            edges = list(manifest.edges)
        else:
            relationships = getattr(manifest, "relationships", None) or {}
            if isinstance(relationships, dict):
                raw_edges = relationships.get("edges") or []
                for item in raw_edges:
                    if isinstance(item, Edge):
                        edges.append(item)
                    elif isinstance(item, dict):
                        edges.append(Edge.from_dict(item))

        for edge in edges:
            if not edge.from_urn or not edge.to_urn:
                continue
            yield EdgeSpec(
                edge_type=edge.edge_type,
                from_urn=edge.from_urn,
                to_urn=edge.to_urn,
                direction=edge.direction or "out",
                weight=edge.weight if edge.weight is not None else 1.0,
                reason=edge.reason,
                via=edge.via,
                evidence=edge.evidence,
            )

    def _implicit_edge_specs(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        yield from self._project_document_edges(
            session, project_id=project_id, since=since
        )
        yield from self._document_project_edges(
            session, project_id=project_id, since=since
        )
        yield from self._document_chunk_edges(
            session, project_id=project_id, since=since
        )
        yield from self._chunk_document_edges(
            session, project_id=project_id, since=since
        )
        yield from self._mission_project_edges(
            session, project_id=project_id, since=since
        )
        yield from self._mission_document_edges(
            session, project_id=project_id, since=since
        )
        yield from self._mission_report_edges(
            session, project_id=project_id, since=since
        )
        yield from self._insight_project_edges(
            session, project_id=project_id, since=since
        )
        yield from self._insight_chunk_edges(
            session, project_id=project_id, since=since
        )
        yield from self._report_project_edges(
            session, project_id=project_id, since=since
        )
        yield from self._report_chunk_edges(session, project_id=project_id, since=since)
        yield from self._report_collection_edges(
            session, project_id=project_id, since=since
        )
        yield from self._document_source_edges(
            session, project_id=project_id, since=since
        )
        yield from self._collection_chunk_edges(
            session, project_id=project_id, since=since
        )
        # Semantic edge types (T38.1)
        yield from self._collection_cooccurrence_edges(
            session, project_id=project_id, since=since
        )

    def _project_document_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(Document.project_id, Document.id)
            .join(Project, Document.project_id == Project.id)
            .filter(Document.project_id.isnot(None))
            .filter(Document.deleted_at.is_(None))
            .filter(Project.deleted_at.is_(None))
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        if since:
            query = query.filter(Document.updated_at >= since)

        for project_value, document_id in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_project(str(project_value)))
            to_urn = str(URNGenerator.for_document(str(document_id)))
            yield EdgeSpec(
                edge_type="contains",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: documents.project_id",
                via="data",
            )

    def _document_project_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(Document.id, Document.project_id)
            .filter(Document.project_id.isnot(None))
            .filter(Document.deleted_at.is_(None))
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        if since:
            query = query.filter(Document.updated_at >= since)

        for document_id, project_value in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_document(str(document_id)))
            to_urn = str(URNGenerator.for_project(str(project_value)))
            yield EdgeSpec(
                edge_type="belongs_to",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: documents.project_id",
                via="data",
            )

    def _document_chunk_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.deleted_at.is_(None))
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        if since:
            query = query.filter(DocumentChunk.created_at >= since)

        for document_id, chunk_index in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_document(str(document_id)))
            to_urn = str(URNGenerator.for_chunk(str(document_id), int(chunk_index)))
            yield EdgeSpec(
                edge_type="contains",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: document_chunks.document_id",
                via="data",
            )

    def _chunk_document_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.deleted_at.is_(None))
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        if since:
            query = query.filter(DocumentChunk.created_at >= since)

        for document_id, chunk_index in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_chunk(str(document_id), int(chunk_index)))
            to_urn = str(URNGenerator.for_document(str(document_id)))
            yield EdgeSpec(
                edge_type="part_of",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: document_chunks.document_id",
                via="data",
            )

    def _mission_project_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(Mission.mission_id, Mission.project_id).filter(
            Mission.project_id.isnot(None)
        )
        if project_id:
            query = query.filter(Mission.project_id == project_id)
        if since:
            query = query.filter(Mission.updated_at >= since)

        for mission_id, project_value in query.yield_per(self.batch_size):
            if not mission_id or not project_value:
                continue
            from_urn = str(URNGenerator.for_mission(str(mission_id)))
            to_urn = str(URNGenerator.for_project(str(project_value)))
            yield EdgeSpec(
                edge_type="belongs_to",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: missions.project_id",
                via="data",
            )

    def _mission_document_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(Mission.mission_id, Mission.result_document_ids).filter(
            Mission.result_document_ids.isnot(None)
        )
        if project_id:
            query = query.filter(Mission.project_id == project_id)
        if since:
            query = query.filter(Mission.updated_at >= since)

        for mission_id, result_doc_ids in query.yield_per(self.batch_size):
            if (
                not mission_id
                or not result_doc_ids
                or not isinstance(result_doc_ids, list)
            ):
                continue
            from_urn = str(URNGenerator.for_mission(str(mission_id)))
            for doc_id in result_doc_ids:
                if not doc_id:
                    continue
                to_urn = str(URNGenerator.for_document(str(doc_id)))
                yield EdgeSpec(
                    edge_type="references",
                    from_urn=from_urn,
                    to_urn=to_urn,
                    direction="out",
                    weight=1.0,
                    reason="missions.result_document_ids",
                    via="data",
                )

    def _mission_report_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(Mission.mission_id, Mission.result_report_id).filter(
            Mission.result_report_id.isnot(None)
        )
        if project_id:
            query = query.filter(Mission.project_id == project_id)
        if since:
            query = query.filter(Mission.updated_at >= since)

        for mission_id, report_id in query.yield_per(self.batch_size):
            if not mission_id or not report_id:
                continue
            from_urn = str(URNGenerator.for_mission(str(mission_id)))
            to_urn = str(URNGenerator.generate(EntityType.REPORT, str(report_id)))
            yield EdgeSpec(
                edge_type="references",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="missions.result_report_id",
                via="data",
            )

    def _insight_project_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(Insight.id, Insight.project_id).filter(
            Insight.project_id.isnot(None)
        )
        if project_id:
            query = query.filter(Insight.project_id == project_id)
        if since:
            query = query.filter(Insight.updated_at >= since)

        for insight_id, project_value in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_insight(str(insight_id)))
            to_urn = str(URNGenerator.for_project(str(project_value)))
            yield EdgeSpec(
                edge_type="belongs_to",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: insights.project_id",
                via="data",
            )

    def _insight_chunk_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(InsightSource.insight_id, InsightSource.chunk_id).join(
            Insight, InsightSource.insight_id == Insight.id
        )
        if project_id:
            query = query.filter(Insight.project_id == project_id)
        if since:
            query = query.filter(Insight.updated_at >= since)

        for insight_id, chunk_id in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_insight(str(insight_id)))
            to_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_id)))
            yield EdgeSpec(
                edge_type="derived_from",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: insight_sources.chunk_id",
                via="data",
            )

    def _report_chunk_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(ReportSource.report_id, ReportSource.source_id)
            .join(Report, ReportSource.report_id == Report.id)
            .filter(ReportSource.source_type == "chunk")
        )
        if project_id:
            query = query.filter(Report.project_id == project_id)
        if since:
            query = query.filter(ReportSource.added_at >= since)

        for report_id, chunk_id in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.generate(EntityType.REPORT, str(report_id)))
            to_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_id)))
            yield EdgeSpec(
                edge_type="references",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: report_sources.source_id",
                via="data",
            )

    def _report_project_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(Report.id, Report.project_id).filter(
            Report.project_id.isnot(None)
        )
        if project_id:
            query = query.filter(Report.project_id == project_id)
        if since:
            query = query.filter(Report.updated_at >= since)

        for report_id, project_value in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.generate(EntityType.REPORT, str(report_id)))
            to_urn = str(URNGenerator.for_project(str(project_value)))
            yield EdgeSpec(
                edge_type="belongs_to",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: reports.project_id",
                via="data",
            )

    def _report_collection_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(ReportSource.report_id, ReportSource.source_id)
            .join(Report, ReportSource.report_id == Report.id)
            .filter(ReportSource.source_type == "collection")
        )
        if project_id:
            query = query.filter(Report.project_id == project_id)
        if since:
            query = query.filter(ReportSource.added_at >= since)

        for report_id, collection_id in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.generate(EntityType.REPORT, str(report_id)))
            to_urn = str(
                URNGenerator.generate(EntityType.COLLECTION, str(collection_id))
            )
            yield EdgeSpec(
                edge_type="references",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: report_sources.source_id",
                via="data",
            )

    def _document_source_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(
                Document.id,
                Document.source_report_id,
                Mission.mission_id,
            )
            .outerjoin(Mission, Document.source_mission_id == Mission.id)
            .filter(
                or_(
                    Document.source_report_id.isnot(None),
                    Document.source_mission_id.isnot(None),
                )
            )
            .filter(Document.deleted_at.is_(None))
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        if since:
            query = query.filter(Document.updated_at >= since)

        for document_id, report_id, mission_id in query.yield_per(self.batch_size):
            from_urn = str(URNGenerator.for_document(str(document_id)))
            if report_id:
                to_urn = str(URNGenerator.generate(EntityType.REPORT, str(report_id)))
                yield EdgeSpec(
                    edge_type="derived_from",
                    from_urn=from_urn,
                    to_urn=to_urn,
                    direction="out",
                    weight=1.0,
                    reason="documents.source_report_id",
                    via="data",
                )
            if mission_id:
                to_urn = str(URNGenerator.for_mission(str(mission_id)))
                yield EdgeSpec(
                    edge_type="derived_from",
                    from_urn=from_urn,
                    to_urn=to_urn,
                    direction="out",
                    weight=1.0,
                    reason="documents.source_mission_id",
                    via="data",
                )

    def _collection_chunk_edges(
        self,
        session: Session,
        *,
        project_id: str | None,
        since: datetime | None,
    ) -> Iterable[EdgeSpec]:
        query = session.query(CollectionItem.collection_id, CollectionItem.chunk_id)
        if project_id:
            query = (
                query.join(DocumentChunk, CollectionItem.chunk_id == DocumentChunk.id)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(Document.project_id == project_id)
                .filter(Document.deleted_at.is_(None))
            )
        if since:
            query = query.filter(CollectionItem.added_at >= since)

        for collection_id, chunk_id in query.yield_per(self.batch_size):
            from_urn = str(
                URNGenerator.generate(EntityType.COLLECTION, str(collection_id))
            )
            to_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_id)))
            yield EdgeSpec(
                edge_type="contains",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=1.0,
                reason="FK: collection_items.chunk_id",
                via="data",
            )

    # ------------------------------------------------------------------
    # Semantic edge types (T38.1)
    # ------------------------------------------------------------------

    MAX_COOCCURRENCE_COLLECTION_SIZE: int = 100

    def _collection_cooccurrence_edges(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        since: Optional[datetime],
    ) -> Iterable[EdgeSpec]:
        """Create co_occurs edges between chunks in the same collection.

        If chunks A and B both belong to collection C, they co-occur.
        Generates bidirectional pairs (A→B and B→A) for BFS traversal.
        Skips collections larger than MAX_COOCCURRENCE_COLLECTION_SIZE
        to prevent combinatorial explosion.
        """
        query = session.query(
            CollectionItem.collection_id, CollectionItem.chunk_id
        ).join(Collection, CollectionItem.collection_id == Collection.id)
        if project_id:
            query = (
                query.join(DocumentChunk, CollectionItem.chunk_id == DocumentChunk.id)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(Document.project_id == project_id)
                .filter(Document.deleted_at.is_(None))
            )
        if since:
            query = query.filter(CollectionItem.added_at >= since)

        # Group chunk IDs by collection
        collection_chunks: Dict[str, List[str]] = {}
        for collection_id, chunk_id in query.all():
            cid = str(collection_id)
            collection_chunks.setdefault(cid, []).append(str(chunk_id))

        for collection_id, chunk_ids in collection_chunks.items():
            if (
                len(chunk_ids) < 2
                or len(chunk_ids) > self.MAX_COOCCURRENCE_COLLECTION_SIZE
            ):
                continue
            unique_ids = list(dict.fromkeys(chunk_ids))
            for i, id_a in enumerate(unique_ids):
                urn_a = str(URNGenerator.generate(EntityType.CHUNK, id_a))
                for id_b in unique_ids[i + 1 :]:
                    urn_b = str(URNGenerator.generate(EntityType.CHUNK, id_b))
                    # Bidirectional: A→B and B→A
                    yield EdgeSpec(
                        edge_type="co_occurs",
                        from_urn=urn_a,
                        to_urn=urn_b,
                        direction="out",
                        weight=0.8,
                        reason=f"collection:{collection_id}",
                        via="semantic",
                    )
                    yield EdgeSpec(
                        edge_type="co_occurs",
                        from_urn=urn_b,
                        to_urn=urn_a,
                        direction="out",
                        weight=0.8,
                        reason=f"collection:{collection_id}",
                        via="semantic",
                    )

    DEFAULT_SIMILARITY_THRESHOLD: float = 0.85
    DEFAULT_SIMILARITY_TOP_K: int = 10

    def materialize_topic_similarity_edges(
        self,
        session: Optional[Session] = None,
        *,
        project_id: Optional[str] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        top_k: int = DEFAULT_SIMILARITY_TOP_K,
        qdrant_client: Optional[Any] = None,
        collection_name: Optional[str] = None,
    ) -> MaterializationResult:
        """Materialize topic_similar edges using Qdrant embedding similarity.

        For each chunk, queries Qdrant for nearest neighbors above the
        similarity threshold and creates bidirectional topic_similar edges.

        This is a separate pass from implicit edges because it requires
        Qdrant and is more expensive to compute.

        Args:
            session: SQLAlchemy session (created if not provided).
            project_id: Limit to chunks in this project.
            similarity_threshold: Minimum cosine similarity (default 0.85).
            top_k: Max neighbors per chunk (default 10).
            qdrant_client: Qdrant client instance (auto-resolved if not provided).
            collection_name: Qdrant collection name (auto-resolved if not provided).
        """
        session, managed = self._get_session(session)
        try:
            edges = list(
                self._topic_similarity_edge_specs(
                    session,
                    project_id=project_id,
                    similarity_threshold=similarity_threshold,
                    top_k=top_k,
                    qdrant_client=qdrant_client,
                    collection_name=collection_name,
                )
            )
            return self._upsert_edges(edges, session=session, commit=managed)
        finally:
            if managed:
                session.close()

    def _topic_similarity_edge_specs(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        similarity_threshold: float,
        top_k: int,
        qdrant_client: Optional[Any],
        collection_name: Optional[str],
    ) -> Iterable[EdgeSpec]:
        """Yield topic_similar edges by querying Qdrant for embedding neighbors."""
        import logging

        logger = logging.getLogger(__name__)

        # Resolve Qdrant client
        client = qdrant_client
        if client is None:
            try:
                from app.core.qdrant_client import get_qdrant_client

                client = get_qdrant_client()
            except Exception as exc:
                logger.warning("Qdrant unavailable for topic similarity: %s", exc)
                return

        if collection_name is None:
            try:
                from app.core.config import settings

                collection_name = settings.qdrant_collection_name
            except Exception:
                collection_name = "research_chunks"

        # Get chunk IDs to process
        query = session.query(
            DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index
        )
        if project_id:
            query = (
                query.join(Document, DocumentChunk.document_id == Document.id)
                .filter(Document.project_id == project_id)
                .filter(Document.deleted_at.is_(None))
            )

        chunks = query.all()
        if not chunks:
            return

        # Build chunk_id -> URN mapping
        chunk_urn_map: Dict[str, str] = {}
        for chunk_id, doc_id, chunk_index in chunks:
            chunk_urn_map[str(chunk_id)] = str(
                URNGenerator.for_chunk(str(doc_id), int(chunk_index))
            )

        # Query Qdrant for similar chunks per point
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
        except ImportError:
            logger.warning("qdrant_client.models not available")
            return

        seen_pairs: set = set()
        chunk_ids = list(chunk_urn_map.keys())

        for chunk_id in chunk_ids:
            try:
                query_filter = None
                if project_id:
                    query_filter = Filter(
                        must=[
                            FieldCondition(
                                key="project_id",
                                match=MatchValue(value=str(project_id)),
                            )
                        ]
                    )

                results = client.recommend(
                    collection_name=collection_name,
                    positive=[chunk_id],
                    limit=top_k,
                    score_threshold=similarity_threshold,
                    query_filter=query_filter,
                )
            except Exception as exc:
                logger.debug("Qdrant recommend failed for %s: %s", chunk_id, exc)
                continue

            from_urn = chunk_urn_map.get(chunk_id)
            if not from_urn:
                continue

            for result in results:
                neighbor_id = str(result.id)
                if neighbor_id == chunk_id:
                    continue
                score = float(result.score)

                # Deduplicate: only process each pair once
                pair_key = tuple(sorted([chunk_id, neighbor_id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Resolve neighbor URN
                to_urn = chunk_urn_map.get(neighbor_id)
                if not to_urn:
                    # Neighbor may be outside our chunk set; resolve from payload
                    payload = getattr(result, "payload", {}) or {}
                    n_doc_id = payload.get("document_id")
                    n_chunk_idx = payload.get("chunk_index")
                    if n_doc_id is not None and n_chunk_idx is not None:
                        to_urn = str(
                            URNGenerator.for_chunk(str(n_doc_id), int(n_chunk_idx))
                        )
                    else:
                        to_urn = str(
                            URNGenerator.generate(EntityType.CHUNK, neighbor_id)
                        )

                # Bidirectional edges
                yield EdgeSpec(
                    edge_type="topic_similar",
                    from_urn=from_urn,
                    to_urn=to_urn,
                    direction="out",
                    weight=round(score, 4),
                    reason=f"cosine>={similarity_threshold}",
                    via="semantic",
                    evidence={"cosine_similarity": round(score, 4)},
                )
                yield EdgeSpec(
                    edge_type="topic_similar",
                    from_urn=to_urn,
                    to_urn=from_urn,
                    direction="out",
                    weight=round(score, 4),
                    reason=f"cosine>={similarity_threshold}",
                    via="semantic",
                    evidence={"cosine_similarity": round(score, 4)},
                )

    def _upsert_edges(
        self,
        edges: Iterable[EdgeSpec],
        *,
        session: Session,
        commit: bool,
    ) -> MaterializationResult:
        result = MaterializationResult()
        batch: list[EdgeSpec] = []

        for edge in edges:
            if not edge.from_urn or not edge.to_urn:
                result.skipped_count += 1
                continue
            batch.append(edge)
            if len(batch) >= self.batch_size:
                self._upsert_batch(batch, session, result)
                if commit:
                    session.commit()
                else:
                    session.flush()
                batch = []

        if batch:
            self._upsert_batch(batch, session, result)
            if commit:
                session.commit()
            else:
                session.flush()

        return result

    def _upsert_batch(
        self,
        batch: Sequence[EdgeSpec],
        session: Session,
        result: MaterializationResult,
    ) -> None:
        if not batch:
            return

        keys = [edge.key for edge in batch]
        existing_edges = (
            session.query(GraphEdge)
            .filter(
                tuple_(
                    GraphEdge.from_urn,
                    GraphEdge.to_urn,
                    GraphEdge.edge_type,
                    GraphEdge.direction,
                ).in_(keys)
            )
            .all()
        )
        existing_map = {
            (edge.from_urn, edge.to_urn, edge.edge_type, edge.direction): edge
            for edge in existing_edges
        }

        new_edges: list[GraphEdge] = []
        seen: set[tuple[str, str, str, str]] = set()

        for spec in batch:
            if spec.key in seen:
                result.skipped_count += 1
                continue
            seen.add(spec.key)
            existing = existing_map.get(spec.key)
            if existing:
                if self._apply_edge_update(existing, spec):
                    result.updated_count += 1
                else:
                    result.skipped_count += 1
            else:
                new_edges.append(
                    GraphEdge.from_semantic_edge(
                        edge_type=spec.edge_type,
                        from_urn=spec.from_urn,
                        to_urn=spec.to_urn,
                        direction=spec.direction,
                        weight=spec.weight,
                        reason=spec.reason,
                        via=spec.via,
                        evidence=spec.evidence,
                    )
                )
                result.inserted_count += 1

        if new_edges:
            session.add_all(new_edges)

    @staticmethod
    def _apply_edge_update(edge: GraphEdge, spec: EdgeSpec) -> bool:
        updated = False

        if spec.weight is not None and edge.weight != spec.weight:
            edge.weight = spec.weight
            updated = True
        if spec.reason is not None and edge.reason != spec.reason:
            edge.reason = spec.reason
            updated = True
        if spec.via is not None and edge.via != spec.via:
            edge.via = spec.via
            updated = True
        if spec.evidence is not None and edge.evidence != spec.evidence:
            edge.evidence = spec.evidence
            updated = True

        return updated
