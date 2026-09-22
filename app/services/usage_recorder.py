"""Record what a mission costs, so metering is possible later (METER-0, decision #522).

Three write paths, all idempotent on (mission_id, kind):

* ``record_mission_submission`` at submit: the queued row, attributed to the
  user who pressed submit. This is the only moment the submitter is known.
* ``record_mission_terminal`` under the materialization lock: the same row,
  filled from the accounting DeepSearch writes into ``execution_metadata``.
* ``sweep_unrecorded_terminal_missions`` from the reconciler tick: any
  terminal mission with no row yet, attributed to the project owner because
  the submitter is unknown for history. This is also the backfill.

Librarian calls record one row each through ``record_librarian_usage``.
Nothing here limits, blocks or bills; that is the whole point of the mission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.usage_record import (
    ATTRIBUTION_CALLER,
    ATTRIBUTION_PROJECT_OWNER,
    ATTRIBUTION_SUBMITTER,
    USAGE_KIND_DEEPSEARCH_RUN,
    UsageRecord,
)

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "validation_failed", "blocked", "cancelled")


@dataclass
class RunUsage:
    """What can be read out of a DeepSearch run's execution_metadata."""

    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    requests: int | None = None
    steps: int | None = None
    tool_calls: int | None = None
    duration_seconds: float | None = None
    usage_complete: bool | None = None
    details: dict[str, Any] | None = None


def _get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def extract_run_usage(execution_metadata: Any) -> RunUsage:
    """Read the worker's accounting. Every field is optional; older runs carry less."""
    em = execution_metadata if isinstance(execution_metadata, dict) else {}
    telemetry = _get(em, "synthesis_telemetry") or {}
    accounting = _get(telemetry, "recovery", "attempt_accounting") or {}
    token_usage = _get(accounting, "token_usage") or _get(telemetry, "token_usage") or {}
    if not isinstance(token_usage, dict):
        token_usage = {}
    tool_summary = _get(telemetry, "tool_call_summary", "by_tool")
    tool_calls = None
    if isinstance(tool_summary, dict):
        counts = [_int(v) for v in tool_summary.values()]
        tool_calls = sum(c for c in counts if c is not None) if counts else None

    total = _int(_get(em, "total_tokens"))
    if total is None:
        total = _int(token_usage.get("total"))
    usage_complete = _get(accounting, "token_usage_complete")
    if usage_complete is None:
        usage_complete = _get(telemetry, "token_usage_complete")
    details: dict[str, Any] = {}
    if isinstance(tool_summary, dict):
        details["tool_calls_by_tool"] = {str(k): _int(v) for k, v in tool_summary.items()}
    hit_max_steps = _get(em, "quality_record", "hit_max_steps")
    if hit_max_steps is not None:
        details["hit_max_steps"] = bool(hit_max_steps)
    build_hash = _get(em, "runtime_identity", "build_hash")
    if build_hash:
        details["worker_build_hash"] = str(build_hash)

    return RunUsage(
        provider=_get(telemetry, "effective_model", "provider") or _get(em, "runtime_identity", "llm_backend"),
        model=_get(em, "runtime_identity", "model")
        or _get(telemetry, "effective_model", "requested_model")
        or _get(telemetry, "model_id")
        or _get(em, "model_used"),
        input_tokens=_int(token_usage.get("input")),
        output_tokens=_int(token_usage.get("output")),
        total_tokens=total,
        requests=_int(_get(accounting, "model_accounting", "requests")),
        steps=_int(_get(em, "quality_record", "terminating_step")) or _int(_get(telemetry, "step_count")),
        tool_calls=tool_calls,
        duration_seconds=_float(_get(em, "duration_seconds")),
        usage_complete=bool(usage_complete) if usage_complete is not None else None,
        details=details or None,
    )


def _run_row(db: Session, mission_id: UUID) -> UsageRecord | None:
    return (
        db.query(UsageRecord)
        .filter(UsageRecord.mission_id == mission_id, UsageRecord.kind == USAGE_KIND_DEEPSEARCH_RUN)
        .first()
    )


def record_mission_submission(db: Session, mission: Mission, *, submitted_by: UUID | None) -> UsageRecord:
    """The queued row, attributed to the submitter. Safe to call again."""
    row = _run_row(db, mission.id)
    if row is None:
        row = UsageRecord(
            mission_id=mission.id,
            project_id=mission.project_id,
            kind=USAGE_KIND_DEEPSEARCH_RUN,
            status=str(mission.status or "queued"),
            attribution=ATTRIBUTION_SUBMITTER if submitted_by is not None else ATTRIBUTION_PROJECT_OWNER,
            user_id=submitted_by if submitted_by is not None else mission.owner_id,
        )
        db.add(row)
    elif submitted_by is not None and row.user_id != submitted_by:
        row.user_id = submitted_by
        row.attribution = ATTRIBUTION_SUBMITTER
    row.status = str(mission.status or row.status)
    row.started_at = mission.queued_at or row.started_at
    db.commit()
    return row


def record_mission_terminal(db: Session, mission: Mission) -> UsageRecord | None:
    """Fill the run's row from the worker's accounting once the mission is terminal.

    Idempotent: called from the materialization path on every replay and from
    the reconciler sweep. A row that already carries the same numbers is left
    untouched so replays do not churn ``updated_at``.
    """
    if mission.status not in TERMINAL_STATUSES:
        return None
    usage = extract_run_usage(mission.execution_metadata)
    row = _run_row(db, mission.id)
    if row is None:
        row = UsageRecord(
            mission_id=mission.id,
            project_id=mission.project_id,
            kind=USAGE_KIND_DEEPSEARCH_RUN,
            status=str(mission.status),
            attribution=ATTRIBUTION_PROJECT_OWNER,
            user_id=mission.owner_id,
        )
        db.add(row)
    desired = {
        "status": str(mission.status),
        "project_id": mission.project_id,
        "provider": usage.provider,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "requests": usage.requests,
        "steps": usage.steps,
        "tool_calls": usage.tool_calls,
        "duration_seconds": usage.duration_seconds,
        "usage_complete": usage.usage_complete,
        "details": usage.details,
        "started_at": mission.started_at or mission.queued_at,
        "completed_at": mission.completed_at,
    }
    changed = row.id is None or any(getattr(row, key) != value for key, value in desired.items())
    if changed:
        for key, value in desired.items():
            setattr(row, key, value)
        db.commit()
    return row


def sweep_unrecorded_terminal_missions(db: Session, *, limit: int = 500) -> int:
    """Record every terminal mission that has no run row yet. Backfill and safety net in one."""
    recorded_ids = db.query(UsageRecord.mission_id).filter(UsageRecord.kind == USAGE_KIND_DEEPSEARCH_RUN)
    missions = (
        db.query(Mission)
        .filter(Mission.status.in_(TERMINAL_STATUSES), ~Mission.id.in_(recorded_ids))
        .order_by(Mission.completed_at.desc().nullslast(), Mission.id)
        .limit(limit)
        .all()
    )
    recorded = 0
    for mission in missions:
        try:
            if record_mission_terminal(db, mission) is not None:
                recorded += 1
        except Exception:  # pragma: no cover - one bad row must not stop the sweep
            logger.warning("usage sweep could not record mission %s", mission.id, exc_info=True)
            db.rollback()
    return recorded


def record_librarian_usage(
    db: Session,
    *,
    user_id: UUID | None,
    project_id: UUID | None,
    kind: str,
    model: str | None,
    usage: dict[str, int] | None,
    requests: int,
    provider: str | None = None,
) -> UsageRecord | None:
    """One row per Librarian call. Never raises: telemetry must not fail a turn."""
    if not usage:
        return None
    try:
        row = UsageRecord(
            user_id=user_id,
            project_id=project_id,
            mission_id=None,
            kind=kind,
            status="completed",
            attribution=ATTRIBUTION_CALLER,
            provider=provider,
            model=model,
            input_tokens=_int(usage.get("prompt_tokens")),
            output_tokens=_int(usage.get("completion_tokens")),
            total_tokens=_int(usage.get("total_tokens")),
            requests=requests,
            usage_complete=True,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        return row
    except Exception:  # pragma: no cover - telemetry must never fail the request
        logger.warning("Librarian usage could not be recorded", exc_info=True)
        db.rollback()
        return None


def summarize_usage(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    user_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Per user, per kind, per model totals over [since, until). One query, no logs."""
    query = (
        db.query(
            UsageRecord.user_id,
            UsageRecord.kind,
            UsageRecord.model,
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.duration_seconds), 0.0),
            func.sum(UsageRecord.cost_usd),
        )
        .filter(UsageRecord.recorded_at >= since, UsageRecord.recorded_at < until)
        .group_by(UsageRecord.user_id, UsageRecord.kind, UsageRecord.model)
        .order_by(UsageRecord.user_id, UsageRecord.kind, UsageRecord.model)
    )
    if user_id is not None:
        query = query.filter(UsageRecord.user_id == user_id)
    return [
        {
            "user_id": row[0],
            "kind": row[1],
            "model": row[2],
            "records": int(row[3] or 0),
            "input_tokens": int(row[4] or 0),
            "output_tokens": int(row[5] or 0),
            "total_tokens": int(row[6] or 0),
            "duration_seconds": float(row[7] or 0.0),
            "cost_usd": float(row[8]) if row[8] is not None else None,
        }
        for row in query.all()
    ]
