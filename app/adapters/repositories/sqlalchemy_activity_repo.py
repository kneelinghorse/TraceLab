"""Recency stream over missions, reports and evidence groups, scoped before counting."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased

from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.report import Report
from app.models.user_item_view import UserItemView
from app.schemas.activity import ActivityItem, ActivityPage, ActivitySummary, ViewedItem
from app.services.evidence_scope import evidence_activity_groups, evidence_href, scoped_query

EVIDENCE_NAMESPACE = uuid.UUID("2f6c0b7e-4b1a-4f6e-9a0c-6d3b1c9e7a51")

# The moment an item last "happened": a completion completes, a run starts, a
# queue entry queues; every other status change only has updated_at.
MISSION_OCCURRED_AT = case(
    (Mission.status == "completed", func.coalesce(Mission.completed_at, Mission.updated_at)),
    (Mission.status == "in_progress", func.coalesce(Mission.started_at, Mission.updated_at)),
    (Mission.status == "queued", func.coalesce(Mission.queued_at, Mission.created_at)),
    else_=Mission.updated_at,
)


def evidence_item_id(project_id, mission_id, session_key: str, origin: str) -> uuid.UUID:
    """A stable id for an evidence group, which has no row of its own."""
    return uuid.uuid5(EVIDENCE_NAMESPACE, f"{project_id}:{mission_id or ''}:{session_key}:{origin}")


def _origin_label(origin: str) -> str:
    return "DeepSearch" if origin == "deepsearch-worker" else "Research agent"


class SQLAlchemyActivityRepository:
    def _missions(self, db: Session, user: AuthenticatedUser):
        view = aliased(UserItemView)
        query = scoped_query(db, user, Mission).outerjoin(
            view, and_(view.user_id == user.user_id, view.item_type == "mission", view.item_id == Mission.id),
        )
        new = or_(view.item_id.is_(None), view.occurred_at < MISSION_OCCURRED_AT)
        return query, new

    def _reports(self, db: Session, user: AuthenticatedUser):
        view = aliased(UserItemView)
        query = scoped_query(db, user, Report).outerjoin(
            view, and_(view.user_id == user.user_id, view.item_type == "report", view.item_id == Report.id),
        )
        new = or_(view.item_id.is_(None), view.occurred_at < Report.updated_at)
        return query, new

    def _evidence(self, db: Session, user: AuthenticatedUser, *, limit: int | None = None) -> list[ActivityItem]:
        groups = evidence_activity_groups(db, user).order_by(
            func.max(LedgerEntry.created_at).desc(), LedgerEntry.project_id, LedgerEntry.session_key,
            LedgerEntry.mission_id, LedgerEntry.origin,
        )
        rows = (groups.limit(limit) if limit else groups).all()
        viewed = dict(
            db.query(UserItemView.item_id, UserItemView.occurred_at)
            .filter(UserItemView.user_id == user.user_id, UserItemView.item_type == "evidence")
            .all()
        )
        items = []
        for g in rows:
            item_id = evidence_item_id(g.project_id, g.mission_id, g.session_key, g.origin)
            seen = viewed.get(item_id)
            items.append(ActivityItem(
                type="evidence", id=item_id,
                title=f"{g.entry_count:,} evidence entries · {_origin_label(g.origin)}",
                subtitle=g.session_key, status=None, occurred_at=g.last_created_at,
                href=evidence_href(g.project_id, g.mission_id, g.session_key),
                new=seen is None or seen < g.last_created_at,
            ))
        return items

    def page(
        self, db: Session, user: AuthenticatedUser, *, now: datetime, page: int = 1, page_size: int = 20
    ) -> ActivityPage:
        window = page * page_size
        missions, mission_new = self._missions(db, user)
        reports, report_new = self._reports(db, user)
        mission_rows = (
            missions.with_entities(
                Mission.id, Mission.mission_id, Mission.title, Mission.status,
                MISSION_OCCURRED_AT.label("occurred_at"), mission_new.label("new"),
            )
            .order_by(MISSION_OCCURRED_AT.desc(), Mission.id).limit(window).all()
        )
        report_rows = (
            reports.with_entities(Report.id, Report.title, Report.status, Report.updated_at, report_new.label("new"))
            .order_by(Report.updated_at.desc(), Report.id).limit(window).all()
        )
        items = [
            ActivityItem(type="mission", id=r.id, title=r.title, subtitle=r.mission_id, status=r.status,
                         occurred_at=r.occurred_at, href=f"/missions/{r.id}", new=bool(r.new))
            for r in mission_rows
        ] + [
            ActivityItem(type="report", id=r.id, title=r.title, subtitle=None, status=r.status,
                         occurred_at=r.updated_at, href=f"/reports/{r.id}", new=bool(r.new))
            for r in report_rows
        ] + self._evidence(db, user, limit=window)
        items.sort(key=lambda i: (i.occurred_at, i.type, str(i.id)), reverse=True)
        total = missions.count() + reports.count() + evidence_activity_groups(db, user).count()
        summary = self.summary(db, user, now=now)
        return ActivityPage(
            generated_at=now, page=page, page_size=page_size, total=total, new_total=summary.new_total,
            items=items[(page - 1) * page_size : page * page_size],
        )

    def summary(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> ActivitySummary:
        missions, mission_new = self._missions(db, user)
        reports, report_new = self._reports(db, user)
        by_type = {
            "mission": missions.filter(mission_new).count(),
            "report": reports.filter(report_new).count(),
            "evidence": sum(1 for item in self._evidence(db, user) if item.new),
        }
        return ActivitySummary(generated_at=now, new_total=sum(by_type.values()), by_type=by_type)

    def mark_viewed(self, db: Session, user: AuthenticatedUser, items: list[ViewedItem], *, now: datetime) -> int:
        readable: set[tuple[str, uuid.UUID]] = set()
        mission_ids = [i.id for i in items if i.type == "mission"]
        report_ids = [i.id for i in items if i.type == "report"]
        if mission_ids:
            rows = scoped_query(db, user, Mission).with_entities(Mission.id).filter(Mission.id.in_(mission_ids)).all()
            readable.update(("mission", r[0]) for r in rows)
        if report_ids:
            rows = scoped_query(db, user, Report).with_entities(Report.id).filter(Report.id.in_(report_ids)).all()
            readable.update(("report", r[0]) for r in rows)
        evidence_ids = {item.id for item in self._evidence(db, user)}
        readable.update(("evidence", i.id) for i in items if i.type == "evidence" and i.id in evidence_ids)
        values = {}
        for item in items:
            if (item.type, item.id) in readable:
                key = (item.type, item.id)
                values[key] = max(values.get(key, item.occurred_at), item.occurred_at)
        if not values:
            return 0
        insert = pg_insert(UserItemView) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(UserItemView)
        statement = insert.values([
            {"user_id": user.user_id, "item_type": t, "item_id": i, "occurred_at": occurred, "viewed_at": now}
            for (t, i), occurred in values.items()
        ])
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "item_type", "item_id"],
                set_={"occurred_at": statement.excluded.occurred_at, "viewed_at": statement.excluded.viewed_at},
                where=UserItemView.occurred_at <= statement.excluded.occurred_at,
            )
        )
        db.commit()
        return len(values)
