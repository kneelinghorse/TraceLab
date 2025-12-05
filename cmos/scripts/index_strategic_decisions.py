#!/usr/bin/env python3
"""Populate the strategic_decisions table from MASTER_CONTEXT decisions."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _utc_now() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_master_context(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT content FROM contexts WHERE id = 'master_context'").fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise SystemExit("master_context not found in contexts table.")
    return json.loads(row[0])


def _decision_entries(decisions: Iterable[Any]) -> Iterable[Dict[str, Any]]:
    for entry in decisions or []:
        if isinstance(entry, dict):
            yield {
                "decision": entry.get("decision") or entry.get("decision_text") or str(entry),
                "date": entry.get("date"),
                "sprint_id": entry.get("sprint_id"),
                "source": entry.get("source"),
            }
        else:
            yield {
                "decision": str(entry),
                "date": None,
                "sprint_id": None,
                "source": "legacy",
            }


def populate(db_path: Path, project_domain: str) -> int:
    context = _load_master_context(db_path)
    decisions = list(_decision_entries(context.get("decisions_made") or []))
    if not decisions:
        print("No decisions found in master_context.")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        existing = {
            row["decision_text"]
            for row in conn.execute("SELECT decision_text FROM strategic_decisions")
        }
        inserted = 0
        with conn:
            for entry in decisions:
                text = entry["decision"].strip()
                if not text or text in existing:
                    continue
                created_at = entry.get("date") or _utc_now()
                conn.execute(
                    """
                    INSERT INTO strategic_decisions (
                        decision_text, created_at, sprint_id, project_domain, context_id
                    ) VALUES (
                        :decision_text, :created_at, :sprint_id, :project_domain, 'master_context'
                    )
                    """,
                    {
                        "decision_text": text,
                        "created_at": created_at,
                        "sprint_id": entry.get("sprint_id"),
                        "project_domain": project_domain,
                    },
                )
                existing.add(text)
                inserted += 1
    finally:
        conn.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Index strategic decisions from master context.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("cmos.TraceLab/db/cmos.sqlite"),
        help="SQLite database path.",
    )
    parser.add_argument(
        "--domain",
        default="tracelab",
        help="Project domain label stored with decisions.",
    )
    args = parser.parse_args()

    inserted = populate(args.db_path.resolve(), args.domain)
    print(f"Inserted {inserted} decisions.")


if __name__ == "__main__":
    main()
