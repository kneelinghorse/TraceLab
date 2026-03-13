#!/usr/bin/env python3
"""Backfill TraceLab planning sessions into the canonical SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


SessionRow = Dict[str, Any]


@dataclass
class LegacySession:
    focus: str
    date: str
    agent: str
    key_discoveries: List[str]
    decisions_made: List[str]
    mistakes_made: List[str]


def load_legacy_sessions(path: Path) -> List[LegacySession]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    planning = payload.get("planning") or {}
    sessions = planning.get("session_summaries") or []
    results: List[LegacySession] = []
    for entry in sessions:
        results.append(
            LegacySession(
                focus=str(entry.get("focus") or "Planning Session"),
                date=str(entry.get("session_date") or "2025-01-01"),
                agent=str(entry.get("agent") or "assistant"),
                key_discoveries=list(entry.get("key_discoveries") or []),
                decisions_made=list(entry.get("decisions_made") or []),
                mistakes_made=list(entry.get("mistakes_made") or []),
            )
        )
    return results


def infer_type(focus: str) -> str:
    text = focus.lower()
    if "onboard" in text:
        return "onboarding"
    if "plan" in text or "roadmap" in text:
        return "planning"
    if "review" in text or "retro" in text:
        return "review"
    if "research" in text or "investigation" in text:
        return "research"
    if "triage" in text or "unblock" in text or "status" in text:
        return "check-in"
    return "custom"


def generate_session_id(date: str, counter: int) -> str:
    clean = date.replace("-", "")
    return f"PS-{clean}-{counter:03d}"


def load_existing_ids(db_path: Path) -> Set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id FROM sessions").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def build_rows(
    legacy_sessions: Iterable[LegacySession],
    existing_ids: Set[str],
) -> List[SessionRow]:
    rows: List[SessionRow] = []
    per_day_counts: Dict[str, int] = {}
    for session in legacy_sessions:
        per_day_counts.setdefault(session.date, 0)
        per_day_counts[session.date] += 1
        session_id = generate_session_id(session.date, per_day_counts[session.date])
        while session_id in existing_ids:
            per_day_counts[session.date] += 1
            session_id = generate_session_id(session.date, per_day_counts[session.date])

        started = f"{session.date}T09:00:00Z"
        completed = f"{session.date}T10:00:00Z"
        captures: List[Dict[str, str]] = []
        for discovery in session.key_discoveries:
            captures.append(
                {
                    "timestamp": started,
                    "category": "learning",
                    "content": discovery,
                }
            )
        for decision in session.decisions_made:
            captures.append(
                {
                    "timestamp": completed,
                    "category": "decision",
                    "content": decision,
                }
            )
        for mistake in session.mistakes_made:
            captures.append(
                {
                    "timestamp": completed,
                    "category": "context",
                    "content": mistake,
                }
            )
        summary = f"{session.focus} ({session.date})"
        metadata = {
            "source": "legacy_session_summary",
            "legacy_agent": session.agent,
        }
        rows.append(
            {
                "id": session_id,
                "type": infer_type(session.focus),
                "title": session.focus,
                "started_at": started,
                "completed_at": completed,
                "agent": session.agent or "assistant",
                "summary": summary,
                "captures": json.dumps(captures, ensure_ascii=False),
                "next_steps": None,
                "status": "completed",
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
    return rows


def insert_rows(db_path: Path, rows: List[SessionRow]) -> int:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executemany(
                """
                INSERT INTO sessions (
                    id, type, title, started_at, completed_at, agent, summary,
                    captures, next_steps, status, metadata
                ) VALUES (
                    :id, :type, :title, :started_at, :completed_at, :agent, :summary,
                    :captures, :next_steps, :status, :metadata
                )
                """,
                rows,
            )
    finally:
        conn.close()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill sessions from legacy context."
    )
    parser.add_argument(
        "--legacy-context",
        type=Path,
        default=Path("cmos.TraceLab/context/MASTER_CONTEXT.json.backup-20251114111619"),
        help="Path to the pre-upgrade MASTER_CONTEXT.json backup.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("cmos.TraceLab/db/cmos.sqlite"),
        help="Path to the SQLite database to update.",
    )
    args = parser.parse_args()

    legacy_sessions = load_legacy_sessions(args.legacy_context.resolve())
    if not legacy_sessions:
        print("No legacy session summaries found.")
        return

    db_path = args.db_path.resolve()
    existing = load_existing_ids(db_path)
    rows = build_rows(legacy_sessions, existing)

    new_rows = [row for row in rows if row["id"] not in existing]
    if not new_rows:
        print("No new sessions to insert.")
        return

    inserted = insert_rows(db_path, new_rows)
    print(f"Inserted {inserted} sessions into {db_path}")


if __name__ == "__main__":
    main()
