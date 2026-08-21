"""PEDR Relational Layer - Graph Context for Research Entities.

This module builds and traverses the relationship graph for research entities,
enabling "show me everything related to this mission" queries.

Relationships modeled:
- mission BELONGS_TO project
- mission REFERENCES chunk (via result_document_ids -> documents -> chunks)
- document BELONGS_TO project
- document CONTAINS chunk
- insight DERIVED_FROM chunk (via insight_sources)
- report BELONGS_TO project
- report REFERENCES chunk (via report_sources)

Uses SQL joins for MVP - no separate graph DB required.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Document,
    DocumentChunk,
    Insight,
    InsightSource,
    Mission,
    Project,
    Report,
    ReportSource,
)
from app.services.pedr.semantic_protocol import get_semantic_protocol

logger = logging.getLogger(__name__)


class RelationType(str, Enum):
    """Types of relationships between entities."""

    BELONGS_TO = "belongs_to"  # entity -> parent
    CONTAINS = "contains"  # parent -> child
    REFERENCES = "references"  # entity -> evidence
    DERIVED_FROM = "derived_from"  # insight -> source chunks
    SIBLING_OF = "sibling_of"  # same parent
    RELATED_TO = "related_to"  # general association


class EntityType(str, Enum):
    """Types of entities in the research graph."""

    PROJECT = "project"
    DOCUMENT = "document"
    CHUNK = "chunk"
    MISSION = "mission"
    INSIGHT = "insight"
    REPORT = "report"


@dataclass
class RelatedEntity:
    """An entity related to the query entity."""

    entity_type: EntityType
    entity_id: str
    relation_type: RelationType
    relation_direction: str  # "outbound" or "inbound"
    distance: int  # hops from source entity
    content_preview: str | None = None  # First N chars of content
    metadata: dict[str, Any] = field(default_factory=dict)
    urn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "relation_type": self.relation_type.value,
            "relation_direction": self.relation_direction,
            "distance": self.distance,
            "content_preview": self.content_preview,
            "metadata": self.metadata,
            "urn": self.urn,
        }


@dataclass
class GraphExpansionResult:
    """Result from graph expansion query."""

    source_urn: str
    source_entity_type: EntityType
    source_entity_id: str
    related_entities: list[RelatedEntity]
    total_found: int
    expansion_depth: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "source_urn": self.source_urn,
            "source_entity_type": self.source_entity_type.value,
            "source_entity_id": self.source_entity_id,
            "related_entities": [e.to_dict() for e in self.related_entities],
            "total_found": self.total_found,
            "expansion_depth": self.expansion_depth,
        }


class RelationalService:
    """Service for building and traversing the research entity graph.

    Provides graph expansion capabilities for the PEDR search orchestrator,
    enabling queries like "show me everything related to this mission".
    """

    CONTENT_PREVIEW_LENGTH = 200

    def __init__(
        self,
        session: Session | None = None,
        semantic_protocol: Any | None = None,
    ) -> None:
        """Initialize the relational service.

        Args:
            session: SQLAlchemy session. If None, creates new session per call.
            semantic_protocol: SemanticProtocol instance for URN generation.
        """
        self._session = session
        self._semantic_protocol = semantic_protocol or get_semantic_protocol()

    @contextmanager
    def _session_scope(
        self,
        session: Session | None = None,
    ) -> Iterable[Session]:
        if session is not None:
            yield session
            return
        if self._session is not None:
            yield self._session
            return
        created_session = SessionLocal()
        try:
            yield created_session
        finally:
            created_session.close()

    def parse_urn(self, urn: str) -> tuple[EntityType, str]:
        """Parse a URN into entity type and ID.

        URN format: urn:research:{type}:{id}

        Args:
            urn: The URN to parse.

        Returns:
            Tuple of (EntityType, entity_id)

        Raises:
            ValueError: If URN format is invalid.
        """
        if not urn.startswith("urn:research:"):
            raise ValueError(f"Invalid URN format: {urn}")

        parts = urn.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid URN format: {urn}")

        type_str = parts[2]
        entity_id = parts[3]

        type_map = {
            "project": EntityType.PROJECT,
            "document": EntityType.DOCUMENT,
            "chunk": EntityType.CHUNK,
            "mission": EntityType.MISSION,
            "insight": EntityType.INSIGHT,
            "report": EntityType.REPORT,
        }

        if type_str not in type_map:
            raise ValueError(f"Unknown entity type in URN: {type_str}")

        return type_map[type_str], entity_id

    def get_related(
        self,
        urn: str,
        *,
        max_depth: int = 2,
        limit: int = 50,
        include_types: list[EntityType] | None = None,
        exclude_types: list[EntityType] | None = None,
        relation_types: list[RelationType] | None = None,
        session: Session | None = None,
        allowed_project_ids: list[UUID] | None = None,
    ) -> GraphExpansionResult:
        """Get entities related to the given URN.

        Performs breadth-first graph traversal from the source entity,
        collecting related entities up to max_depth hops away.

        Args:
            urn: URN of the source entity.
            max_depth: Maximum traversal depth (default 2).
            limit: Maximum total related entities to return.
            include_types: Only include these entity types.
            exclude_types: Exclude these entity types.
            relation_types: Only follow these relation types.
            allowed_project_ids: Project scope for returned and traversed entities.
                None preserves the unscoped behavior; an empty list denies all.

        Returns:
            GraphExpansionResult with related entities.
        """
        entity_type, entity_id = self.parse_urn(urn)

        related: list[RelatedEntity] = []
        visited: set[str] = {f"{entity_type.value}:{entity_id}"}
        allowed_project_id_set = (
            set(allowed_project_ids) if allowed_project_ids is not None else None
        )

        if allowed_project_id_set is not None and not allowed_project_id_set:
            return GraphExpansionResult(
                source_urn=urn,
                source_entity_type=entity_type,
                source_entity_id=entity_id,
                related_entities=[],
                total_found=0,
                expansion_depth=max_depth,
            )

        # BFS traversal
        current_level = [(entity_type, entity_id, 0)]  # (type, id, depth)

        with self._session_scope(session) as active_session:
            if (
                allowed_project_id_set is not None
                and self._entity_project_id(
                    active_session,
                    entity_type,
                    entity_id,
                )
                not in allowed_project_id_set
            ):
                return GraphExpansionResult(
                    source_urn=urn,
                    source_entity_type=entity_type,
                    source_entity_id=entity_id,
                    related_entities=[],
                    total_found=0,
                    expansion_depth=max_depth,
                )

            while current_level and len(related) < limit:
                next_level = []

                for current_type, current_id, depth in current_level:
                    if depth >= max_depth:
                        continue

                    # Get direct relations at depth + 1
                    neighbors = self._get_neighbors(
                        active_session,
                        current_type,
                        current_id,
                        include_types=include_types,
                        exclude_types=exclude_types,
                        relation_types=relation_types,
                    )

                    for neighbor in neighbors:
                        if (
                            allowed_project_id_set is not None
                            and self._entity_project_id(
                                active_session,
                                neighbor.entity_type,
                                neighbor.entity_id,
                            )
                            not in allowed_project_id_set
                        ):
                            continue
                        key = f"{neighbor.entity_type.value}:{neighbor.entity_id}"
                        if key not in visited:
                            visited.add(key)
                            neighbor.distance = depth + 1
                            related.append(neighbor)

                            if len(related) >= limit:
                                break

                            # Queue for next level
                            next_level.append(
                                (neighbor.entity_type, neighbor.entity_id, depth + 1)
                            )

                    if len(related) >= limit:
                        break

                current_level = next_level

        return GraphExpansionResult(
            source_urn=urn,
            source_entity_type=entity_type,
            source_entity_id=entity_id,
            related_entities=related[:limit],
            total_found=len(related),
            expansion_depth=max_depth,
        )

    def _entity_project_id(
        self,
        session: Session,
        entity_type: EntityType,
        entity_id: str,
    ) -> UUID | None:
        """Resolve the project governing an entity for graph-scope pruning."""
        try:
            entity_uuid = UUID(entity_id)
        except (TypeError, ValueError):
            return None

        if entity_type == EntityType.PROJECT:
            return entity_uuid
        if entity_type == EntityType.CHUNK:
            return session.execute(
                select(Document.project_id)
                .join(
                    DocumentChunk,
                    DocumentChunk.document_id == Document.id,
                )
                .where(DocumentChunk.id == entity_uuid)
            ).scalar_one_or_none()

        model_by_type = {
            EntityType.DOCUMENT: Document,
            EntityType.MISSION: Mission,
            EntityType.INSIGHT: Insight,
            EntityType.REPORT: Report,
        }
        model = model_by_type.get(entity_type)
        if model is None:
            return None
        resource = session.get(model, entity_uuid)
        return resource.project_id if resource is not None else None

    def _get_neighbors(
        self,
        session: Session,
        entity_type: EntityType,
        entity_id: str,
        *,
        include_types: list[EntityType] | None = None,
        exclude_types: list[EntityType] | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[RelatedEntity]:
        """Get direct neighbors of an entity.

        Args:
            session: Database session.
            entity_type: Type of the source entity.
            entity_id: ID of the source entity.
            include_types: Only include these entity types.
            exclude_types: Exclude these entity types.
            relation_types: Only follow these relation types.

        Returns:
            List of directly related entities.
        """
        neighbors: list[RelatedEntity] = []

        # Dispatch to type-specific handlers
        handlers = {
            EntityType.PROJECT: self._get_project_neighbors,
            EntityType.DOCUMENT: self._get_document_neighbors,
            EntityType.CHUNK: self._get_chunk_neighbors,
            EntityType.MISSION: self._get_mission_neighbors,
            EntityType.INSIGHT: self._get_insight_neighbors,
            EntityType.REPORT: self._get_report_neighbors,
        }

        handler = handlers.get(entity_type)
        if handler:
            raw_neighbors = handler(session, entity_id)

            # Filter by types
            for neighbor in raw_neighbors:
                if include_types and neighbor.entity_type not in include_types:
                    continue
                if exclude_types and neighbor.entity_type in exclude_types:
                    continue
                if relation_types and neighbor.relation_type not in relation_types:
                    continue
                neighbors.append(neighbor)

        return neighbors

    def _get_project_neighbors(
        self,
        session: Session,
        project_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of a project entity."""
        neighbors: list[RelatedEntity] = []

        try:
            project_uuid = UUID(project_id)
        except ValueError:
            return neighbors

        # Documents BELONG_TO project (inbound)
        docs = (
            session.execute(
                select(Document)
                .where(Document.project_id == project_uuid)
                .where(Document.deleted_at.is_(None))
                .limit(20)
            )
            .scalars()
            .all()
        )

        for doc in docs:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.DOCUMENT,
                    entity_id=str(doc.id),
                    relation_type=RelationType.BELONGS_TO,
                    relation_direction="inbound",
                    distance=1,
                    content_preview=doc.name,
                    metadata={
                        "file_type": doc.file_type,
                        "source_type": doc.source_type,
                    },
                    urn=self._semantic_protocol.generate_urn("document", str(doc.id)),
                )
            )

        # Missions BELONG_TO project (inbound)
        missions = (
            session.execute(
                select(Mission).where(Mission.project_id == project_uuid).limit(20)
            )
            .scalars()
            .all()
        )

        for mission in missions:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.MISSION,
                    entity_id=str(mission.id),
                    relation_type=RelationType.BELONGS_TO,
                    relation_direction="inbound",
                    distance=1,
                    content_preview=mission.title[: self.CONTENT_PREVIEW_LENGTH]
                    if mission.title
                    else None,
                    metadata={
                        "mission_id": mission.mission_id,
                        "status": mission.status,
                    },
                    urn=self._semantic_protocol.generate_urn(
                        "mission", str(mission.id)
                    ),
                )
            )

        # Reports BELONG_TO project (inbound)
        reports = (
            session.execute(
                select(Report).where(Report.project_id == project_uuid).limit(20)
            )
            .scalars()
            .all()
        )

        for report in reports:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.REPORT,
                    entity_id=str(report.id),
                    relation_type=RelationType.BELONGS_TO,
                    relation_direction="inbound",
                    distance=1,
                    content_preview=report.title,
                    metadata={
                        "report_type": report.report_type,
                        "status": report.status,
                    },
                    urn=self._semantic_protocol.generate_urn("report", str(report.id)),
                )
            )

        # Insights BELONG_TO project (inbound)
        insights = (
            session.execute(
                select(Insight).where(Insight.project_id == project_uuid).limit(20)
            )
            .scalars()
            .all()
        )

        for insight in insights:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.INSIGHT,
                    entity_id=str(insight.id),
                    relation_type=RelationType.BELONGS_TO,
                    relation_direction="inbound",
                    distance=1,
                    content_preview=insight.title,
                    metadata={
                        "insight_type": insight.insight_type,
                        "validated": insight.validated,
                    },
                    urn=self._semantic_protocol.generate_urn(
                        "insight", str(insight.id)
                    ),
                )
            )

        return neighbors

    def _get_document_neighbors(
        self,
        session: Session,
        document_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of a document entity."""
        neighbors: list[RelatedEntity] = []

        try:
            doc_uuid = UUID(document_id)
        except ValueError:
            return neighbors

        # Get the document
        doc = session.execute(
            select(Document).where(Document.id == doc_uuid)
        ).scalar_one_or_none()

        if not doc:
            return neighbors

        # Document BELONGS_TO project (outbound)
        if doc.project_id:
            project = session.execute(
                select(Project).where(Project.id == doc.project_id)
            ).scalar_one_or_none()

            if project:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.PROJECT,
                        entity_id=str(project.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=project.name,
                        metadata={
                            "status": project.status,
                            "research_type": project.research_type,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "project", str(project.id)
                        ),
                    )
                )

        # Document CONTAINS chunks (outbound)
        chunks = (
            session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc_uuid)
                .order_by(DocumentChunk.chunk_index)
                .limit(30)
            )
            .scalars()
            .all()
        )

        for chunk in chunks:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.CHUNK,
                    entity_id=str(chunk.id),
                    relation_type=RelationType.CONTAINS,
                    relation_direction="outbound",
                    distance=1,
                    content_preview=chunk.content[: self.CONTENT_PREVIEW_LENGTH]
                    if chunk.content
                    else None,
                    metadata={
                        "chunk_index": chunk.chunk_index,
                        "token_count": chunk.token_count,
                    },
                    urn=self._semantic_protocol.generate_urn("chunk", str(chunk.id)),
                )
            )

        # Sibling documents in same project
        if doc.project_id:
            siblings = (
                session.execute(
                    select(Document)
                    .where(
                        and_(
                            Document.project_id == doc.project_id,
                            Document.id != doc_uuid,
                            Document.deleted_at.is_(None),
                        )
                    )
                    .limit(10)
                )
                .scalars()
                .all()
            )

            for sibling in siblings:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.DOCUMENT,
                        entity_id=str(sibling.id),
                        relation_type=RelationType.SIBLING_OF,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=sibling.name,
                        metadata={
                            "file_type": sibling.file_type,
                            "source_type": sibling.source_type,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "document", str(sibling.id)
                        ),
                    )
                )

        return neighbors

    def _get_chunk_neighbors(
        self,
        session: Session,
        chunk_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of a chunk entity."""
        neighbors: list[RelatedEntity] = []

        try:
            chunk_uuid = UUID(chunk_id)
        except ValueError:
            return neighbors

        # Get the chunk
        chunk = session.execute(
            select(DocumentChunk).where(DocumentChunk.id == chunk_uuid)
        ).scalar_one_or_none()

        if not chunk:
            return neighbors

        # Chunk BELONGS_TO document (outbound - using CONTAINS inverse)
        if chunk.document_id:
            doc = session.execute(
                select(Document).where(Document.id == chunk.document_id)
            ).scalar_one_or_none()

            if doc:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.DOCUMENT,
                        entity_id=str(doc.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=doc.name,
                        metadata={
                            "file_type": doc.file_type,
                            "source_type": doc.source_type,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "document", str(doc.id)
                        ),
                    )
                )

        # Insights DERIVED_FROM this chunk (inbound via InsightSource)
        insight_sources = (
            session.execute(
                select(InsightSource).where(InsightSource.chunk_id == chunk_uuid)
            )
            .scalars()
            .all()
        )

        for source in insight_sources:
            insight = session.execute(
                select(Insight).where(Insight.id == source.insight_id)
            ).scalar_one_or_none()

            if insight:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.INSIGHT,
                        entity_id=str(insight.id),
                        relation_type=RelationType.DERIVED_FROM,
                        relation_direction="inbound",
                        distance=1,
                        content_preview=insight.title,
                        metadata={
                            "insight_type": insight.insight_type,
                            "relevance_score": float(source.relevance_score)
                            if source.relevance_score
                            else None,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "insight", str(insight.id)
                        ),
                    )
                )

        # Reports that reference this chunk (inbound via ReportSource)
        report_sources = (
            session.execute(
                select(ReportSource).where(
                    and_(
                        ReportSource.source_type == "chunk",
                        ReportSource.source_id == chunk_uuid,
                    )
                )
            )
            .scalars()
            .all()
        )

        for source in report_sources:
            report = session.execute(
                select(Report).where(Report.id == source.report_id)
            ).scalar_one_or_none()

            if report:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.REPORT,
                        entity_id=str(report.id),
                        relation_type=RelationType.REFERENCES,
                        relation_direction="inbound",
                        distance=1,
                        content_preview=report.title,
                        metadata={
                            "report_type": report.report_type,
                            "status": report.status,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "report", str(report.id)
                        ),
                    )
                )

        # Sibling chunks in same document
        if chunk.document_id:
            siblings = (
                session.execute(
                    select(DocumentChunk)
                    .where(
                        and_(
                            DocumentChunk.document_id == chunk.document_id,
                            DocumentChunk.id != chunk_uuid,
                        )
                    )
                    .order_by(DocumentChunk.chunk_index)
                    .limit(5)  # Limit sibling chunks
                )
                .scalars()
                .all()
            )

            for sibling in siblings:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.CHUNK,
                        entity_id=str(sibling.id),
                        relation_type=RelationType.SIBLING_OF,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=sibling.content[: self.CONTENT_PREVIEW_LENGTH]
                        if sibling.content
                        else None,
                        metadata={"chunk_index": sibling.chunk_index},
                        urn=self._semantic_protocol.generate_urn(
                            "chunk", str(sibling.id)
                        ),
                    )
                )

        return neighbors

    def _get_mission_neighbors(
        self,
        session: Session,
        mission_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of a mission entity."""
        neighbors: list[RelatedEntity] = []

        try:
            mission_uuid = UUID(mission_id)
        except ValueError:
            return neighbors

        # Get the mission
        mission = session.execute(
            select(Mission).where(Mission.id == mission_uuid)
        ).scalar_one_or_none()

        if not mission:
            return neighbors

        # Mission BELONGS_TO project (outbound)
        if mission.project_id:
            project = session.execute(
                select(Project).where(Project.id == mission.project_id)
            ).scalar_one_or_none()

            if project:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.PROJECT,
                        entity_id=str(project.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=project.name,
                        metadata={"status": project.status},
                        urn=self._semantic_protocol.generate_urn(
                            "project", str(project.id)
                        ),
                    )
                )

        # Mission REFERENCES documents via result_document_ids (outbound)
        result_doc_ids = mission.result_document_ids or []
        for doc_id_str in result_doc_ids[:20]:  # Limit
            try:
                doc_uuid = (
                    UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
                )
                doc = session.execute(
                    select(Document).where(Document.id == doc_uuid)
                ).scalar_one_or_none()

                if doc:
                    neighbors.append(
                        RelatedEntity(
                            entity_type=EntityType.DOCUMENT,
                            entity_id=str(doc.id),
                            relation_type=RelationType.REFERENCES,
                            relation_direction="outbound",
                            distance=1,
                            content_preview=doc.name,
                            metadata={
                                "file_type": doc.file_type,
                                "source_type": doc.source_type,
                            },
                            urn=self._semantic_protocol.generate_urn(
                                "document", str(doc.id)
                            ),
                        )
                    )
            except (ValueError, TypeError):
                continue

        # Mission -> result_report (outbound)
        if mission.result_report_id:
            report = session.execute(
                select(Report).where(Report.id == mission.result_report_id)
            ).scalar_one_or_none()

            if report:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.REPORT,
                        entity_id=str(report.id),
                        relation_type=RelationType.REFERENCES,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=report.title,
                        metadata={
                            "report_type": report.report_type,
                            "status": report.status,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "report", str(report.id)
                        ),
                    )
                )

        # Sibling missions in same project
        if mission.project_id:
            siblings = (
                session.execute(
                    select(Mission)
                    .where(
                        and_(
                            Mission.project_id == mission.project_id,
                            Mission.id != mission_uuid,
                        )
                    )
                    .limit(10)
                )
                .scalars()
                .all()
            )

            for sibling in siblings:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.MISSION,
                        entity_id=str(sibling.id),
                        relation_type=RelationType.SIBLING_OF,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=sibling.title[: self.CONTENT_PREVIEW_LENGTH]
                        if sibling.title
                        else None,
                        metadata={
                            "mission_id": sibling.mission_id,
                            "status": sibling.status,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "mission", str(sibling.id)
                        ),
                    )
                )

        return neighbors

    def _get_insight_neighbors(
        self,
        session: Session,
        insight_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of an insight entity."""
        neighbors: list[RelatedEntity] = []

        try:
            insight_uuid = UUID(insight_id)
        except ValueError:
            return neighbors

        # Get the insight
        insight = session.execute(
            select(Insight).where(Insight.id == insight_uuid)
        ).scalar_one_or_none()

        if not insight:
            return neighbors

        # Insight BELONGS_TO project (outbound)
        if insight.project_id:
            project = session.execute(
                select(Project).where(Project.id == insight.project_id)
            ).scalar_one_or_none()

            if project:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.PROJECT,
                        entity_id=str(project.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=project.name,
                        metadata={"status": project.status},
                        urn=self._semantic_protocol.generate_urn(
                            "project", str(project.id)
                        ),
                    )
                )

        # Insight DERIVED_FROM chunks (outbound via InsightSource)
        sources = (
            session.execute(
                select(InsightSource).where(InsightSource.insight_id == insight_uuid)
            )
            .scalars()
            .all()
        )

        for source in sources:
            chunk = session.execute(
                select(DocumentChunk).where(DocumentChunk.id == source.chunk_id)
            ).scalar_one_or_none()

            if chunk:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.CHUNK,
                        entity_id=str(chunk.id),
                        relation_type=RelationType.DERIVED_FROM,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=chunk.content[: self.CONTENT_PREVIEW_LENGTH]
                        if chunk.content
                        else None,
                        metadata={
                            "chunk_index": chunk.chunk_index,
                            "relevance_score": float(source.relevance_score)
                            if source.relevance_score
                            else None,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "chunk", str(chunk.id)
                        ),
                    )
                )

        # Sibling insights in same project
        if insight.project_id:
            siblings = (
                session.execute(
                    select(Insight)
                    .where(
                        and_(
                            Insight.project_id == insight.project_id,
                            Insight.id != insight_uuid,
                        )
                    )
                    .limit(10)
                )
                .scalars()
                .all()
            )

            for sibling in siblings:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.INSIGHT,
                        entity_id=str(sibling.id),
                        relation_type=RelationType.SIBLING_OF,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=sibling.title,
                        metadata={
                            "insight_type": sibling.insight_type,
                            "validated": sibling.validated,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "insight", str(sibling.id)
                        ),
                    )
                )

        return neighbors

    def _get_report_neighbors(
        self,
        session: Session,
        report_id: str,
    ) -> list[RelatedEntity]:
        """Get neighbors of a report entity."""
        neighbors: list[RelatedEntity] = []

        try:
            report_uuid = UUID(report_id)
        except ValueError:
            return neighbors

        # Get the report
        report = session.execute(
            select(Report).where(Report.id == report_uuid)
        ).scalar_one_or_none()

        if not report:
            return neighbors

        # Report BELONGS_TO project (outbound)
        if report.project_id:
            project = session.execute(
                select(Project).where(Project.id == report.project_id)
            ).scalar_one_or_none()

            if project:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.PROJECT,
                        entity_id=str(project.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=project.name,
                        metadata={"status": project.status},
                        urn=self._semantic_protocol.generate_urn(
                            "project", str(project.id)
                        ),
                    )
                )

        # Report REFERENCES chunks/collections (outbound via ReportSource)
        sources = (
            session.execute(
                select(ReportSource).where(ReportSource.report_id == report_uuid)
            )
            .scalars()
            .all()
        )

        for source in sources:
            if source.source_type == "chunk":
                chunk = session.execute(
                    select(DocumentChunk).where(DocumentChunk.id == source.source_id)
                ).scalar_one_or_none()

                if chunk:
                    neighbors.append(
                        RelatedEntity(
                            entity_type=EntityType.CHUNK,
                            entity_id=str(chunk.id),
                            relation_type=RelationType.REFERENCES,
                            relation_direction="outbound",
                            distance=1,
                            content_preview=chunk.content[: self.CONTENT_PREVIEW_LENGTH]
                            if chunk.content
                            else None,
                            metadata={"chunk_index": chunk.chunk_index},
                            urn=self._semantic_protocol.generate_urn(
                                "chunk", str(chunk.id)
                            ),
                        )
                    )

        # Report parent relationship
        if report.parent_id:
            parent = session.execute(
                select(Report).where(Report.id == report.parent_id)
            ).scalar_one_or_none()

            if parent:
                neighbors.append(
                    RelatedEntity(
                        entity_type=EntityType.REPORT,
                        entity_id=str(parent.id),
                        relation_type=RelationType.BELONGS_TO,
                        relation_direction="outbound",
                        distance=1,
                        content_preview=parent.title,
                        metadata={
                            "report_type": parent.report_type,
                            "status": parent.status,
                        },
                        urn=self._semantic_protocol.generate_urn(
                            "report", str(parent.id)
                        ),
                    )
                )

        # Missions that produced this report (inbound)
        missions = (
            session.execute(
                select(Mission).where(Mission.result_report_id == report_uuid)
            )
            .scalars()
            .all()
        )

        for mission in missions:
            neighbors.append(
                RelatedEntity(
                    entity_type=EntityType.MISSION,
                    entity_id=str(mission.id),
                    relation_type=RelationType.REFERENCES,
                    relation_direction="inbound",
                    distance=1,
                    content_preview=mission.title[: self.CONTENT_PREVIEW_LENGTH]
                    if mission.title
                    else None,
                    metadata={
                        "mission_id": mission.mission_id,
                        "status": mission.status,
                    },
                    urn=self._semantic_protocol.generate_urn(
                        "mission", str(mission.id)
                    ),
                )
            )

        return neighbors

    def enrich_search_results(
        self,
        results: list[dict[str, Any]],
        *,
        include_related: bool = True,
        max_related_per_result: int = 5,
        allowed_project_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Enrich search results with related entities.

        Adds a 'related_entities' field to each result containing
        immediate neighbors in the entity graph.

        Args:
            results: Search results to enrich.
            include_related: Whether to include related entities.
            max_related_per_result: Max related entities per result.
            allowed_project_ids: Request-local project scope for graph expansion.

        Returns:
            Enriched results with related entities.
        """
        if not include_related:
            return results

        enriched = []
        with self._session_scope() as session:
            for result in results:
                enriched_result = dict(result)

                # Get URN or construct from chunk_id
                urn = result.get("urn")
                if not urn and result.get("chunk_id"):
                    urn = self._semantic_protocol.generate_urn(
                        "chunk", result["chunk_id"]
                    )

                if urn:
                    try:
                        expansion_kwargs: dict[str, Any] = {
                            "max_depth": 1,
                            "limit": max_related_per_result,
                            "session": session,
                        }
                        if allowed_project_ids is not None:
                            expansion_kwargs["allowed_project_ids"] = (
                                allowed_project_ids
                            )
                        expansion = self.get_related(urn, **expansion_kwargs)
                        enriched_result["related_entities"] = [
                            e.to_dict() for e in expansion.related_entities
                        ]
                    except (ValueError, Exception) as e:
                        logger.warning("Failed to expand relations for %s: %s", urn, e)
                        enriched_result["related_entities"] = []
                else:
                    enriched_result["related_entities"] = []

                enriched.append(enriched_result)

        return enriched


# Singleton instance
_relational_service: RelationalService | None = None


def get_relational_service() -> RelationalService:
    """Get or create the singleton relational service."""
    global _relational_service
    if _relational_service is None:
        _relational_service = RelationalService()
    return _relational_service


__all__ = [
    "RelationType",
    "EntityType",
    "RelatedEntity",
    "GraphExpansionResult",
    "RelationalService",
    "get_relational_service",
]
