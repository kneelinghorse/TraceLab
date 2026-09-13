"""Scoped COUNT queries and bounded summaries for Home, on PostgreSQL and SQLite."""

from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Query, Session, load_only, noload

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import MISSION_STATUSES, Mission
from app.models.mission_review import MissionReview
from app.models.project import Project
from app.models.report import Report
from app.schemas.home import (
    HomeEvidenceActivity,
    HomeMission,
    HomeMissionTotals,
    HomeRecent,
    HomeResponse,
    HomeSection,
)
from app.services.home import observed_progress
from app.services.mission_attention import STALLED_AFTER_SECONDS, attention_predicates

SECTION_LIMIT = 6


def _scoped(db: Session, user: AuthenticatedUser, model: type) -> Query[Any]:
    query: Query[Any] = db.query(model)
    scope = accessible_filter(user, model, db)
    return query.filter(scope) if scope is not None else query


def _evidence_href(project_id, mission_id=None, session_key=None):
    params = {"project_id": str(project_id)}
    if mission_id:
        params["mission_id"] = str(mission_id)
    if session_key:
        params["session_key"] = session_key
    return "/evidence?" + urlencode(params)


class SQLAlchemyHomeRepository:
    def snapshot(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> HomeResponse:
        missions = _scoped(db, user, Mission)
        reports = _scoped(db, user, Report)
        projects = _scoped(db, user, Project).filter(Project.deleted_at.is_(None))

        # Match the ledger's project gate AND child-row policy, including its
        # project-owner allow path. Row ownership alone cannot bypass the parent.
        evidence = db.query(LedgerEntry).filter(
            LedgerEntry.project_id.in_(projects.with_entities(Project.id).statement),
        )
        evidence_scope = accessible_filter(user, LedgerEntry, db)
        if evidence_scope is not None:
            evidence = evidence.filter(
                or_(
                    evidence_scope,
                    LedgerEntry.project_id.in_(select(Project.id).where(Project.owner_id == user.user_id)),
                )
            )
        # Home links into a mission-filtered ledger; never disclose a mission ID
        # the caller cannot read, even if individual claims happen to be owned.
        evidence = evidence.filter(
            or_(
                LedgerEntry.mission_id.is_(None),
                LedgerEntry.mission_id.in_(missions.with_entities(Mission.id).statement),
            )
        )

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
                evidence_href=_evidence_href(row.project_id, row.id) if evidence_count else None,
            )

        groups = evidence.with_entities(
            LedgerEntry.project_id,
            LedgerEntry.mission_id,
            LedgerEntry.session_key,
            LedgerEntry.origin,
            func.count(LedgerEntry.id).label("entry_count"),
            func.max(LedgerEntry.created_at).label("last_created_at"),
        ).group_by(LedgerEntry.project_id, LedgerEntry.mission_id, LedgerEntry.session_key, LedgerEntry.origin)
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
                        href=_evidence_href(g.project_id, g.mission_id, g.session_key),
                    )
                    for g in activity
                ],
            ),
        )

    def review_completion(self, db: Session, user: AuthenticatedUser, mission_id: UUID, updated_at: datetime) -> None:
        row = _scoped(db, user, Mission).options(noload("*")).filter(Mission.id == mission_id).with_for_update().first()
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
