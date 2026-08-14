#!/usr/bin/env python3
"""Repair missing TraceLab artifacts for stored DeepSearch terminal results.

Usage:
    python -m app.cli.reconcile_mission_results --limit 100
    python -m app.cli.reconcile_mission_results --mission-id <uuid-or-mission-id>
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.mission import Mission
from app.services.result_materialization import MissionResultMaterializationService


def _mission_by_identifier(db: Session, identifier: str) -> Mission | None:
    try:
        mission_uuid = UUID(identifier)
    except ValueError:
        mission_uuid = None
    if mission_uuid is not None:
        mission = cast(
            Mission | None,
            db.query(Mission).filter(Mission.id == mission_uuid).first(),
        )
        if mission is not None:
            return mission
    return cast(
        Mission | None,
        db.query(Mission).filter(Mission.mission_id == identifier).first(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded reconciliation pass and emit machine-readable counts."""
    parser = argparse.ArgumentParser(
        description="Materialize missing documents/reports from stored DeepSearch results"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum terminal missions to attempt (1-500, default: 100)",
    )
    parser.add_argument(
        "--mission-id",
        help="Repair one UUID or human-readable mission ID instead of scanning",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        service = MissionResultMaterializationService()
        if args.mission_id:
            mission = _mission_by_identifier(db, args.mission_id)
            if mission is None:
                print(json.dumps({"error": "mission_not_found", "mission_id": args.mission_id}))
                return 2
            if mission.status not in {"completed", "validation_failed"}:
                print(
                    json.dumps(
                        {
                            "error": "mission_not_terminal",
                            "mission_id": mission.mission_id,
                            "status": mission.status,
                        }
                    )
                )
                return 2
            outcome = service.materialize(db, mission)
            pending = service.needs_materialization(db, mission)
            print(
                json.dumps(
                    {
                        "mission_id": mission.mission_id,
                        "changed": outcome.changed,
                        "pending": pending,
                        "errors": outcome.errors,
                    },
                    sort_keys=True,
                )
            )
            return 1 if outcome.errors or pending else 0

        summary = service.reconcile_completed(db, limit=args.limit)
        print(
            json.dumps(
                {
                    "scanned": summary.scanned,
                    "eligible": summary.eligible,
                    "repaired": summary.repaired,
                    "failed": summary.failed,
                },
                sort_keys=True,
            )
        )
        return 1 if summary.failed else 0
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
