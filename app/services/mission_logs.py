"""Owned, replay-safe observations; log delivery cannot change research outcomes."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ports.mission_logs import MissionLogRepository
from app.schemas.mission_logs import AttemptLogBatch, LogBatchAcknowledgement, LogBatchRequest

TERMINAL_LOG_STATUSES = frozenset({'completed', 'validation_failed', 'blocked'})


def _same(left: str | None, right: str) -> bool:
    return left is not None and hmac.compare_digest(left.encode(), right.encode())


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MissionLogService:
    def __init__(self, repository: MissionLogRepository):
        self.repository = repository

    def ingest(self, db: Session, mission_id: UUID, payload: AttemptLogBatch) -> LogBatchAcknowledgement:
        if payload.mission_id != mission_id:
            raise HTTPException(409, detail='Log batch mission does not match the request path.')
        mission, now = self.repository.lock_mission(db, mission_id)
        if mission is None:
            raise HTTPException(404, detail='Mission not found')
        token = payload.lease_token.get_secret_value()
        result_key = hashlib.sha256(f'tracelab-missions-lease-v2:{mission_id}:{payload.attempt_count}:{token}'.encode()).hexdigest()
        identity = mission.deepsearch_attempt_count == payload.attempt_count and _same(mission.deepsearch_lease_owner, payload.lease_owner)
        active = (mission.status == 'in_progress' and _same(mission.deepsearch_lease_token, token)
                  and mission.deepsearch_lease_expires_at is not None and _utc(mission.deepsearch_lease_expires_at) > _utc(now))
        terminal = (mission.status in TERMINAL_LOG_STATUSES and mission.deepsearch_lease_token is None
                    and _same(mission.deepsearch_result_key, result_key))
        if not identity or not (active or terminal):
            raise HTTPException(409, detail='Log attempt is no longer owned or its proof is invalid.')
        existing = self.repository.find_events(db, mission_id, payload.attempt_count,
            [entry.event_id for entry in payload.logs], [entry.sequence for entry in payload.logs])
        by_id = {entry.event_id: entry for entry in existing}
        by_sequence = {entry.sequence: entry for entry in existing}
        rows = []
        for entry in payload.logs:
            row = by_id.get(entry.event_id) or by_sequence.get(entry.sequence)
            if row is not None:
                if (row.event_id, row.sequence, row.level, row.message, row.source, _utc(row.logged_at)) != (
                    entry.event_id, entry.sequence, entry.level, entry.message, entry.source, entry.logged_at,
                ):
                    raise HTTPException(409, detail='Log event identity conflicts with recorded content.')
            else:
                rows.append({**entry.model_dump(), 'mission_id':mission_id, 'attempt_count':payload.attempt_count,
                             'logged_at':entry.logged_at.replace(tzinfo=None), 'created_at':_utc(now).replace(tzinfo=None)})
        # Validate every identity before any insert, so a late conflict cannot
        # partially append a batch. The lock serializes simultaneous retries.
        self.repository.append(db, rows)
        db.commit()
        return LogBatchAcknowledgement(mission_id=mission_id, attempt_count=payload.attempt_count,
            accepted=len(rows), replayed=len(payload.logs)-len(rows), event_ids=[entry.event_id for entry in payload.logs])

    def ingest_legacy(self, db: Session, mission_id: UUID, payload: LogBatchRequest) -> int:
        mission, now = self.repository.lock_mission(db, mission_id)
        if mission is None:
            raise HTTPException(404, detail='Mission not found')
        if (mission.status not in TERMINAL_LOG_STATUSES or not mission.deepsearch_result_key
                or self.repository.has_versioned_logs(db, mission_id)):
            raise HTTPException(409, detail='Legacy logs are restricted to terminal-only rollout delivery; use the v2 contract.')
        self.repository.append(db, [{'mission_id':mission_id, 'level':entry.level.upper()[:20], 'message':entry.message,
            'source':entry.source, 'logged_at':_utc(entry.logged_at or now).replace(tzinfo=None),
            'created_at':_utc(now).replace(tzinfo=None)} for entry in payload.logs])
        db.commit()
        return len(payload.logs)
