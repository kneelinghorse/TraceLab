"""Database serialization against DeepSearch claim/reclaim/terminal row updates."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.mission_log import MissionLog


class SQLAlchemyMissionLogRepository:
    def lock_mission(self, db: Session, mission_id: UUID) -> tuple[Any | None, datetime]:
        sqlite = db.get_bind().dialect.name == 'sqlite'
        if sqlite:
            # SQLite ignores FOR UPDATE. Reserve the writer before observing
            # ownership; a pre-existing SQLite transaction fails rather than
            # silently checking an unfenced snapshot. Routes pass fresh sessions.
            db.execute(text('BEGIN IMMEDIATE'))
        # Select only fence fields. Mission's eager result-report outer join
        # must not be part of FOR UPDATE (PostgreSQL rejects that nullable lock).
        mission = db.query(
            Mission.id, Mission.status, Mission.deepsearch_attempt_count,
            Mission.deepsearch_lease_owner, Mission.deepsearch_lease_token,
            Mission.deepsearch_lease_expires_at, Mission.deepsearch_result_key,
        ).filter(Mission.id == mission_id).with_for_update(of=Mission).first()
        if sqlite:
            now = datetime.fromisoformat(db.scalar(text("SELECT strftime('%Y-%m-%dT%H:%M:%f', 'now')"))).replace(tzinfo=UTC)
        else:
            # now()/transaction_timestamp() would be stale after a lock wait.
            now = db.scalar(select(func.clock_timestamp()))
        return mission, now

    def find_events(self, db: Session, mission_id: UUID, attempt: int, event_ids: list[UUID], sequences: list[int]) -> list[MissionLog]:
        return db.query(MissionLog).filter(
            MissionLog.mission_id == mission_id, MissionLog.attempt_count == attempt,
            or_(MissionLog.event_id.in_(event_ids), MissionLog.sequence.in_(sequences)),
        ).all()

    def has_versioned_logs(self, db: Session, mission_id: UUID) -> bool:
        return db.query(MissionLog.id).filter(MissionLog.mission_id == mission_id, MissionLog.attempt_count.isnot(None)).first() is not None

    def append(self, db: Session, rows: list[dict[str, Any]]) -> None:
        db.add_all(MissionLog(**row) for row in rows)
