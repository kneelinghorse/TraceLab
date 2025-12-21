"""Materialize Semantic Protocol edges into graph_edges storage."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, tuple_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
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
    reason: Optional[str] = None
    via: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    @property
    def key(self) -> Tuple[str, str, str, str]:
        return (self.from_urn, self.to_urn, self.edge_type, self.direction)


@dataclass
class MaterializationResult:
    """Result summary for edge materialization."""

    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: List[str] = field(default_factory=list)

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
        session: Optional[Session] = None,
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
        session: Optional[Session] = None,
        *,
        mode: str = "full",
        project_id: Optional[str] = None,
    ) -> MaterializationResult:
        """Persist implicit edges derived from FK relationships."""
        session, managed = self._get_session(session)
        try:
            since = None
            if mode == "incremental":
                since = self._resolve_incremental_cutoff(session)
            edges = self._implicit_edge_specs(
                session,
                project_id=project_id,
                since=since,
            )
            return self._upsert_edges(edges, session=session, commit=managed)
        finally:
            if managed:
                session.close()

    def _get_session(self, session: Optional[Session]) -> Tuple[Session, bool]:
        if session is not None:
            return session, False
        return self.session_factory(), True

    @staticmethod
    def _resolve_incremental_cutoff(session: Session) -> Optional[datetime]:
        return session.query(func.max(GraphEdge.updated_at)).scalar()

    def _edges_from_manifest(
        self,
        manifest: ProtocolManifest,
    ) -> Iterable[EdgeSpec]:
        edges: List[Edge] = []

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
        project_id: Optional[str],
        since: Optional[datetime],
    ) -> Iterable[EdgeSpec]:
        yield from self._project_document_edges(session, project_id=project_id, since=since)
        yield from self._document_chunk_edges(session, project_id=project_id, since=since)
        yield from self._mission_project_edges(session, project_id=project_id, since=since)
        yield from self._insight_chunk_edges(session, project_id=project_id, since=since)
        yield from self._report_chunk_edges(session, project_id=project_id, since=since)

    def _project_document_edges(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        since: Optional[datetime],
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

    def _document_chunk_edges(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        since: Optional[datetime],
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

    def _mission_project_edges(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        since: Optional[datetime],
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(Mission.mission_id, Mission.project_id)
            .filter(Mission.project_id.isnot(None))
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

    def _insight_chunk_edges(
        self,
        session: Session,
        *,
        project_id: Optional[str],
        since: Optional[datetime],
    ) -> Iterable[EdgeSpec]:
        query = (
            session.query(InsightSource.insight_id, InsightSource.chunk_id)
            .join(Insight, InsightSource.insight_id == Insight.id)
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
        project_id: Optional[str],
        since: Optional[datetime],
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

    def _upsert_edges(
        self,
        edges: Iterable[EdgeSpec],
        *,
        session: Session,
        commit: bool,
    ) -> MaterializationResult:
        result = MaterializationResult()
        batch: List[EdgeSpec] = []

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

        new_edges: List[GraphEdge] = []
        seen: set[Tuple[str, str, str, str]] = set()

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
