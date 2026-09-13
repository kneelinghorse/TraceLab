"""Whole-database aggregates; callers must pass the admin-only route boundary."""

from datetime import UTC, datetime
from typing import get_args

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerNote, LedgerSource
from app.models.graph_edge import GraphEdge
from app.models.ingestion_job import IngestionJob
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.schemas.admin_stats import AdminStatsResponse, RecentAdminMission, StateCounts
from app.schemas.mission import MissionStatus


class SQLAlchemyAdminStatsRepository:
    def snapshot(self, db: Session) -> AdminStatsResponse:
        def count(model) -> int:
            return int(db.query(func.count()).select_from(model).scalar() or 0)

        mission_counts = dict.fromkeys(get_args(MissionStatus), 0)
        mission_counts.update(
            {
                str(status): int(total)
                for status, total in db.query(Mission.status, func.count()).group_by(Mission.status)
            }
        )
        ingestion_counts = {
            str(status): int(total)
            for status, total in db.query(IngestionJob.status, func.count()).group_by(IngestionJob.status)
        }
        edge_counts = {
            str(kind): int(total)
            for kind, total in db.query(GraphEdge.edge_type, func.count()).group_by(GraphEdge.edge_type)
        }
        recent = (
            db.query(Mission.id, Mission.mission_id, Mission.title, Mission.status, Mission.updated_at)
            .order_by(Mission.updated_at.desc(), Mission.id)
            .limit(6)
            .all()
        )
        return AdminStatsResponse(
            generated_at=datetime.now(UTC),
            missions=StateCounts(total=count(Mission), by_status=mission_counts),
            projects=db.query(Project).filter(Project.deleted_at.is_(None)).count(),
            documents=db.query(Document).filter(Document.deleted_at.is_(None)).count(),
            chunks=db.query(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.deleted_at.is_(None))
            .count(),
            reports=count(Report),
            ingestion_jobs=StateCounts(total=count(IngestionJob), by_status=ingestion_counts),
            graph_edges=count(GraphEdge),
            graph_edges_by_type=edge_counts,
            evidence_entries=count(LedgerEntry),
            evidence_sources=count(LedgerSource),
            evidence_notes=count(LedgerNote),
            recent_missions=[
                RecentAdminMission(
                    id=m.id, mission_id=m.mission_id, title=m.title, status=m.status, updated_at=m.updated_at
                )
                for m in recent
            ],
        )
