"""Mission relationship traversal surface via SQL-backed lookups."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.insight import Insight, InsightSource
from app.models.mission import Mission
from app.schemas.relationships import (
    RelatedChunk,
    RelatedDocument,
    RelatedInsight,
    RelatedMission,
    RelationshipContextResponse,
    RelationshipEdgeInfo,
    RelationshipFilters,
    RelationshipTotals,
)
from app.services.cache_manager import CacheManager, get_cache_manager


class RelationshipServiceError(RuntimeError):
    """Raised when relationship traversal fails."""


class MissionRelationshipNotFound(RelationshipServiceError):
    """Raised when the requested mission cannot be located."""


@dataclass(frozen=True)
class _EvidenceLink:
    evidence_id: str
    chunk_id: UUID | None
    insight_id: UUID | None
    summary: str
    source: str
    relevance_score: float | None


@dataclass(frozen=True)
class _ChunkRecord:
    chunk: DocumentChunk
    document: Document | None


class RelationshipService:
    """Encapsulates relationship traversal, filtering, and caching."""

    SUPPORTED_ENTITY_TYPES: set[str] = {"documents", "insights", "chunks", "missions"}
    _ENTITY_ALIASES: dict[str, str] = {
        "document": "documents",
        "documents": "documents",
        "doc": "documents",
        "insight": "insights",
        "insights": "insights",
        "chunk": "chunks",
        "chunks": "chunks",
        "mission": "missions",
        "missions": "missions",
    }

    def __init__(self, cache_manager: CacheManager | None = None) -> None:
        self.cache_manager = cache_manager or get_cache_manager()

    def get_relationship_context(
        self,
        db: Session,
        mission_id: UUID,
        *,
        depth: int = 1,
        entity_types: Sequence[str] | None = None,
        min_relevance: float | None = None,
    ) -> RelationshipContextResponse:
        normalized_depth = self._normalize_depth(depth)
        normalized_types = self._normalize_entity_types(entity_types)
        normalized_relevance = self._normalize_relevance(min_relevance)

        mission = self._load_mission(db, mission_id)
        filters = RelationshipFilters(
            entity_types=normalized_types, min_relevance=normalized_relevance
        )

        cache_key = self.cache_manager.relationship_context_key(
            mission_id=str(mission.id),
            depth=normalized_depth,
            entity_types=tuple(filters.entity_types),
            min_relevance=filters.min_relevance,
        )

        def _loader() -> dict:
            context = self._build_context(db, mission, normalized_depth, filters)
            return context.model_dump(exclude={"cached"})

        payload, cache_hit = self.cache_manager.cached_value(
            "relationship_context", cache_key, _loader
        )
        return RelationshipContextResponse(**payload, cached=cache_hit)

    # ------------------------------------------------------------------
    # Core builders
    # ------------------------------------------------------------------
    def _build_context(
        self,
        db: Session,
        mission: Mission,
        depth: int,
        filters: RelationshipFilters,
    ) -> RelationshipContextResponse:
        context = mission.context if isinstance(mission.context, dict) else {}
        evidence_payload = self._normalize_evidence(context.get("evidence", []))
        chunk_ids = [link.chunk_id for link in evidence_payload if link.chunk_id]
        chunk_map, missing_chunk_ids = self._load_chunks(db, chunk_ids)

        include_chunk_preview = depth >= 2

        chunks = self._build_chunk_relationships(
            chunk_map,
            evidence_payload,
            include_preview=include_chunk_preview,
            min_relevance=filters.min_relevance,
        )
        documents = self._build_document_relationships(
            chunk_map,
            chunks,
            min_relevance=filters.min_relevance,
        )
        insights = self._build_insight_relationships(
            db,
            evidence_payload,
            chunk_map,
            min_relevance=filters.min_relevance,
        )
        related_missions = self._build_related_missions(
            db,
            mission,
            chunk_map=chunk_map,
            current_insights={
                link.insight_id for link in evidence_payload if link.insight_id
            },
            depth=depth,
        )

        applied_types = set(filters.entity_types or self.SUPPORTED_ENTITY_TYPES)
        if "documents" not in applied_types:
            documents = []
        if "insights" not in applied_types:
            insights = []
        if "chunks" not in applied_types:
            chunks = []
        if "missions" not in applied_types:
            related_missions = []

        documents.sort(key=lambda item: item.name.lower())
        insights.sort(key=lambda item: item.title.lower())
        chunks.sort(key=lambda item: (item.document_name or "", item.chunk_index))
        related_missions.sort(
            key=lambda item: item.title or item.mission_identifier or ""
        )

        totals = RelationshipTotals(
            documents=len(documents),
            insights=len(insights),
            chunks=len(chunks),
            missions=len(related_missions),
        )

        warnings: list[str] = []
        if missing_chunk_ids:
            warnings.append(
                f"{len(missing_chunk_ids)} evidence entries reference missing document chunks"
            )

        return RelationshipContextResponse(
            mission_id=mission.id,
            mission_identifier=mission.mission_id
            or self._extract_mission_identifier(
                mission.context if isinstance(mission.context, dict) else None
            ),
            project_id=mission.project_id,
            depth=depth,
            filters=filters,
            documents=documents,
            insights=insights,
            chunks=chunks,
            related_missions=related_missions,
            totals=totals,
            warnings=warnings,
            cached=False,
        )

    def _build_chunk_relationships(
        self,
        chunk_map: dict[UUID, _ChunkRecord],
        evidence_payload: Sequence[_EvidenceLink],
        *,
        include_preview: bool,
        min_relevance: float | None,
    ) -> list[RelatedChunk]:
        relationships: list[RelatedChunk] = []
        evidence_by_chunk: dict[UUID, list[_EvidenceLink]] = {}
        for link in evidence_payload:
            if not link.chunk_id:
                continue
            evidence_by_chunk.setdefault(link.chunk_id, []).append(link)

        for chunk_id, record in chunk_map.items():
            supporting = evidence_by_chunk.get(chunk_id, [])
            if not supporting:
                continue
            relevance_values = [
                link.relevance_score
                for link in supporting
                if link.relevance_score is not None
            ]
            best_relevance = max(relevance_values) if relevance_values else None
            effective_relevance = best_relevance if best_relevance is not None else 1.0
            if min_relevance is not None and effective_relevance < min_relevance:
                continue

            relationship = RelationshipEdgeInfo(
                relationship_type="evidence_chunk",
                evidence_ids=[link.evidence_id for link in supporting],
                summary=self._combine_summaries(supporting),
                source=supporting[0].source or None,
                relevance_score=best_relevance,
            )
            preview = self._preview(record.chunk.content) if include_preview else None
            relationships.append(
                RelatedChunk(
                    id=record.chunk.id,
                    document_id=record.chunk.document_id,
                    document_name=record.document.name if record.document else None,
                    chunk_index=record.chunk.chunk_index,
                    preview=preview,
                    relationship=relationship,
                )
            )
        return relationships

    def _build_document_relationships(
        self,
        chunk_map: dict[UUID, _ChunkRecord],
        chunk_relationships: Sequence[RelatedChunk],
        *,
        min_relevance: float | None,
    ) -> list[RelatedDocument]:
        grouped: dict[UUID, dict[str, object]] = {}
        for chunk_rel in chunk_relationships:
            grouped.setdefault(chunk_rel.document_id, {"chunks": []})
            grouped[chunk_rel.document_id]["chunks"].append(chunk_rel)

        documents: list[RelatedDocument] = []
        for document_id, payload in grouped.items():
            chunk_rels: list[RelatedChunk] = payload["chunks"]  # type: ignore[assignment]
            relevance_values = [
                rel.relationship.relevance_score
                for rel in chunk_rels
                if rel.relationship.relevance_score is not None
            ]
            best_relevance = max(relevance_values) if relevance_values else None
            effective_relevance = best_relevance if best_relevance is not None else 1.0
            if min_relevance is not None and effective_relevance < min_relevance:
                continue

            document = None
            if chunk_rels:
                chunk_id = chunk_rels[0].id
                record = chunk_map.get(chunk_id)
                document = record.document if record else None

            relationship = RelationshipEdgeInfo(
                relationship_type="evidence_document",
                evidence_ids=[
                    eid for rel in chunk_rels for eid in rel.relationship.evidence_ids
                ],
                summary=None,
                source=document.source_type if document else None,
                relevance_score=best_relevance,
            )
            documents.append(
                RelatedDocument(
                    id=document_id,
                    name=document.name if document else "Unknown Document",
                    file_type=document.file_type if document else None,
                    source_type=document.source_type if document else None,
                    evidence_chunks=len(chunk_rels),
                    chunk_ids=[rel.id for rel in chunk_rels],
                    relationship=relationship,
                )
            )
        return documents

    def _build_insight_relationships(
        self,
        db: Session,
        evidence_payload: Sequence[_EvidenceLink],
        chunk_map: dict[UUID, _ChunkRecord],
        *,
        min_relevance: float | None,
    ) -> list[RelatedInsight]:
        chunk_ids = list(chunk_map.keys())
        if not chunk_ids:
            return []

        # Map each insight to its supporting chunks and relevance scores
        insight_details: dict[UUID, dict[str, object]] = {}

        if chunk_ids:
            rows = (
                db.query(InsightSource)
                .filter(InsightSource.chunk_id.in_(chunk_ids))
                .all()
            )
            for row in rows:
                payload = insight_details.setdefault(
                    row.insight_id,
                    {
                        "chunk_ids": set(),
                        "relevance_scores": [],
                        "evidence_ids": [],
                    },
                )
                payload["chunk_ids"].add(row.chunk_id)  # type: ignore[assignment]
                if row.relevance_score is not None:
                    payload["relevance_scores"].append(float(row.relevance_score))  # type: ignore[assignment]

        for link in evidence_payload:
            if not link.insight_id:
                continue
            payload = insight_details.setdefault(
                link.insight_id,
                {
                    "chunk_ids": set(),
                    "relevance_scores": [],
                    "evidence_ids": [],
                },
            )
            if link.chunk_id:
                payload["chunk_ids"].add(link.chunk_id)  # type: ignore[assignment]
            if link.relevance_score is not None:
                payload["relevance_scores"].append(float(link.relevance_score))  # type: ignore[assignment]
            payload["evidence_ids"].append(link.evidence_id)  # type: ignore[assignment]

        if not insight_details:
            return []

        insights = (
            db.query(Insight).filter(Insight.id.in_(list(insight_details.keys()))).all()
        )
        indexed = {insight.id: insight for insight in insights}
        relationships: list[RelatedInsight] = []
        for insight_id, payload in insight_details.items():
            instance = indexed.get(insight_id)
            if not instance:
                continue
            relevance_scores: list[float] = payload["relevance_scores"]  # type: ignore[assignment]
            best_relevance = max(relevance_scores) if relevance_scores else None
            effective_relevance = best_relevance if best_relevance is not None else 1.0
            if min_relevance is not None and effective_relevance < min_relevance:
                continue
            evidence_ids: list[str] = payload["evidence_ids"]  # type: ignore[assignment]
            relationships.append(
                RelatedInsight(
                    id=insight_id,
                    title=instance.title,
                    insight_type=instance.insight_type,
                    validated=bool(instance.validated),
                    relationship=RelationshipEdgeInfo(
                        relationship_type="derived_insight",
                        evidence_ids=evidence_ids,
                        summary=None,
                        source=None,
                        relevance_score=best_relevance,
                    ),
                )
            )
        return relationships

    def _build_related_missions(
        self,
        db: Session,
        mission: Mission,
        *,
        chunk_map: dict[UUID, _ChunkRecord],
        current_insights: set[UUID],
        depth: int,
    ) -> list[RelatedMission]:
        if mission.project_id is None:
            return []
        siblings = (
            db.query(Mission)
            .filter(Mission.project_id == mission.project_id, Mission.id != mission.id)
            .order_by(Mission.created_at.desc())
            .all()
        )
        if not siblings:
            return []

        current_chunk_ids = set(chunk_map.keys())
        include_shared_stats = depth >= 2 and bool(current_chunk_ids)

        related: list[RelatedMission] = []
        for sibling in siblings:
            sibling_data = sibling.context if isinstance(sibling.context, dict) else {}
            shared_documents = 0
            shared_chunks = 0
            shared_insights = 0
            summary = None

            if include_shared_stats:
                sibling_evidence = self._normalize_evidence(
                    (sibling_data or {}).get("evidence", [])
                )
                sibling_chunk_ids = {
                    link.chunk_id for link in sibling_evidence if link.chunk_id
                }
                overlapping_chunk_ids = {
                    cid for cid in sibling_chunk_ids if cid in current_chunk_ids
                }
                shared_chunks = len(overlapping_chunk_ids)
                if overlapping_chunk_ids:
                    shared_documents = len(
                        {
                            chunk_map[cid].chunk.document_id
                            for cid in overlapping_chunk_ids
                            if cid in chunk_map
                        }
                    )
                sibling_insight_ids = {
                    link.insight_id for link in sibling_evidence if link.insight_id
                }
                shared_insights = len(current_insights & sibling_insight_ids)
                if shared_documents:
                    summary = f"Shares {shared_documents} documents"

            related.append(
                RelatedMission(
                    id=sibling.id,
                    mission_identifier=sibling.mission_id
                    or self._extract_mission_identifier(sibling_data),
                    title=sibling.title or self._extract_mission_title(sibling_data),
                    status=sibling.status or "draft",
                    completion_percentage=(sibling.execution_metadata or {}).get(
                        "completion_percentage", 0
                    )
                    or 0,
                    shared_documents=shared_documents,
                    shared_chunks=shared_chunks,
                    shared_insights=shared_insights,
                    relationship=RelationshipEdgeInfo(
                        relationship_type="project_peer",
                        evidence_ids=[],
                        summary=summary,
                        source=None,
                        relevance_score=None,
                    ),
                )
            )
        return related

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_depth(value: int) -> int:
        if value < 1:
            return 1
        if value > 2:
            return 2
        return value

    def _normalize_entity_types(self, entity_types: Sequence[str] | None) -> list[str]:
        if not entity_types:
            return sorted(self.SUPPORTED_ENTITY_TYPES)
        normalized: set[str] = set()
        for raw in entity_types:
            token = (raw or "").strip().lower()
            if not token:
                continue
            mapped = self._ENTITY_ALIASES.get(token)
            if mapped:
                normalized.add(mapped)
        return sorted(normalized or self.SUPPORTED_ENTITY_TYPES)

    @staticmethod
    def _normalize_relevance(value: float | None) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric < 0:
            return 0.0
        if numeric > 1:
            return 1.0
        return numeric

    @staticmethod
    def _safe_uuid(value: object) -> UUID | None:
        if not value:
            return None
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _normalize_evidence(self, payload: Iterable[dict]) -> list[_EvidenceLink]:
        normalized: list[_EvidenceLink] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or f"evidence-{index + 1}")
            chunk_id = self._safe_uuid(item.get("chunk_id"))
            insight_id = self._safe_uuid(item.get("insight_id"))
            summary = str(item.get("summary") or "")
            source = str(item.get("source") or "")
            relevance_raw = item.get("relevance_score")
            relevance_score = None
            if relevance_raw is not None:
                try:
                    relevance_score = max(0.0, min(1.0, float(relevance_raw)))
                except (TypeError, ValueError):
                    relevance_score = None
            normalized.append(
                _EvidenceLink(
                    evidence_id=evidence_id,
                    chunk_id=chunk_id,
                    insight_id=insight_id,
                    summary=summary,
                    source=source,
                    relevance_score=relevance_score,
                )
            )
        return normalized

    def _load_mission(self, db: Session, mission_id: UUID) -> Mission:
        mission = db.query(Mission).filter(Mission.id == mission_id).one_or_none()
        if not mission:
            raise MissionRelationshipNotFound(f"Mission {mission_id} not found")
        return mission

    def _load_chunks(
        self,
        db: Session,
        chunk_ids: Sequence[UUID | None],
    ) -> tuple[dict[UUID, _ChunkRecord], set[str]]:
        normalized_ids = {cid for cid in chunk_ids if cid}
        if not normalized_ids:
            return {}, set()
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.id.in_(list(normalized_ids)))
            .all()
        )
        chunk_map: dict[UUID, DocumentChunk] = {chunk.id: chunk for chunk in chunks}
        missing = {str(cid) for cid in normalized_ids if cid not in chunk_map}

        document_ids = {chunk.document_id for chunk in chunks}
        documents: dict[UUID, Document] = {}
        if document_ids:
            rows = db.query(Document).filter(Document.id.in_(list(document_ids))).all()
            documents = {row.id: row for row in rows}

        records: dict[UUID, _ChunkRecord] = {}
        for chunk in chunks:
            records[chunk.id] = _ChunkRecord(
                chunk=chunk, document=documents.get(chunk.document_id)
            )
        return records, missing

    @staticmethod
    def _preview(text: str | None, limit: int = 220) -> str | None:
        if not text:
            return None
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3]}..."

    @staticmethod
    def _combine_summaries(
        links: Sequence[_EvidenceLink], limit: int = 160
    ) -> str | None:
        summaries = [link.summary.strip() for link in links if link.summary.strip()]
        if not summaries:
            return None
        combined = "; ".join(summaries)
        if len(combined) <= limit:
            return combined
        return f"{combined[: limit - 3]}..."

    @staticmethod
    def _extract_mission_identifier(payload: dict | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        mission_id = payload.get("mission_id")
        return str(mission_id).strip() if mission_id else None

    @staticmethod
    def _extract_mission_title(payload: dict | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        title = payload.get("title")
        return str(title).strip() if title else None
