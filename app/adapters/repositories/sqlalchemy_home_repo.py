"""Scoped COUNT queries and bounded summaries for Home, on PostgreSQL and SQLite."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, load_only, noload

from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import MISSION_STATUSES, Mission
from app.models.mission_review import MissionReview
from app.models.project import Project
from app.models.report import Report
from app.models.user_favorite import UserFavorite
from app.schemas.home import (
    HomeAttention,
    HomeEvidenceActivity,
    HomeMission,
    HomeMissionTotals,
    HomeRecent,
    HomeResponse,
    HomeSection,
)
from app.services.evidence_scope import evidence_activity_groups, evidence_href, readable_evidence, scoped_query
from app.services.home import observed_progress
from app.services.mission_attention import STALLED_AFTER_SECONDS, attention_predicates, attention_reason_clauses

SECTION_LIMIT = 6


class SQLAlchemyHomeRepository:
    def attention(
        self, db: Session, user: AuthenticatedUser, *, now: datetime, project_id: UUID | None = None,
    ) -> HomeAttention:
        query = scoped_query(db, user, Mission)
        if project_id is not None:
            query = query.filter(Mission.project_id == project_id)
        reasons = attention_reason_clauses(user.user_id, now=now)
        counts = query.with_entities(*(func.count(case((clause, 1))) for clause in reasons.values())).one()
        by_reason = dict(zip(reasons, counts, strict=True))
        return HomeAttention(
            generated_at=now, stalled_after_seconds=STALLED_AFTER_SECONDS,
            total=sum(counts), by_reason=by_reason,
            dashboards=[{"key": "at_risk", "total": sum(counts[:3])}, {"key": "unreviewed", "total": by_reason["unreviewed"]}],
        )

    def favorites(
        self, db: Session, user: AuthenticatedUser, *, page: int = 1, page_size: int = SECTION_LIMIT,
        project_id: UUID | None = None,
    ) -> HomeSection[HomeRecent]:
        query = scoped_query(db, user, Project).join(UserFavorite, UserFavorite.entity_id == Project.id).filter(
            Project.deleted_at.is_(None), UserFavorite.user_id == user.user_id, UserFavorite.entity_type == "project",
        )
        if project_id is not None:
            query = query.filter(Project.id == project_id)
        total = query.count()
        rows = query.order_by(UserFavorite.created_at.desc(), Project.id).offset((page - 1) * page_size).limit(page_size).all()
        return HomeSection(total=total, items=[
            HomeRecent(id=row.id, title=row.name, updated_at=row.updated_at, href=f"/projects/{row.id}") for row in rows
        ])

    def set_favorite(self, db: Session, user: AuthenticatedUser, project_id: UUID, *, favorite: bool) -> None:
        if favorite:
            project = scoped_query(db, user, Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
            if project is None:
                raise LookupError("Project not found.")
            insert = pg_insert(UserFavorite) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(UserFavorite)
            db.execute(insert.values(user_id=user.user_id, entity_type="project", entity_id=project_id).on_conflict_do_nothing())
        else:
            db.query(UserFavorite).filter(
                UserFavorite.user_id == user.user_id, UserFavorite.entity_type == "project", UserFavorite.entity_id == project_id,
            ).delete(synchronize_session=False)
        db.commit()

    def snapshot(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> HomeResponse:
        missions = scoped_query(db, user, Mission)
        reports = scoped_query(db, user, Report)
        projects = scoped_query(db, user, Project).filter(Project.deleted_at.is_(None))
        # The inbox shares this exact ledger scope (app/services/evidence_scope.py).
        evidence = readable_evidence(db, user)

        by_status = dict.fromkeys(sorted(MISSION_STATUSES), 0)
        by_status.update(
            {
                status: count
                for status, count in missions.with_entities(Mission.status, func.count(Mission.id))
                .group_by(Mission.status)
                .all()
            }
        )
        predicate, rank = attention_predicates(user.user_id, now=now)
        attention = missions.filter(predicate)
        active = missions.filter(Mission.status == "in_progress")
        columns: list[Any] = [
            Mission.id,
            Mission.mission_id,
            Mission.title,
            Mission.status,
            Mission.project_id,
            Mission.updated_at,
            Mission.started_at,
            Mission.completed_at,
            Mission.execution_metadata,
            Mission.result_report_id,
        ]
        attention_rows = (
            attention.options(noload("*"), load_only(*columns))
            .order_by(rank, Mission.updated_at.desc(), Mission.id)
            .limit(SECTION_LIMIT)
            .all()
        )
        active_rows = (
            active.options(noload("*"), load_only(*columns))
            .order_by(Mission.updated_at.desc(), Mission.id)
            .limit(SECTION_LIMIT)
            .all()
        )
        shown_ids = [m.id for m in attention_rows + active_rows]
        evidence_counts = dict(
            evidence.filter(LedgerEntry.mission_id.in_(shown_ids))
            .with_entities(LedgerEntry.mission_id, func.count(LedgerEntry.id))
            .group_by(LedgerEntry.mission_id)
            .all()
        )
        result_ids = [m.result_report_id for m in attention_rows + active_rows if m.result_report_id]
        readable_reports = {r[0] for r in reports.with_entities(Report.id).filter(Report.id.in_(result_ids)).all()}

        def item(row, *, attention_item=False):
            reason = None
            if attention_item:
                reason = {"queued": "stalled", "completed": "unreviewed"}.get(row.status, row.status)
            evidence_count = evidence_counts.get(row.id, 0)
            return HomeMission(
                id=row.id,
                mission_id=row.mission_id,
                title=row.title,
                status=row.status,
                updated_at=row.updated_at,
                started_at=row.started_at,
                completed_at=row.completed_at,
                reason=reason,
                progress=observed_progress(row.execution_metadata),
                report_id=row.result_report_id if row.result_report_id in readable_reports else None,
                evidence_count=evidence_count,
                evidence_href=evidence_href(row.project_id, row.id) if evidence_count else None,
            )

        groups = evidence_activity_groups(db, user)
        activity = (
            groups.order_by(
                func.max(LedgerEntry.created_at).desc(),
                LedgerEntry.project_id,
                LedgerEntry.session_key,
                LedgerEntry.mission_id,
                LedgerEntry.origin,
            )
            .limit(SECTION_LIMIT)
            .all()
        )
        report_rows = (
            reports.with_entities(Report.id, Report.title, Report.updated_at)
            .order_by(Report.updated_at.desc(), Report.id)
            .limit(SECTION_LIMIT)
            .all()
        )
        project_rows = (
            projects.with_entities(Project.id, Project.name, Project.updated_at)
            .order_by(Project.updated_at.desc(), Project.id)
            .limit(SECTION_LIMIT)
            .all()
        )
        return HomeResponse(
            generated_at=now,
            favorites=self.favorites(db, user),
            stalled_after_seconds=STALLED_AFTER_SECONDS,
            missions=HomeMissionTotals(total=sum(by_status.values()), by_status=by_status),
            attention=HomeSection(
                total=attention.count(), items=[item(m, attention_item=True) for m in attention_rows]
            ),
            active_runs=HomeSection(total=active.count(), items=[item(m) for m in active_rows]),
            recent_reports=HomeSection(
                total=reports.count(),
                items=[
                    HomeRecent(id=r.id, title=r.title, updated_at=r.updated_at, href=f"/reports/{r.id}")
                    for r in report_rows
                ],
            ),
            recent_projects=HomeSection(
                total=projects.count(),
                items=[
                    HomeRecent(id=p.id, title=p.name, updated_at=p.updated_at, href=f"/projects/{p.id}")
                    for p in project_rows
                ],
            ),
            evidence_activity=HomeSection(
                total=groups.count(),
                items=[
                    HomeEvidenceActivity(
                        project_id=g.project_id,
                        mission_id=g.mission_id,
                        session_key=g.session_key,
                        origin=g.origin,
                        entry_count=g.entry_count,
                        last_created_at=g.last_created_at,
                        href=evidence_href(g.project_id, g.mission_id, g.session_key),
                    )
                    for g in activity
                ],
            ),
        )

    def review_completion(self, db: Session, user: AuthenticatedUser, mission_id: UUID, updated_at: datetime) -> None:
        row = scoped_query(db, user, Mission).options(noload("*")).filter(Mission.id == mission_id).with_for_update().first()
        if row is None:
            raise LookupError("Mission not found.")
        if row.status != "completed" or row.updated_at != updated_at:
            raise ValueError("The mission changed. Refresh Home and review its current result.")
        insert = (
            pg_insert(MissionReview) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(MissionReview)
        )
        statement = insert.values(
            user_id=user.user_id,
            mission_id=mission_id,
            mission_updated_at=updated_at,
            reviewed_at=datetime.utcnow(),
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "mission_id"],
                set_={
                    "mission_updated_at": statement.excluded.mission_updated_at,
                    "reviewed_at": statement.excluded.reviewed_at,
                },
            )
        )
        db.commit()
