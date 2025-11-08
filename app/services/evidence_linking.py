"""Helpers for linking insights to supporting document chunks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.insight import Insight, InsightSource
from app.models.chunk import DocumentChunk


@dataclass
class EvidenceLinkSummary:
    """Result metadata describing applied evidence links."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    missing_insights: int = 0
    missing_chunks: int = 0


class EvidenceLinkingService:
    """Synchronise `insight_sources` rows from Mission Protocol evidence entries."""

    def __init__(self, *, require_entities: bool = True) -> None:
        self.require_entities = require_entities

    def sync_from_evidence(self, db: Session, evidence_items: Iterable[Dict[str, Any]]) -> EvidenceLinkSummary:
        summary = EvidenceLinkSummary()

        for payload in evidence_items:
            insight_id = self._parse_uuid(payload.get("insight_id"))
            chunk_id = self._parse_uuid(payload.get("chunk_id"))
            if not insight_id or not chunk_id:
                summary.skipped += 1
                continue

            if not self._entity_exists(db, Insight, insight_id):
                summary.missing_insights += 1
                if self.require_entities:
                    summary.skipped += 1
                    continue

            if not self._entity_exists(db, DocumentChunk, chunk_id):
                summary.missing_chunks += 1
                if self.require_entities:
                    summary.skipped += 1
                    continue

            link = (
                db.query(InsightSource)
                .filter(InsightSource.insight_id == insight_id, InsightSource.chunk_id == chunk_id)
                .one_or_none()
            )

            if link:
                link.relevance_score = payload.get("relevance_score")
                summary.updated += 1
            else:
                link = InsightSource(
                    insight_id=insight_id,
                    chunk_id=chunk_id,
                    relevance_score=payload.get("relevance_score"),
                )
                db.add(link)
                summary.created += 1

        return summary

    @staticmethod
    def _parse_uuid(value: Any) -> Optional[UUID]:
        if not value:
            return None
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _entity_exists(db: Session, model: Any, entity_id: UUID) -> bool:
        return (
            db.query(model)
            .filter(model.id == entity_id)
            .with_entities(model.id)
            .scalar()
            is not None
        )

