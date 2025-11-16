"""Faceted search helpers for filtering and facet aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.project import Project
from app.models.tag import DocumentTag, Tag


SessionFactory = Callable[[], Session]


def _normalize_sequence(values: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if not values:
        return ()
    normalized = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        normalized.append(text.lower())
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True)
class FacetFilters:
    """Normalized filter inputs shared across faceted search helpers."""

    project_id: Optional[str] = None
    document_types: Tuple[str, ...] = ()
    source_types: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @classmethod
    def from_kwargs(
        cls,
        *,
        project_id: Optional[str] = None,
        document_types: Optional[Sequence[str]] = None,
        source_types: Optional[Sequence[str]] = None,
        source_type: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> "FacetFilters":
        """Build filters from mixed singular/list inputs."""
        normalized_sources = list(_normalize_sequence(source_types))
        if source_type:
            text = str(source_type).strip()
            if text:
                normalized_sources.append(text.lower())
        project_value = str(project_id) if project_id else None
        return cls(
            project_id=project_value,
            document_types=_normalize_sequence(document_types),
            source_types=tuple(sorted(set(normalized_sources))),
            tags=_normalize_sequence(tags),
            date_from=date_from,
            date_to=date_to,
        )

    def requires_metadata(self) -> bool:
        """Return True when filters depend on document metadata."""
        return any(
            [
                self.document_types,
                self.source_types,
                self.tags,
                self.date_from is not None,
                self.date_to is not None,
            ]
        )

    def signature(self) -> str:
        """Canonical representation for caching keys."""
        return "|".join(
            [
                self.project_id or "*",
                ",".join(self.document_types) or "*",
                ",".join(self.source_types) or "*",
                ",".join(self.tags) or "*",
                self.date_from.isoformat() if self.date_from else "*",
                self.date_to.isoformat() if self.date_to else "*",
            ]
        )


class FacetedSearchService:
    """Apply advanced filters to queries and aggregate available facets."""

    def __init__(self, session_factory: SessionFactory = SessionLocal) -> None:
        self.session_factory = session_factory

    # ------------------------------------------------------------------
    # Filter application helpers
    # ------------------------------------------------------------------
    def apply_sql_filters(self, stmt, filters: FacetFilters):
        """Attach document-level filter clauses to a SQLAlchemy statement."""
        conditions = self._build_document_conditions(filters)
        if not conditions:
            return stmt
        if hasattr(stmt, "where"):
            for condition in conditions:
                stmt = stmt.where(condition)
            return stmt
        return stmt.filter(*conditions)

    def filter_chunks(self, chunks: List[Dict[str, Any]], filters: FacetFilters) -> List[Dict[str, Any]]:
        """Filter semantic or keyword chunks by document metadata."""
        if not chunks:
            return []

        doc_ids = {chunk.get("document_id") for chunk in chunks if chunk.get("document_id")}
        if not doc_ids:
            return [] if filters.requires_metadata() else [dict(chunk) for chunk in chunks]

        metadata = self._load_document_metadata(doc_ids)
        if not metadata:
            return [] if filters.requires_metadata() else [dict(chunk) for chunk in chunks]

        filtered: List[Dict[str, Any]] = []
        for chunk in chunks:
            document_id = chunk.get("document_id")
            info = metadata.get(document_id)
            if info is None:
                if filters.requires_metadata():
                    continue
                filtered.append(dict(chunk))
                continue
            if not self._matches_filters(info, filters):
                continue
            entry = dict(chunk)
            if info["document_type"] is not None:
                entry["document_type"] = info["document_type"]
            if info["source_type"] is not None:
                entry["source_type"] = info["source_type"]
            entry["collection_date"] = info["collection_date_iso"]
            entry["tags"] = list(info["tags"])
            filtered.append(entry)
        return filtered

    # ------------------------------------------------------------------
    # Facet aggregation
    # ------------------------------------------------------------------
    def get_facets(self, filters: FacetFilters) -> Dict[str, Any]:
        """Return facet counts for projects, document/source types, tags, and date ranges."""
        session = self.session_factory()
        try:
            project_rows = (
                session.query(Project.id, Project.name, func.count(Document.id))
                .join(Document, Document.project_id == Project.id)
            )
            project_rows = self._apply_query_filters(project_rows, filters)
            project_rows = project_rows.group_by(Project.id, Project.name).order_by(Project.name)
            projects = [
                {
                    "value": str(project_id),
                    "label": project_name or str(project_id),
                    "count": int(total or 0),
                }
                for project_id, project_name, total in project_rows
            ]

            document_rows = session.query(Document.file_type, func.count(Document.id))
            document_rows = self._apply_query_filters(document_rows, filters)
            document_rows = document_rows.group_by(Document.file_type).order_by(Document.file_type)
            document_types = [
                {"value": value, "label": value or "unknown", "count": int(total or 0)}
                for value, total in document_rows
                if value
            ]

            source_rows = session.query(Document.source_type, func.count(Document.id))
            source_rows = self._apply_query_filters(source_rows, filters)
            source_rows = source_rows.group_by(Document.source_type).order_by(Document.source_type)
            source_types = [
                {"value": value, "label": value or "unknown", "count": int(total or 0)}
                for value, total in source_rows
                if value
            ]

            tag_rows = (
                session.query(Tag.name, func.count(Document.id))
                .join(DocumentTag, DocumentTag.tag_id == Tag.id)
                .join(Document, Document.id == DocumentTag.document_id)
            )
            tag_rows = self._apply_query_filters(tag_rows, filters)
            tag_rows = tag_rows.group_by(Tag.name).order_by(Tag.name)
            tags = [
                {"value": name, "label": name, "count": int(total or 0)}
                for name, total in tag_rows
                if name
            ]

            date_row = session.query(
                func.min(Document.collection_date),
                func.max(Document.collection_date),
            )
            date_row = self._apply_query_filters(date_row, filters)
            min_date, max_date = date_row.first()
            date_range = {
                "min": min_date.isoformat() if min_date else None,
                "max": max_date.isoformat() if max_date else None,
            }
        finally:
            session.close()

        return {
            "projects": projects,
            "document_types": document_types,
            "source_types": source_types,
            "tags": tags,
            "date_range": date_range,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_query_filters(self, query, filters: FacetFilters):
        conditions = self._build_document_conditions(filters)
        if not conditions:
            return query
        return query.filter(*conditions)

    def _build_document_conditions(self, filters: FacetFilters):
        conditions = []
        project_uuid = self._parse_uuid(filters.project_id)
        if project_uuid:
            conditions.append(Document.project_id == project_uuid)
        if filters.document_types:
            conditions.append(func.lower(Document.file_type).in_(filters.document_types))
        if filters.source_types:
            conditions.append(func.lower(Document.source_type).in_(filters.source_types))
        if filters.date_from:
            conditions.append(Document.collection_date >= filters.date_from)
        if filters.date_to:
            conditions.append(Document.collection_date <= filters.date_to)
        if filters.tags:
            tag_exists = (
                select(DocumentTag.document_id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(DocumentTag.document_id == Document.id)
                .where(func.lower(Tag.name).in_(filters.tags))
                .limit(1)
            ).exists()
            conditions.append(tag_exists)
        return conditions

    def _load_document_metadata(self, doc_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        uuid_values: List[UUID] = []
        id_map: Dict[str, str] = {}
        for raw_id in doc_ids:
            try:
                parsed = UUID(str(raw_id))
            except ValueError:
                continue
            uuid_values.append(parsed)
            id_map[str(parsed)] = str(raw_id)

        if not uuid_values:
            return {}

        session = self.session_factory()
        metadata: Dict[str, Dict[str, any]] = {}
        try:
            rows = (
                session.query(
                    Document.id,
                    Document.file_type,
                    Document.source_type,
                    Document.collection_date,
                )
                .filter(Document.id.in_(uuid_values))
                .all()
            )
            for row in rows:
                key = str(row.id)
                metadata[id_map.get(key, key)] = {
                    "document_type": row.file_type,
                    "document_type_norm": (row.file_type or "").strip().lower() or None,
                    "source_type": row.source_type,
                    "source_type_norm": (row.source_type or "").strip().lower() or None,
                    "collection_date": row.collection_date,
                    "collection_date_iso": row.collection_date.isoformat() if row.collection_date else None,
                    "tags": [],
                    "tag_terms": set(),
                }

            tag_rows = (
                session.query(DocumentTag.document_id, Tag.name)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .filter(DocumentTag.document_id.in_(uuid_values))
                .all()
            )
            for document_id, tag_name in tag_rows:
                key = id_map.get(str(document_id), str(document_id))
                info = metadata.get(key)
                if not info:
                    continue
                if tag_name:
                    info["tags"].append(tag_name)
                    info["tag_terms"].add(tag_name.strip().lower())
        finally:
            session.close()
        return metadata

    def _matches_filters(self, info: Dict[str, Any], filters: FacetFilters) -> bool:
        if filters.document_types and info.get("document_type_norm") not in filters.document_types:
            return False
        if filters.source_types and info.get("source_type_norm") not in filters.source_types:
            return False
        if filters.date_from:
            collection_date = info.get("collection_date")
            if collection_date is None or collection_date < filters.date_from:
                return False
        if filters.date_to:
            collection_date = info.get("collection_date")
            if collection_date is None or collection_date > filters.date_to:
                return False
        if filters.tags:
            tag_terms = info.get("tag_terms") or set()
            if not tag_terms.intersection(filters.tags):
                return False
        return True

    @staticmethod
    def _parse_uuid(value: Optional[str]) -> Optional[UUID]:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None
