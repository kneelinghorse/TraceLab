#!/usr/bin/env python3
"""Validate parity between SQLite canonical store and file mirrors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _find_cmos_root() -> Path:
    """Find cmos/ directory from any working directory."""
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir.parent
    if (candidate / "db" / "schema.sql").exists() and (candidate / "agents.md").exists():
        return candidate
    if (Path.cwd() / "cmos" / "db" / "schema.sql").exists():
        return Path.cwd() / "cmos"
    current = Path.cwd().resolve()
    for _ in range(5):
        if (current / "cmos" / "db" / "schema.sql").exists():
            return current / "cmos"
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError("Cannot find cmos/ directory. Please run from project root.")


CMOS_ROOT = _find_cmos_root()
ROOT_DIR = CMOS_ROOT
if str(CMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(CMOS_ROOT))

from context.db_client import SQLiteClient, SQLiteClientError  # noqa: E402


def load_backlog(backlog_path: Path) -> Dict[str, Dict[str, Any]]:
    if not backlog_path.exists():
        return {}
    with backlog_path.open("r", encoding="utf-8") as handle:
        documents = list(yaml.safe_load_all(handle))
    if not documents:
        return {}
    missions: Dict[str, Dict[str, Any]] = {}
    for document in documents:
        domain = document.get("domainFields", {}) or {}
        mission_entries = domain.get("missions", []) or []
        missions.update(_extract_missions(mission_entries))
        sprint_entries = domain.get("sprints", []) or []
        for sprint in sprint_entries:
            sprint_missions = sprint.get("missions", []) or []
            missions.update(_extract_missions(sprint_missions))
    return missions


def _extract_missions(nodes: List[Any]) -> Dict[str, Dict[str, Any]]:
    extracted: Dict[str, Dict[str, Any]] = {}
    for mission in nodes:
        if not isinstance(mission, dict):
            continue
        mission_id = mission.get("id") or mission.get("missionId")
        if not mission_id:
            continue
        extracted[mission_id] = mission
    return extracted


def load_sessions_file(sessions_path: Path) -> List[str]:
    if not sessions_path.exists():
        return []
    with sessions_path.open("r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def compare_missions(db_rows: List[Dict[str, Any]], file_missions: Dict[str, Dict[str, Any]]) -> List[str]:
    mismatches: List[str] = []
    for row in db_rows:
        mission_id = row["id"]
        file_entry = file_missions.get(mission_id)
        if not file_entry:
            mismatches.append(f"{mission_id}: missing from backlog file")
            continue
        for field in ("status", "completed_at", "notes"):
            db_value = row.get(field) or ""
            file_value = file_entry.get(field) or ""
            if db_value != file_value:
                mismatches.append(f"{mission_id}: {field} mismatch (db='{db_value}' vs file='{file_value}')")
    return mismatches


def compare_contexts(client: SQLiteClient, path: Path, context_id: str) -> Tuple[bool, str]:
    db_row = client.fetchone("SELECT content FROM contexts WHERE id = :id", {"id": context_id})
    if not db_row:
        return False, f"{context_id}: missing from database"
    file_payload = {}
    if path.exists():
        file_payload = json.loads(path.read_text(encoding="utf-8"))
    db_payload = json.loads(db_row["content"])
    if file_payload != db_payload:
        return False, f"{context_id}: content mismatch"
    return True, f"{context_id}: OK"


def compare_sessions(db_rows: List[Dict[str, Any]], file_events: List[str]) -> List[str]:
    db_set = {row["raw_event"].strip() for row in db_rows}
    file_set = set(file_events)
    missing_in_db = file_set - db_set
    missing_in_file = db_set - file_set
    issues: List[str] = []
    if missing_in_db:
        issues.append(f"Sessions missing in DB: {len(missing_in_db)}")
    if missing_in_file:
        issues.append(f"Sessions missing in file: {len(missing_in_file)}")
    return issues


def run_parity_check(root: Path, data_root: Path | None = None) -> int:
    repo_root = root
    mirrors_root = data_root if data_root else repo_root
    backlog_path = mirrors_root / "missions" / "backlog.yaml"
    project_context_path = mirrors_root / "PROJECT_CONTEXT.json"
    master_context_path = mirrors_root / "context" / "MASTER_CONTEXT.json"
    sessions_path = mirrors_root / "SESSIONS.jsonl"
    db_path = repo_root / "db" / "cmos.sqlite"
    schema_path = repo_root / "db" / "schema.sql"

    client = SQLiteClient(db_path, schema_path=schema_path, create_missing=False)
    try:
        mission_rows = client.fetchall("SELECT id, status, completed_at, notes FROM missions")
        session_rows = client.fetchall("SELECT raw_event FROM session_events")
    except SQLiteClientError as error:  # pragma: no cover - defensive
        raise SystemExit(f"Database access failed: {error}") from error

    file_missions = load_backlog(backlog_path)
    mission_mismatches = compare_missions(mission_rows, file_missions)

    session_file_events = load_sessions_file(sessions_path)
    session_mismatches = compare_sessions(session_rows, session_file_events)

    ctx_results = [
        compare_contexts(client, project_context_path, "project_context"),
        compare_contexts(client, master_context_path, "master_context"),
    ]
    client.close()

    issues: List[str] = []
    issues.extend(mission_mismatches)
    issues.extend(session_mismatches)
    for ok, message in ctx_results:
        if not ok:
            issues.append(message)

    if issues:
        for issue in issues:
            print(f"[FAIL] {issue}")
        return 1

    print("[OK] Database and file mirrors are in sync.")
    return 0


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate parity between SQLite DB and file mirrors.")
    parser.add_argument("--root", type=Path, default=ROOT_DIR, help="CMOS root directory (default: %(default)s)")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Path containing backlog/context mirrors for comparison (default: repository root)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compatibility flag with legacy CLI invocations",
    )
    args = parser.parse_args(argv)
    sys.exit(
        run_parity_check(
            args.root.resolve(),
            args.data_root.resolve() if args.data_root else None,
        )
    )


if __name__ == "__main__":
    main()
