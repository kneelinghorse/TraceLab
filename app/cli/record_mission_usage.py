"""Record usage rows for terminal missions that have none (METER-0 backfill and safety net).

    python -m app.cli.record_mission_usage --limit 1000
    python -m app.cli.record_mission_usage --mission-id <uuid>

Idempotent: a mission that already has its run row is skipped by the sweep and
left unchanged by a targeted re-record unless the worker's accounting changed.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from uuid import UUID

from app.core.database import SessionLocal
from app.models.mission import Mission
from app.services.usage_recorder import record_mission_terminal, sweep_unrecorded_terminal_missions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=500, help="Maximum terminal missions to record in one sweep.")
    parser.add_argument("--mission-id", type=UUID, default=None, help="Record (or re-record) one mission by UUID.")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if args.mission_id is not None:
            mission = db.query(Mission).filter(Mission.id == args.mission_id).first()
            if mission is None:
                print(json.dumps({"error": "mission not found", "mission_id": str(args.mission_id)}))
                return 1
            row = record_mission_terminal(db, mission)
            if row is None:
                print(json.dumps({"recorded": 0, "reason": f"mission status is {mission.status}, not terminal"}))
                return 0
            print(
                json.dumps(
                    {
                        "recorded": 1,
                        "mission_id": str(mission.id),
                        "mission_ref": mission.mission_id,
                        "user_id": str(row.user_id) if row.user_id else None,
                        "attribution": row.attribution,
                        "model": row.model,
                        "total_tokens": row.total_tokens,
                        "requests": row.requests,
                        "steps": row.steps,
                        "duration_seconds": row.duration_seconds,
                    }
                )
            )
            return 0
        recorded = sweep_unrecorded_terminal_missions(db, limit=args.limit)
        print(json.dumps({"recorded": recorded, "limit": args.limit}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
