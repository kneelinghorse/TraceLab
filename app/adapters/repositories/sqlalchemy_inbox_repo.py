"""Scoped inbox sections and a per-user watermark, on PostgreSQL and SQLite."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Query, Session

from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.user import User
from app.models.user_inbox_state import UserInboxState
from app.schemas.inbox import DEFAULT_LOOKBACK_SECONDS, InboxCounts, InboxItem, InboxPage, InboxSection, InboxSummary
from app.services.evidence_scope import evidence_activity_groups, evidence_href, scoped_query
from app.services.mission_attention import attention_reason_clauses, reviewed_clause

# completed_at wherever the worker or API set it; updated_at churns during result
# materialization, so it is only the fallback for rows that never completed.
OCCURRED_AT = func.coalesce(Mission.completed_at, Mission.updated_at)
LAST_CREATED_AT = func.max(LedgerEntry.created_at)


class SQLAlchemyInboxRepository:
    def seen_through(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> datetime:
        """The stored watermark, else a first-visit window bounded by account age and seven days."""
        row = db.get(UserInboxState, user.user_id)
        if row is not None:
            return row.seen_through
        created_at = db.query(User.created_at).filter(User.id == user.user_id).scalar()
        default = now - timedelta(seconds=DEFAULT_LOOKBACK_SECONDS)
        return max(created_at, default) if created_at is not None else default

    def _mission_clauses(self, user: AuthenticatedUser, *, now: datetime, seen: datetime) -> dict[str, Any]:
        reasons = attention_reason_clauses(user.user_id, now=now)
        return {
            "failures": and_(or_(reasons["validation_failed"], reasons["blocked"]), seen < OCCURRED_AT),
            "completions": and_(reasons["unreviewed"], seen < OCCURRED_AT),
        }

    def summary(self, db: Session, user: AuthenticatedUser, *, now: datetime) -> InboxSummary:
        seen = self.seen_through(db, user, now=now)
        unread = self._mission_clauses(user, now=now, seen=seen)
        failures, completions = scoped_query(db, user, Mission).with_entities(
            func.count(case((unread["failures"], 1))), func.count(case((unread["completions"], 1))),
        ).one()
        evidence = evidence_activity_groups(db, user).having(seen < LAST_CREATED_AT).count()
        return InboxSummary(
            generated_at=now, seen_through=seen,
            unread=InboxCounts(failures=failures, completions=completions, evidence=evidence,
                               total=failures + completions + evidence),
        )

    def _missions(self, db: Session, user: AuthenticatedUser, section: InboxSection, *, now: datetime) -> Query[Any]:
        reasons = attention_reason_clauses(user.user_id, now=now)
        query = scoped_query(db, user, Mission)
        if section == "failures":
            return query.filter(or_(reasons["validation_failed"], reasons["blocked"]))
        return query.filter(Mission.status == "completed")

    def list(
        self, db: Session, user: AuthenticatedUser, *, now: datetime, section: InboxSection,
        page: int, page_size: int, unread_only: bool,
    ) -> InboxPage:
        seen = self.seen_through(db, user, now=now)
        offset = (page - 1) * page_size
        if section == "evidence":
            groups = evidence_activity_groups(db, user)
            if unread_only:
                groups = groups.having(seen < LAST_CREATED_AT)
            total = groups.count()
            rows = (
                groups.order_by(
                    LAST_CREATED_AT.desc(), LedgerEntry.project_id, LedgerEntry.session_key, LedgerEntry.mission_id,
                    LedgerEntry.origin,
                )
                .offset(offset)
                .limit(page_size)
                .all()
            )
            items = [
                InboxItem(
                    section=section, id=f"{g.project_id}:{g.mission_id or ''}:{g.session_key}:{g.origin}",
                    title=g.session_key, label=g.origin, occurred_at=g.last_created_at,
                    unread=g.last_created_at > seen, href=evidence_href(g.project_id, g.mission_id, g.session_key),
                    entry_count=g.entry_count, project_id=g.project_id, mission_id=g.mission_id,
                    session_key=g.session_key, origin=g.origin,
                )
                for g in rows
            ]
            return InboxPage(section=section, generated_at=now, seen_through=seen, total=total, items=items)

        query = self._missions(db, user, section, now=now)
        if unread_only:
            query = query.filter(self._mission_clauses(user, now=now, seen=seen)[section])
        total = query.count()
        rows = (
            query.with_entities(
                Mission.id, Mission.mission_id, Mission.title, Mission.status, Mission.updated_at, Mission.completed_at,
                reviewed_clause(user.user_id).label("reviewed"),
            )
            .order_by(OCCURRED_AT.desc(), Mission.id)
            .offset(offset)
            .limit(page_size)
            .all()
        )
        items = []
        for row in rows:
            occurred_at = row.completed_at or row.updated_at
            reviewed = bool(row.reviewed) if section == "completions" else None
            items.append(InboxItem(
                section=section, id=str(row.id), title=row.title, label=row.mission_id, status=row.status,
                occurred_at=occurred_at, updated_at=row.updated_at, unread=occurred_at > seen and not reviewed,
                href=f"/missions/{row.id}", reviewed=reviewed,
            ))
        return InboxPage(section=section, generated_at=now, seen_through=seen, total=total, items=items)

    def mark_seen(self, db: Session, user: AuthenticatedUser, seen_through: datetime, *, now: datetime) -> datetime:
        insert = pg_insert(UserInboxState) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(UserInboxState)
        statement = insert.values(user_id=user.user_id, seen_through=seen_through, updated_at=now)
        # Monotonic under concurrency: an older value never wins the upsert.
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id"],
                set_={"seen_through": statement.excluded.seen_through, "updated_at": statement.excluded.updated_at},
                where=UserInboxState.seen_through < statement.excluded.seen_through,
            )
        )
        db.commit()
        return db.query(UserInboxState.seen_through).filter(UserInboxState.user_id == user.user_id).scalar()
