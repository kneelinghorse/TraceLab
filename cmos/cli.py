#!/usr/bin/env python3
"""Unified CMOS command line entry point.

Provides mission lifecycle helpers, database inspection/export commands,
and lightweight validation utilities backed by the canonical SQLite store.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None

try:  # pragma: no cover - optional dependency
    import click  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    click = None


def _find_cmos_root() -> Path:
    """Locate the cmos/ directory so the CLI can run from any path."""

    script_dir = Path(__file__).resolve().parent
    candidate = script_dir
    if (candidate / "db" / "schema.sql").exists() and (
        candidate / "agents.md"
    ).exists():
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
    raise RuntimeError(
        "Cannot find cmos/ directory. Please run from project root or supply --root."
    )


DEFAULT_ROOT = _find_cmos_root()
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from context.db_client import SQLiteClient, SQLiteClientError  # noqa: E402
from context.mission_runtime import (  # noqa: E402
    MissionRuntime,
    MissionRuntimeError,
    block as block_mission,
    complete as complete_mission,
    start as start_mission,
)
from context.session_runtime import (  # noqa: E402
    ActiveSessionError,
    NoActiveSessionError,
    SessionError,
    SessionRuntimeError,
    ValidationError,
    capture as capture_session,
    complete as complete_session,
    start as start_session,
)
from context.view_helpers import (  # noqa: E402
    ContextViewError,
    export_context as export_context_view,
    get_context_at_point,
    get_domain_view,
    get_master_context_view,
)


@dataclass(frozen=True)
class Environment:
    root: Path
    db_path: Path
    schema_path: Path


FOUNDATIONAL_CHECKS = {
    Path("agents.md"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
    Path("README.md"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
    Path("context/MASTER_CONTEXT.json"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
}

VALID_MISSION_STATUSES = (
    "Queued",
    "Current",
    "In Progress",
    "Blocked",
    "Completed",
)

_STATUS_LOOKUP = {status.lower(): status for status in VALID_MISSION_STATUSES}

ANSI_RESET = "\033[0m"
ANSI_COLORS = {
    "red": "\033[31m",
    "yellow": "\033[33m",
}

NO_ACTIVE_SESSION_MESSAGE = (
    'No active session. Start one with: ./cmos/cli.py session start --type planning --title "Sprint planning" '
    "or pass --session PS-YYYY-MM-DD-### to target an existing one."
)


def _isatty(stream: Any) -> bool:
    probe = getattr(stream, "isatty", None)
    if callable(probe):  # pragma: no branch - thin wrapper
        try:
            return bool(probe())
        except OSError:  # pragma: no cover - platform specific
            return False
    return False


def _emit_text(text: str, *, color: str | None = None, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    if click is not None:
        styled = click.style(text, fg=color) if color else text
        click.echo(styled, err=err)
        return
    if color and _isatty(stream):
        prefix = ANSI_COLORS.get(color)
        if prefix:
            text = f"{prefix}{text}{ANSI_RESET}"
    print(text, file=stream)


def _session_error_label(error: SessionError) -> str:
    if isinstance(error, ValidationError):
        return "Validation error"
    if isinstance(error, ActiveSessionError):
        return "Active session conflict"
    if isinstance(error, NoActiveSessionError):
        return "Session lookup error"
    if isinstance(error, SessionRuntimeError):
        return "Session runtime error"
    return "Session error"


def _print_session_error(error: SessionError) -> None:
    label = _session_error_label(error)
    _emit_text(f"{label}: {error}", color="red", err=True)
    if getattr(error, "hint", None):
        _emit_text(f"Hint: {error.hint}", color="yellow", err=True)
    if getattr(error, "suggestion", None):
        _emit_text(f"Try: {error.suggestion}", color="yellow", err=True)


def _print_generic_error(error: Exception) -> None:
    _emit_text(f"Error: {error}", color="red", err=True)


def _normalize_status(value: str) -> str:
    normalized = _STATUS_LOOKUP.get((value or "").strip().lower())
    if not normalized:
        allowed = ", ".join(VALID_MISSION_STATUSES)
        raise SystemExit(f"Invalid status '{value}'. Choose from: {allowed}.")
    return normalized


def _ensure_mission_exists(client: SQLiteClient, mission_id: str) -> Dict[str, Any]:
    row = client.fetchone(
        "SELECT id, metadata FROM missions WHERE id = :id", {"id": mission_id}
    )
    if not row:
        raise SystemExit(f"Mission {mission_id} does not exist.")
    return row


def _ensure_sprint_exists(client: SQLiteClient, sprint_id: str) -> None:
    row = client.fetchone("SELECT id FROM sprints WHERE id = :id", {"id": sprint_id})
    if not row:
        raise SystemExit(f"Sprint {sprint_id} does not exist in the database.")


def _build_metadata_payload(
    *,
    base: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    success_criteria: Optional[List[str]] = None,
    deliverables: Optional[List[str]] = None,
    metadata_json: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    payload: Dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    if metadata_json:
        try:
            incoming = json.loads(metadata_json)
        except json.JSONDecodeError as error:
            raise SystemExit(f"Invalid metadata JSON: {error}") from error
        if not isinstance(incoming, dict):
            raise SystemExit("Metadata JSON must be an object.")
        payload.update(incoming)
    if description is not None:
        payload["description"] = description
    if success_criteria is not None:
        payload["successCriteria"] = success_criteria
    if deliverables is not None:
        payload["deliverables"] = deliverables
    return payload or None


def _resolve_environment(args: argparse.Namespace) -> Environment:
    root = (args.root or DEFAULT_ROOT).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    db_path = (args.database or (root / "db" / "cmos.sqlite")).resolve()
    schema_path = (root / "db" / "schema.sql").resolve()
    return Environment(root=root, db_path=db_path, schema_path=schema_path)


def _open_client(env: Environment) -> SQLiteClient:
    return SQLiteClient(env.db_path, schema_path=env.schema_path, create_missing=False)


def _build_runtime(env: Environment) -> MissionRuntime:
    return MissionRuntime(repo_root=env.root, db_path=env.db_path)


def _print_json(label: str, payload: Dict[str, Any]) -> None:
    print(label)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _parse_metadata_blob(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_string_items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, (list, tuple)):
        results: List[str] = []
        for item in value:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    results.append(candidate)
        return results


def _load_json_array(raw: Any) -> List[Any]:
    """Best-effort conversion of JSON-encoded list columns into Python lists."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _format_relative_timestamp(value: Optional[str]) -> str:
    dt = _parse_iso_timestamp(value)
    if not dt:
        return "unknown"
    now = datetime.now(tz=timezone.utc)
    delta = now - dt.astimezone(timezone.utc)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m ago"
    if seconds < 86_400:
        hours = seconds // 3600
        return f"{hours}h ago"
    if seconds < 604_800:
        days = seconds // 86_400
        return f"{days}d ago"
    return dt.strftime("%Y-%m-%d")


def _format_full_timestamp(value: Optional[str]) -> str:
    dt = _parse_iso_timestamp(value)
    if not dt:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_duration(start: Optional[str], end: Optional[str]) -> str:
    start_dt = _parse_iso_timestamp(start)
    end_dt = _parse_iso_timestamp(end) or datetime.now(tz=timezone.utc)
    if not start_dt:
        return "unknown"
    total_seconds = int((end_dt - start_dt).total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    minutes = total_seconds // 60
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _active_session_info(env: Environment) -> Optional[Dict[str, Any]]:
    """Return the active session record from project_context if available."""
    client = _open_client(env)
    try:
        project_context = client.get_context("project_context") or {}
    finally:
        client.close()
    working = project_context.get("working_memory") or {}
    active = working.get("active_session")
    if isinstance(active, dict) and active.get("id"):
        return active
    return None


def _require_session_id(env: Environment, override: Optional[str]) -> str:
    """Resolve the session ID to operate on, enforcing active session when needed."""
    if override:
        return override
    active = _active_session_info(env)
    if not active:
        raise SystemExit(NO_ACTIVE_SESSION_MESSAGE)
    return str(active["id"])
    return []


def _format_sprint_label(mission: Dict[str, Any]) -> str:
    sprint_id = mission.get("sprint_id")
    sprint_title = mission.get("sprint_title")
    if sprint_id and sprint_title:
        return f"{sprint_id} – {sprint_title}"
    if sprint_id:
        return str(sprint_id)
    if sprint_title:
        return str(sprint_title)
    return "Unassigned"


def _render_bullet_block(items: List[str], placeholder: str) -> List[str]:
    if items:
        return [f"- {item}" for item in items]
    return [f"- {placeholder}"]


def _render_research_report(
    mission: Dict[str, Any], events: List[Dict[str, Any]]
) -> str:
    metadata_blob = _parse_metadata_blob(mission.get("metadata"))
    brief = (
        metadata_blob.get("metadata")
        if isinstance(metadata_blob.get("metadata"), dict)
        else {}
    )

    description = brief.get("description") if isinstance(brief, dict) else None
    success = _extract_string_items(
        brief.get("successCriteria") if isinstance(brief, dict) else None
    )
    deliverables = _extract_string_items(
        brief.get("deliverables") if isinstance(brief, dict) else None
    )
    research_questions = _extract_string_items(
        brief.get("researchQuestions") if isinstance(brief, dict) else None
    )

    started_at = metadata_blob.get("started_at")
    completed_at = mission.get("completed_at") or metadata_blob.get("completed_at")

    lines: List[str] = []
    mission_name = mission.get("name") or "(untitled mission)"
    lines.append(f"# Research Report: {mission.get('id')} – {mission_name}")
    lines.append("")

    lines.append("## Mission Overview")
    lines.append(f"- **Status**: {mission.get('status') or 'unknown'}")
    lines.append(f"- **Sprint**: {_format_sprint_label(mission)}")
    if started_at:
        lines.append(f"- **Started**: {started_at}")
    if completed_at:
        lines.append(f"- **Completed**: {completed_at}")
    lines.append("")

    lines.append("## Mission Brief")
    if description:
        lines.append(description)
    else:
        lines.append("_No description recorded._")
    lines.append("")

    if research_questions:
        lines.append("### Research Questions")
        lines.extend(_render_bullet_block(research_questions, ""))
        lines.append("")

    lines.append("### Success Criteria")
    lines.extend(_render_bullet_block(success, "No success criteria recorded."))
    lines.append("")

    lines.append("### Deliverables")
    lines.extend(_render_bullet_block(deliverables, "No deliverables recorded."))
    lines.append("")

    lines.append("## Key Findings")
    notes = (mission.get("notes") or "").strip()
    if notes:
        lines.append(notes)
    else:
        lines.append("_No mission notes were stored._")
    lines.append("")

    lines.append("## Session Timeline")
    if events:
        for event in events:
            ts = event.get("ts") or "unknown time"
            agent = event.get("agent") or "unknown agent"
            action = event.get("action") or "event"
            summary = event.get("summary") or ""
            entry = f"- {ts} — **{agent}** [{action}]"
            if summary:
                entry += f": {summary}"
            next_hint = event.get("next_hint")
            if next_hint:
                entry += f" _(next: {next_hint})_"
            lines.append(entry)
    else:
        lines.append("_No session events recorded for this mission._")
    lines.append("")

    snapshot_source: Dict[str, Any]
    if metadata_blob:
        snapshot_source = metadata_blob
    else:
        raw = mission.get("metadata")
        snapshot_source = {"raw_metadata": raw} if raw else {}

    lines.append("## Metadata Snapshot")
    lines.append("```json")
    lines.append(json.dumps(snapshot_source, ensure_ascii=False, indent=2))
    lines.append("```")

    return "\n".join(lines).rstrip()


def _mission_status(runtime: MissionRuntime, limit: int) -> None:
    rows = runtime.client.fetchall(
        """
        SELECT id, name, status, completed_at
          FROM missions
         ORDER BY CASE status
                  WHEN 'In Progress' THEN 0
                  WHEN 'Current' THEN 1
                  WHEN 'Queued' THEN 2
                  WHEN 'Blocked' THEN 3
                  ELSE 4
                END,
                rowid
         LIMIT :limit
        """,
        {"limit": limit},
    )
    if not rows:
        print("No missions present in the queue.")
        return
    print("Mission queue:")
    for row in rows:
        status = row.get("status") or "unknown"
        completed = (
            f" (completed {row['completed_at']})" if row.get("completed_at") else ""
        )
        print(f"- {row.get('id')}: {row.get('name')} [{status}]{completed}")


def _mission_start(env: Environment, args: argparse.Namespace) -> None:
    result = start_mission(
        args.mission_id,
        agent=args.agent,
        summary=args.summary,
        ts=args.ts,
        repo_root=env.root,
        db_path=env.db_path,
    )
    _print_json(f"Mission {args.mission_id} started.", result.event)
    _sync_backlog(env)


def _mission_complete(env: Environment, args: argparse.Namespace) -> None:
    result = complete_mission(
        args.mission_id,
        agent=args.agent,
        summary=args.summary,
        notes=args.notes,
        ts=args.ts,
        next_hint=args.next_hint,
        promote_next=not args.no_promote,
        immediate=args.immediate,
        repo_root=env.root,
        db_path=env.db_path,
    )
    _print_json(f"Mission {args.mission_id} completed.", result.event)
    _sync_backlog(env)
    if result.next_mission:
        status = "In Progress" if args.immediate else "Current"
        print(f"Promoted {result.next_mission} -> {status}.")


def _mission_block(env: Environment, args: argparse.Namespace) -> None:
    result = block_mission(
        args.mission_id,
        agent=args.agent,
        summary=args.summary,
        reason=args.reason,
        needs=args.need or [],
        ts=args.ts,
        next_hint=args.next_hint,
        repo_root=env.root,
        db_path=env.db_path,
    )
    _print_json(f"Mission {args.mission_id} blocked.", result.event)
    _sync_backlog(env)


def _mission_add(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        _ensure_sprint_exists(client, args.sprint)
        existing = client.fetchone(
            "SELECT id FROM missions WHERE id = :id", {"id": args.mission_id}
        )
        if existing:
            raise SystemExit(f"Mission {args.mission_id} already exists.")
        metadata = _build_metadata_payload(
            description=args.description,
            success_criteria=args.success,
            deliverables=args.deliverable,
            metadata_json=args.metadata,
        )
        with client.transaction() as conn:
            conn.execute(
                """
                INSERT INTO missions (id, sprint_id, name, status, completed_at, notes, metadata)
                VALUES (:id, :sprint_id, :name, :status, NULL, :notes, :metadata)
                """,
                {
                    "id": args.mission_id,
                    "sprint_id": args.sprint,
                    "name": args.name,
                    "status": _normalize_status(args.status or "Queued"),
                    "notes": args.notes,
                    "metadata": json.dumps(metadata, ensure_ascii=False)
                    if metadata
                    else None,
                },
            )
    finally:
        client.close()
    _sync_backlog(env)
    print(f"Mission {args.mission_id} added to sprint {args.sprint}.")


def _mission_update(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    changed_fields: List[str] = []
    try:
        row = _ensure_mission_exists(client, args.mission_id)
        updates: Dict[str, Any] = {}
        if args.name:
            updates["name"] = args.name
        if args.status:
            updates["status"] = _normalize_status(args.status)
        if args.sprint:
            _ensure_sprint_exists(client, args.sprint)
            updates["sprint_id"] = args.sprint
        if args.notes is not None:
            updates["notes"] = args.notes

        metadata_requested = any(
            value is not None
            for value in (
                args.description,
                args.success,
                args.deliverable,
                args.metadata,
            )
        )
        if metadata_requested:
            base: Optional[Dict[str, Any]] = None
            raw_metadata = row.get("metadata")
            if raw_metadata:
                try:
                    base = json.loads(raw_metadata)
                except json.JSONDecodeError:
                    base = {}
            metadata = _build_metadata_payload(
                base=base,
                description=args.description,
                success_criteria=args.success,
                deliverables=args.deliverable,
                metadata_json=args.metadata,
            )
            updates["metadata"] = (
                json.dumps(metadata, ensure_ascii=False) if metadata else None
            )

        if not updates:
            raise SystemExit("Provide at least one field to update.")

        changed_fields = list(updates.keys())
        assignments = ", ".join(f"{column} = :{column}" for column in changed_fields)
        updates["id"] = args.mission_id
        with client.transaction() as conn:
            conn.execute(f"UPDATE missions SET {assignments} WHERE id = :id", updates)
    finally:
        client.close()
    _sync_backlog(env)
    print(f"Mission {args.mission_id} updated ({', '.join(changed_fields)}).")


def _mission_depends(env: Environment, args: argparse.Namespace) -> None:
    if args.from_id == args.to_id:
        raise SystemExit("Dependencies require distinct missions.")
    client = _open_client(env)
    try:
        _ensure_mission_exists(client, args.from_id)
        _ensure_mission_exists(client, args.to_id)
        with client.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mission_dependencies (from_id, to_id, type)
                VALUES (:from_id, :to_id, :type)
                ON CONFLICT(from_id, to_id) DO UPDATE SET type = excluded.type
                """,
                {"from_id": args.from_id, "to_id": args.to_id, "type": args.dep_type},
            )
    finally:
        client.close()
    _sync_backlog(env)
    print(f"Dependency recorded: {args.from_id} -> {args.to_id} ({args.dep_type}).")


def _research_export(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        mission = client.fetchone(
            """
            SELECT m.id,
                   m.name,
                   m.status,
                   m.completed_at,
                   m.notes,
                   m.metadata,
                   m.sprint_id,
                   s.title AS sprint_title
              FROM missions m
         LEFT JOIN sprints s ON s.id = m.sprint_id
             WHERE m.id = :id
            """,
            {"id": args.mission_id},
        )
        if not mission:
            raise SystemExit(f"Mission {args.mission_id} does not exist.")
        events = client.fetchall(
            """
            SELECT ts, agent, action, summary, next_hint
              FROM session_events
             WHERE mission = :mission
             ORDER BY ts ASC, id ASC
            """,
            {"mission": args.mission_id},
        )
    finally:
        client.close()

    if mission.get("status") != "Completed" and not args.allow_incomplete:
        raise SystemExit(
            f"Mission {args.mission_id} is {mission.get('status')}. Complete it first or pass --allow-incomplete."
        )

    default_path = env.root / "research" / f"{mission['id']}.md"
    output_path = (args.output or default_path).resolve()
    if output_path.exists() and not args.overwrite:
        raise SystemExit(
            f"Research report already exists: {output_path}. Use --overwrite to replace it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = _render_research_report(mission, events)
    output_path.write_text(document + "\n", encoding="utf-8")
    print(f"Research report written to {output_path}")


def _mission_status_cmd(env: Environment, args: argparse.Namespace) -> None:
    runtime = _build_runtime(env)
    try:
        runtime.ensure_database()
        _mission_status(runtime, args.limit)
    finally:
        runtime.close()


def _mission_show_cmd(env: Environment, args: argparse.Namespace) -> None:
    """Display full mission specification."""
    if yaml is None:
        raise SystemExit(
            "PyYAML is required for mission display. Install pyyaml first."
        )

    client = _open_client(env)
    try:
        row = client.fetchone(
            """
            SELECT m.id, m.name, m.status, m.completed_at, m.notes,
                   s.id as sprint_id, s.title as sprint_title,
                   m.objective, m.context, m.success_criteria, 
                   m.deliverables, m.reference_docs, m.domain_fields
            FROM missions m
            LEFT JOIN sprints s ON s.id = m.sprint_id
            WHERE m.id = :id
            """,
            {"id": args.mission_id},
        )

        if not row:
            raise SystemExit(f"Mission {args.mission_id} not found.")

        if args.format == "compact":
            # Compact format - key info only
            print(f"\nMission: {row['id']}")
            print(f"Name: {row['name']}")
            print(f"Status: {row['status']}")
            print(f"Sprint: {row['sprint_id']} - {row['sprint_title'] or 'N/A'}")
            if row["completed_at"]:
                print(f"Completed: {row['completed_at']}")
            if row["objective"]:
                print(f"\nObjective:\n{row['objective']}")
            if row["notes"]:
                print(f"\nNotes:\n{row['notes']}")
        else:
            # Full format - everything
            print(f"\n{'=' * 80}")
            print(f"Mission: {row['id']} - {row['name']}")
            print(f"{'=' * 80}\n")

            print(f"Status: {row['status']}")
            print(f"Sprint: {row['sprint_id']} - {row['sprint_title'] or 'N/A'}")
            if row["completed_at"]:
                print(f"Completed: {row['completed_at']}")

            if row["objective"]:
                print(f"\n## Objective\n{row['objective']}")

            if row["context"]:
                print(f"\n## Context\n{row['context']}")

            if row["success_criteria"]:
                criteria = json.loads(row["success_criteria"])
                print(f"\n## Success Criteria")
                for i, criterion in enumerate(criteria, 1):
                    print(f"  {i}. {criterion}")

            if row["deliverables"]:
                deliverables = json.loads(row["deliverables"])
                print(f"\n## Deliverables")
                for i, item in enumerate(deliverables, 1):
                    print(f"  {i}. {item}")

            if row["reference_docs"]:
                refs = json.loads(row["reference_docs"])
                print(f"\n## References")
                for ref in refs:
                    print(f"  - {ref}")

            if row["domain_fields"]:
                domain = json.loads(row["domain_fields"])
                print(f"\n## Domain Fields")
                print(f"Type: {domain.get('type', 'N/A')}")
                if domain.get("researchFoundation"):
                    print(f"\nResearch Foundation:")
                    for finding in domain["researchFoundation"]:
                        print(
                            f"  - {finding.get('finding', 'N/A')} (from {finding.get('sourceMission', 'N/A')})"
                        )

            if row["notes"]:
                print(f"\n## Mission Notes\n{row['notes']}")

            print(f"\n{'=' * 80}\n")
    finally:
        client.close()


def _session_start(env: Environment, args: argparse.Namespace) -> None:
    session_id = start_session(
        session_type=args.session_type,
        title=args.title,
        agent=args.agent,
        sprint_id=args.sprint,
        repo_root=env.root,
        db_path=env.db_path,
    )
    print(f"Session {session_id} started ({args.session_type}): {args.title}")


def _session_capture(env: Environment, args: argparse.Namespace) -> None:
    session_id = _require_session_id(env, args.session)
    capture_session(
        session_id=session_id,
        category=args.category,
        content=args.content,
        context=args.context,
        agent=args.agent,
        repo_root=env.root,
        db_path=env.db_path,
    )
    print(f"[{session_id}] Recorded {args.category} insight.")


def _session_complete(env: Environment, args: argparse.Namespace) -> None:
    session_id = _require_session_id(env, args.session)
    next_steps = _extract_string_items(args.next_steps)
    complete_session(
        session_id=session_id,
        summary=args.summary,
        next_steps=next_steps or None,
        agent=args.agent,
        repo_root=env.root,
        db_path=env.db_path,
    )
    note = f"Session {session_id} completed."
    if next_steps:
        note = f"{note} Next steps recorded: {len(next_steps)}."
    print(note)


def _session_onboard(env: Environment, _args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        project_context = client.get_context("project_context") or {}
        master_context = client.get_context("master_context") or {}
        session_stats = (
            client.fetchone(
                """
            SELECT COUNT(*) AS total_sessions,
                   MAX(COALESCE(completed_at, started_at)) AS last_activity
              FROM sessions
            """
            )
            or {}
        )
        recent_sessions = client.fetchall(
            """
            SELECT id, type, title, summary, completed_at, started_at, captures, next_steps
              FROM sessions
             ORDER BY COALESCE(completed_at, started_at) DESC
             LIMIT 5
            """
        )
        active_missions = client.fetchall(
            """
            SELECT id, name, status
              FROM missions
             WHERE status IN ('In Progress', 'Current')
             ORDER BY CASE status WHEN 'In Progress' THEN 0 ELSE 1 END, rowid
             LIMIT 3
            """
        )
        blocked_missions = client.fetchall(
            """
            SELECT id, name, notes
              FROM missions
             WHERE status = 'Blocked'
             ORDER BY rowid
             LIMIT 3
            """
        )
        queued_missions = client.fetchall(
            """
            SELECT id, name
              FROM missions
             WHERE status = 'Queued'
             ORDER BY rowid
             LIMIT 3
            """
        )
        decisions = client.fetchall(
            """
            SELECT decision_text, project_domain, created_at
              FROM strategic_decisions
             ORDER BY created_at DESC
             LIMIT 10
            """
        )
        sprint = client.fetchone(
            """
            SELECT id, title, status
              FROM sprints
             ORDER BY CASE status WHEN 'In Progress' THEN 0 WHEN 'Current' THEN 1 ELSE 2 END,
                      rowid
             LIMIT 1
            """
        )
    finally:
        client.close()

    working_memory = project_context.get("working_memory") or {}
    project_identity = master_context.get("project_identity") or {}
    project_name = project_identity.get("name") or "CMOS Project"
    project_desc = (
        project_identity.get("description") or "Session management initiative"
    )
    total_sessions = (
        working_memory.get("session_count") or session_stats.get("total_sessions") or 0
    )
    last_activity = working_memory.get("last_session") or session_stats.get(
        "last_activity"
    )

    lines: List[str] = []
    lines.append("=== Project Overview ===")
    lines.append(f"Project: {project_name}")
    if project_desc:
        lines.append(f"Description: {project_desc}")
    if sprint:
        lines.append(f"Sprint: {sprint['id']} - {sprint['title']} ({sprint['status']})")
    lines.append(
        f"Sessions: {total_sessions} total, last activity {_format_relative_timestamp(last_activity)}"
    )
    lines.append("")

    lines.append("=== Recent Sessions ===")
    if not recent_sessions:
        lines.append(
            "No sessions recorded yet. Start one with `./cmos/cli.py session start ...`"
        )
    else:
        for row in recent_sessions:
            ts = row.get("completed_at") or row.get("started_at")
            title = row.get("title") or row.get("id")
            lines.append(
                f"• [{(row.get('type') or 'session').title()}] {title} ({_format_relative_timestamp(ts)})"
            )
            summary = row.get("summary") or "No summary captured."
            lines.append(f"  Summary: {summary}")
            captures = _load_json_array(row.get("captures"))
            decision = next(
                (c.get("content") for c in captures if c.get("category") == "decision"),
                None,
            )
            learning = next(
                (c.get("content") for c in captures if c.get("category") == "learning"),
                None,
            )
            next_capture = next(
                (
                    c.get("content")
                    for c in captures
                    if c.get("category") == "next-step"
                ),
                None,
            )
            if decision:
                lines.append(f"  Decision: {decision}")
            if learning:
                lines.append(f"  Learning: {learning}")
            next_steps = _load_json_array(row.get("next_steps"))
            highlight = next_capture or (next_steps[0] if next_steps else None)
            if highlight:
                lines.append(f"  Next: {highlight}")
    lines.append("")

    lines.append("=== Active Work ===")
    if active_missions:
        for mission in active_missions:
            lines.append(f"• {mission['id']} ({mission['status']}): {mission['name']}")
    else:
        lines.append("No missions currently marked Current/In Progress.")
    if blocked_missions:
        lines.append("Blocked:")
        for mission in blocked_missions:
            reason = mission.get("notes") or "reason not captured"
            lines.append(f"  • {mission['id']}: {mission['name']} — {reason}")
    if queued_missions:
        lines.append("Next Up:")
        for mission in queued_missions:
            lines.append(f"  • {mission['id']}: {mission['name']}")
    lines.append("")

    lines.append("=== Recent Decisions ===")
    if decisions:
        for decision in decisions:
            domain = decision.get("project_domain") or "general"
            ts = decision.get("created_at")
            lines.append(
                f"• {decision['decision_text']} [{domain}] ({_format_relative_timestamp(ts)})"
            )
    else:
        lines.append("No strategic decisions recorded yet.")
    lines.append("")

    lines.append("=== Quick Start ===")
    lines.append("1. Review backlog: ./cmos/cli.py mission status")
    lines.append(
        '2. Start build work: ./cmos/cli.py mission start <id> --summary "Your summary"'
    )
    lines.append(
        '3. Capture planning: ./cmos/cli.py session start --type planning --title "Sprint planning"'
    )
    lines.append(
        '4. Log insights: ./cmos/cli.py session capture decision "Key decision"'
    )
    lines.append(
        '5. Finish sessions: ./cmos/cli.py session complete --summary "Wrap-up"'
    )

    print("\n".join(lines))


def _session_list(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        clauses = []
        params: Dict[str, Any] = {"limit": args.limit}
        if args.type:
            clauses.append("type = :type")
            params["type"] = args.type.strip().lower()
        if args.status:
            clauses.append("status = :status")
            params["status"] = args.status.strip().lower()
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = client.fetchall(
            f"""
            SELECT id, type, title, status, agent, started_at, completed_at, summary, captures
              FROM sessions
              {where}
             ORDER BY COALESCE(completed_at, started_at) DESC
             LIMIT :limit
            """,
            params,
        )
    finally:
        client.close()

    print("=== Recent Sessions ===")
    if not rows:
        print("No sessions match the provided filters.")
        return

    for row in rows:
        session_id = row.get("id")
        session_type = (row.get("type") or "session").title()
        status = row.get("status") or "unknown"
        title = row.get("title") or session_id
        started = row.get("started_at")
        completed = row.get("completed_at")
        summary = row.get("summary") or "No summary captured."
        duration = _format_duration(
            started, completed if status == "completed" else None
        )
        captures = _load_json_array(row.get("captures"))
        counts: Dict[str, int] = {}
        for capture in captures:
            category = (capture.get("category") or "").lower()
            if category:
                counts[category] = counts.get(category, 0) + 1

        capture_bits = (
            ", ".join(f"{value} {key}" for key, value in counts.items())
            or "no captures logged"
        )
        print(f"{session_id} [{session_type}] {title} ({status})")
        print(f"  Started: {_format_full_timestamp(started)}, Duration: {duration}")
        print(f"  Summary: {summary}")
        print(f"  Captures: {capture_bits}")
        print("")


def _session_show(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        row = client.fetchone(
            """
            SELECT id, type, title, status, agent, sprint_id,
                   started_at, completed_at, summary, captures, next_steps
              FROM sessions
             WHERE id = :id
            """,
            {"id": args.session_id},
        )
    finally:
        client.close()

    if not row:
        raise SystemExit(f"Session {args.session_id} not found.")

    session_id = row["id"]
    session_type = (row.get("type") or "session").title()
    print(f"=== Session Details: {session_id} ===")
    print(f"Type: {session_type}")
    print(f"Title: {row.get('title') or 'Untitled session'}")
    print(f"Status: {row.get('status') or 'unknown'}")
    print(f"Agent: {row.get('agent') or 'unknown'}")
    if row.get("sprint_id"):
        print(f"Sprint: {row['sprint_id']}")
    print(f"Started: {_format_full_timestamp(row.get('started_at'))}")
    print(f"Completed: {_format_full_timestamp(row.get('completed_at'))}")
    print(f"Summary: {row.get('summary') or 'No summary recorded.'}")
    print("")

    captures = _load_json_array(row.get("captures"))
    print("=== Captures ===")
    if not captures:
        print("No captures recorded.")
    else:
        for capture in captures:
            ts = capture.get("timestamp")
            category = capture.get("category", "entry").title()
            print(f"[{category}] {_format_full_timestamp(ts)}")
            print(f"  {capture.get('content', 'No content provided.')}")
            if capture.get("context"):
                print(f"  Context: {capture['context']}")
            print("")

    next_steps = _load_json_array(row.get("next_steps"))
    print("=== Next Steps ===")
    if next_steps:
        for step in next_steps:
            print(f"• {step}")
    else:
        print("No next steps recorded.")


def _session_search(env: Environment, args: argparse.Namespace) -> None:
    client = _open_client(env)
    try:
        params: Dict[str, Any] = {
            "pattern": f"%{args.query.lower()}%",
            "limit": args.limit,
        }
        rows = client.fetchall(
            """
            SELECT id, type, title, summary, captures, started_at, completed_at
              FROM sessions
             WHERE LOWER(COALESCE(title, '')) LIKE :pattern
                OR LOWER(COALESCE(summary, '')) LIKE :pattern
                OR LOWER(COALESCE(captures, '')) LIKE :pattern
                OR LOWER(COALESCE(next_steps, '')) LIKE :pattern
             ORDER BY COALESCE(completed_at, started_at) DESC
             LIMIT :limit
            """,
            params,
        )
    finally:
        client.close()

    category = (args.category or "").lower()
    print(f'=== Search Results for "{args.query}" ===')
    if not rows:
        print("No sessions matched the search query.")
        return

    matches = 0
    for row in rows:
        captures = _load_json_array(row.get("captures"))
        title = row.get("title") or row.get("id")
        snippet = row.get("summary") or ""
        capture_match = None
        for capture in captures:
            cat = (capture.get("category") or "").lower()
            content = capture.get("content") or ""
            text = f"{content} {capture.get('context') or ''}".lower()
            if category and cat != category:
                continue
            if (
                args.query.lower() in text
                or args.query.lower() in (title or "").lower()
                or args.query.lower() in snippet.lower()
            ):
                capture_match = capture
                break
        if category and capture_match is None:
            continue

        matches += 1
        session_id = row.get("id")
        session_type = (row.get("type") or "session").title()
        print(f"{session_id} [{session_type}] {title}")
        if capture_match:
            print(
                f"  [{capture_match.get('category', 'entry').title()}] {capture_match.get('content')}"
            )
        else:
            print(f"  Summary: {snippet or 'No summary available.'}")
        print(
            f"  When: {_format_relative_timestamp(row.get('completed_at') or row.get('started_at'))}"
        )
        print("")

    if matches == 0:
        print("No sessions matched the category filter.")


def _load_backlog(client: SQLiteClient) -> Dict[str, Any]:
    sprints = client.fetchall(
        "SELECT id, title, focus, status, start_date, end_date, total_missions, completed_missions "
        "FROM sprints ORDER BY COALESCE(start_date, '') ASC, id ASC"
    )
    missions = client.fetchall(
        "SELECT id, sprint_id, name, status, completed_at, notes, metadata "
        "FROM missions ORDER BY sprint_id ASC, id ASC"
    )
    dependencies = client.fetchall(
        "SELECT from_id, to_id, type FROM mission_dependencies ORDER BY from_id, to_id"
    )
    prompts = client.fetchall(
        "SELECT prompt, behavior FROM prompt_mappings ORDER BY id"
    )

    missions_by_sprint: Dict[str, List[Dict[str, Any]]] = {}
    for mission in missions:
        sprint_id = mission.get("sprint_id")
        bucket = missions_by_sprint.setdefault(sprint_id, [])
        entry: Dict[str, Any] = {
            "id": mission.get("id"),
            "name": mission.get("name"),
            "status": mission.get("status"),
        }
        if mission.get("completed_at"):
            entry["completed_at"] = mission["completed_at"]
        if mission.get("notes"):
            entry["notes"] = mission["notes"]
        if mission.get("metadata"):
            try:
                entry["metadata"] = json.loads(mission["metadata"])
            except json.JSONDecodeError:
                entry["metadata"] = mission["metadata"]
        bucket.append(entry)

    sprint_documents: List[Dict[str, Any]] = []
    for sprint in sprints:
        sprint_documents.append(
            {
                "sprintId": sprint.get("id"),
                "title": sprint.get("title"),
                "focus": sprint.get("focus"),
                "status": sprint.get("status"),
                "startDate": sprint.get("start_date"),
                "endDate": sprint.get("end_date"),
                "totalMissions": sprint.get("total_missions"),
                "completedMissions": sprint.get("completed_missions"),
                "missions": missions_by_sprint.get(sprint.get("id"), []),
            }
        )

    dependencies_doc = [
        {"from": row.get("from_id"), "to": row.get("to_id"), "type": row.get("type")}
        for row in dependencies
    ]

    prompt_doc = [
        {"prompt": row.get("prompt"), "agentBehavior": row.get("behavior")}
        for row in prompts
    ]

    return {
        "sprints": sprint_documents,
        "dependencies": dependencies_doc,
        "prompts": prompt_doc,
    }


def _print_backlog(backlog: Dict[str, Any]) -> None:
    sprints = backlog.get("sprints") or []
    if not sprints:
        print("No sprints defined in the database.")
        return
    for sprint in sprints:
        sprint_id = sprint.get("sprintId") or "UNSET"
        print(f"[{sprint_id}] {sprint.get('title') or '(untitled sprint)'}")
        status = sprint.get("status") or "unknown"
        print(f"  status: {status}")
        window = " - ".join(
            filter(None, [sprint.get("startDate"), sprint.get("endDate")])
        )
        if window:
            print(f"  window: {window}")
        missions = sprint.get("missions") or []
        if not missions:
            print("  (no missions)\n")
            continue
        for mission in missions:
            line = f"  - {mission.get('id')}: {mission.get('name')} [{mission.get('status') or 'unknown'}]"
            if mission.get("completed_at"):
                line += f" completed {mission['completed_at']}"
            print(line)
            notes = mission.get("notes")
            if notes:
                print(f"      notes: {notes}")
        print()


def _show_current(client: SQLiteClient) -> None:
    project = client.get_context("project_context") or {}
    missions = client.fetchall(
        "SELECT id, name, status, completed_at, notes FROM missions "
        "WHERE status IN ('Current', 'In Progress') ORDER BY completed_at IS NOT NULL, id"
    )

    active_mission_id = (project.get("working_memory") or {}).get("active_mission")
    if active_mission_id:
        print(f"Active mission from context: {active_mission_id}")
    else:
        print("Active mission not set in project context.")

    if not missions:
        print("No missions currently marked as In Progress or Current.")
        return

    print("Tracked missions in progress:")
    for mission in missions:
        line = (
            f"- {mission.get('id')}: {mission.get('name')} [{mission.get('status')}]."
        )
        if mission.get("completed_at"):
            line += f" completed {mission['completed_at']}"
        print(line)
        if mission.get("notes"):
            print(f"    notes: {mission['notes']}")


def _export_contexts(env: Environment, args: argparse.Namespace) -> None:
    output_root = (args.output_root or env.root).resolve()
    project_path = output_root / "PROJECT_CONTEXT.json"
    master_path = output_root / "context" / "MASTER_CONTEXT.json"
    client = _open_client(env)
    try:
        project = client.get_context("project_context") or {}
        master = client.get_context("master_context") or {}
    finally:
        client.close()

    project_path.parent.mkdir(parents=True, exist_ok=True)
    master_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    master_path.write_text(
        json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported project context to {project_path}")
    print(f"Exported master context to {master_path}")


def _export_backlog(
    env: Environment, output: Optional[Path] = None, *, quiet: bool = False
) -> Path:
    if yaml is None:
        raise SystemExit("PyYAML is required for backlog export. Install pyyaml first.")
    output_path = (output or (env.root / "missions" / "backlog.yaml")).resolve()
    client = _open_client(env)
    try:
        backlog = _load_backlog(client)
    finally:
        client.close()

    metadata_doc = {
        "name": "Planning.SprintPlan.v1",
        "version": "0.0.0",
        "displayName": "CMOS Backlog Export",
        "description": "Backlog export generated from the CMOS SQLite database.",
        "author": "CMOS",
        "schema": "./schemas/SprintPlan.v1.json",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    domain_fields = {
        "type": "Planning.SprintPlan.v1",
        "sprints": backlog["sprints"],
        "missionDependencies": backlog["dependencies"],
        "promptMapping": {"prompts": backlog["prompts"]},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump_all(
            [metadata_doc, {"domainFields": domain_fields}], handle, sort_keys=False
        )
    if not quiet:
        print(f"Exported backlog to {output_path}")
    return output_path


def _sync_backlog(env: Environment) -> Path:
    path = _export_backlog(env, quiet=True)
    print(f"Backlog synced to {path}")
    return path


def _export_mission_yaml(
    env: Environment, mission_id: str, output_dir: Optional[Path] = None
) -> Path:
    """Export a single mission's full YAML specification from database."""
    if yaml is None:
        raise SystemExit("PyYAML is required for mission export. Install pyyaml first.")

    client = _open_client(env)
    try:
        row = client.fetchone(
            """
            SELECT id, sprint_id, name, objective, context, 
                   success_criteria, deliverables, reference_docs, domain_fields
            FROM missions WHERE id = :id
            """,
            {"id": mission_id},
        )
        if not row:
            raise SystemExit(f"Mission {mission_id} not found in database.")
    finally:
        client.close()

    # Build mission YAML structure
    mission_doc = {
        "missionId": row["id"],
        "objective": row["objective"] or "",
        "context": row["context"] or "",
    }

    # Parse JSON fields
    if row["success_criteria"]:
        mission_doc["successCriteria"] = json.loads(row["success_criteria"])
    if row["deliverables"]:
        mission_doc["deliverables"] = json.loads(row["deliverables"])
    if row["reference_docs"]:
        mission_doc["references"] = json.loads(row["reference_docs"])
    if row["domain_fields"]:
        mission_doc["domainFields"] = json.loads(row["domain_fields"])

    # Determine output path
    base_dir = output_dir or (env.root / "missions" / row["sprint_id"])
    base_dir = base_dir.resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from mission name
    safe_name = row["name"].replace(":", "_").replace(" ", "_").replace("/", "-")
    output_path = base_dir / f"{row['id']}_{safe_name}.yaml"

    # Write YAML file with comment header
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"# Mission File: {output_path.name}\n\n")
        yaml.safe_dump(mission_doc, f, sort_keys=False, allow_unicode=True)

    return output_path


def _export_all_missions(env: Environment, output_root: Optional[Path] = None) -> int:
    """Export all missions as YAML files organized by sprint."""
    if yaml is None:
        raise SystemExit("PyYAML is required for mission export. Install pyyaml first.")

    base_dir = (output_root or (env.root / "missions")).resolve()
    client = _open_client(env)
    try:
        rows = client.fetchall(
            """
            SELECT id, sprint_id FROM missions 
            WHERE objective IS NOT NULL
            ORDER BY sprint_id, id
            """
        )
    finally:
        client.close()

    count = 0
    for row in rows:
        sprint_dir = base_dir / row["sprint_id"]
        _export_mission_yaml(env, row["id"], sprint_dir)
        count += 1

    return count


def _context_snapshot(
    env: Environment,
    context_id: str,
    session_id: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Take a snapshot of the specified context."""
    full_context_id = f"{context_id}_context"
    client = _open_client(env)
    try:
        context = client.get_context(full_context_id)
        if not context:
            raise SystemExit(f"Context '{context_id}' not found in database.")

        was_added = client.add_context_snapshot(
            full_context_id, context, session_id=session_id, source=source
        )

        if was_added:
            print(f"Snapshot created for {context_id}_context")
            if source:
                print(f"Source: {source}")
        else:
            print(f"No changes detected in {context_id}_context (snapshot not created)")
    finally:
        client.close()


def _context_history(env: Environment, context_id: str, limit: int = 10) -> None:
    """View snapshot history for a context."""
    full_context_id = f"{context_id}_context"
    client = _open_client(env)
    try:
        snapshots = client.fetchall(
            """
            SELECT id, session_id, source, created_at, content_hash
            FROM context_snapshots
            WHERE context_id = :context_id
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"context_id": full_context_id, "limit": limit},
        )

        if not snapshots:
            print(f"No snapshots found for {context_id}_context")
            return

        print(
            f"\nSnapshot History for {context_id}_context ({len(snapshots)} shown):\n"
        )
        for snap in snapshots:
            print(f"ID: {snap['id']}")
            print(f"  Created: {snap['created_at']}")
            if snap["session_id"]:
                print(f"  Session: {snap['session_id']}")
            if snap["source"]:
                print(f"  Source: {snap['source']}")
            print(f"  Hash: {snap['content_hash'][:16]}...")
            print()
    finally:
        client.close()


def _context_view_snapshot(env: Environment, snapshot_id: int) -> None:
    """View a specific snapshot."""
    client = _open_client(env)
    try:
        snapshot = client.fetchone(
            """
            SELECT id, context_id, session_id, source, content, created_at
            FROM context_snapshots
            WHERE id = :id
            """,
            {"id": snapshot_id},
        )

        if not snapshot:
            raise SystemExit(f"Snapshot {snapshot_id} not found.")

        print(f"\nSnapshot ID: {snapshot['id']}")
        print(f"Context: {snapshot['context_id']}")
        print(f"Created: {snapshot['created_at']}")
        if snapshot["session_id"]:
            print(f"Session: {snapshot['session_id']}")
        if snapshot["source"]:
            print(f"Source: {snapshot['source']}")
        print("\n--- Content ---\n")
        print(snapshot["content"])
    finally:
        client.close()


def _context_render_view(env: Environment, args: argparse.Namespace) -> None:
    """Render an aggregated context view with optional filters."""

    client = _open_client(env)
    try:
        if args.domain:
            view = get_domain_view(
                client,
                args.domain,
                as_of=args.as_of,
                recent_limit=args.recent_limit,
            )
        elif args.as_of:
            view = get_context_at_point(
                client,
                as_of=args.as_of,
                recent_limit=args.recent_limit,
            )
        else:
            view = get_master_context_view(
                client,
                recent_limit=args.recent_limit,
            )
        rendered = export_context_view(view, args.format)
    except ContextViewError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        client.close()

    print(rendered)


def _decisions_list(env: Environment, limit: int, domain: Optional[str] = None) -> None:
    """List strategic decisions."""
    client = _open_client(env)
    try:
        query = "SELECT id, decision_text, created_at, project_domain, sprint_id FROM strategic_decisions"
        params: Dict[str, Any] = {"limit": limit}

        if domain:
            query += " WHERE project_domain = :domain"
            params["domain"] = domain

        query += " ORDER BY created_at DESC LIMIT :limit"

        decisions = client.fetchall(query, params)

        if not decisions:
            print("No strategic decisions found.")
            return

        print(f"\nStrategic Decisions ({len(decisions)} shown):\n")
        for dec in decisions:
            print(f"ID: {dec['id']}")
            print(f"  Date: {dec['created_at']}")
            if dec["project_domain"]:
                print(f"  Domain: {dec['project_domain']}")
            if dec["sprint_id"]:
                print(f"  Sprint: {dec['sprint_id']}")
            print(
                f"  Decision: {dec['decision_text'][:100]}{'...' if len(dec['decision_text']) > 100 else ''}"
            )
            print()
    finally:
        client.close()


def _decisions_search(
    env: Environment, keyword: str, domain: Optional[str] = None
) -> None:
    """Search decisions by keyword."""
    client = _open_client(env)
    try:
        query = """
            SELECT id, decision_text, created_at, project_domain, sprint_id 
            FROM strategic_decisions 
            WHERE decision_text LIKE :keyword
        """
        params: Dict[str, Any] = {"keyword": f"%{keyword}%"}

        if domain:
            query += " AND project_domain = :domain"
            params["domain"] = domain

        query += " ORDER BY created_at DESC"

        decisions = client.fetchall(query, params)

        if not decisions:
            print(f"No decisions found matching '{keyword}'.")
            return

        print(f"\nFound {len(decisions)} decision(s) matching '{keyword}':\n")
        for dec in decisions:
            print(f"ID: {dec['id']} | {dec['created_at']}")
            if dec["project_domain"]:
                print(f"  Domain: {dec['project_domain']}")
            print(f"  {dec['decision_text']}")
            print()
    finally:
        client.close()


def _decisions_by_sprint(env: Environment, sprint_id: str) -> None:
    """Show decisions linked to a sprint."""
    client = _open_client(env)
    try:
        decisions = client.fetchall(
            """
            SELECT id, decision_text, created_at, project_domain 
            FROM strategic_decisions 
            WHERE sprint_id = :sprint_id
            ORDER BY created_at
            """,
            {"sprint_id": sprint_id},
        )

        if not decisions:
            print(f"No decisions found for sprint '{sprint_id}'.")
            return

        print(f"\nStrategic Decisions for {sprint_id} ({len(decisions)} total):\n")
        for dec in decisions:
            print(f"ID: {dec['id']} | {dec['created_at']}")
            if dec["project_domain"]:
                print(f"  Domain: {dec['project_domain']}")
            print(f"  {dec['decision_text']}")
            print()
    finally:
        client.close()


def _validate_foundational_refs(env: Environment) -> None:
    failures: List[str] = []
    for relative_path, rules in FOUNDATIONAL_CHECKS.items():
        file_path = env.root / relative_path
        required = rules.get("required", [])
        forbidden = rules.get("forbidden", [])
        try:
            content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            failures.append(f"{relative_path}: missing file")
            continue
        for needle in required:
            if needle not in content:
                failures.append(
                    f"{relative_path}: missing required reference '{needle}'"
                )
        for needle in forbidden:
            if needle in content:
                failures.append(
                    f"{relative_path}: contains forbidden reference '{needle}'"
                )

    if failures:
        print("Foundational reference validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)

    print("Foundational reference validation succeeded.")


def _validate_health(env: Environment) -> None:
    runtime = _build_runtime(env)
    try:
        runtime.ensure_database()
    finally:
        runtime.close()
    print(f"Database {env.db_path} is reachable and passed health checks.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CMOS helper CLI")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to the cmos/ directory (auto-detected when omitted).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Path to the CMOS SQLite database (default: <root>/db/cmos.sqlite)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    mission_parser = subparsers.add_parser("mission", help="Mission lifecycle helpers")
    mission_sub = mission_parser.add_subparsers(dest="mission_command", required=True)

    mission_status = mission_sub.add_parser(
        "status", help="Show queued and active missions"
    )
    mission_status.add_argument(
        "--limit", type=int, default=5, help="Maximum missions to display"
    )

    mission_show = mission_sub.add_parser(
        "show", help="Display full mission specification"
    )
    mission_show.add_argument("mission_id", help="Mission identifier (e.g. B3.3)")
    mission_show.add_argument(
        "--format", choices=["full", "compact"], default="full", help="Output format"
    )

    mission_start = mission_sub.add_parser(
        "start", help="Mark a mission as In Progress"
    )
    mission_start.add_argument("mission_id", help="Mission identifier (e.g. B3.3)")
    mission_start.add_argument(
        "--summary", required=True, help="Session summary to log"
    )
    mission_start.add_argument(
        "--agent", default="codex", help="Agent identifier for session logging"
    )
    mission_start.add_argument("--ts", help="ISO timestamp override (UTC)")

    mission_complete = mission_sub.add_parser(
        "complete", help="Mark a mission as Completed"
    )
    mission_complete.add_argument("mission_id", help="Mission identifier (e.g. B3.3)")
    mission_complete.add_argument("--summary", required=True, help="Completion summary")
    mission_complete.add_argument(
        "--notes", required=True, help="Notes to persist in the backlog"
    )
    mission_complete.add_argument(
        "--agent", default="codex", help="Agent identifier for session logging"
    )
    mission_complete.add_argument("--ts", help="ISO timestamp override (UTC)")
    mission_complete.add_argument(
        "--next-hint", help="Optional follow-up hint to include in the session log"
    )
    mission_complete.add_argument(
        "--no-promote",
        action="store_true",
        help="Do not promote the next queued mission",
    )
    mission_complete.add_argument(
        "--immediate",
        action="store_true",
        help="Promote the next mission directly to In Progress",
    )

    mission_block = mission_sub.add_parser("block", help="Mark a mission as Blocked")
    mission_block.add_argument("mission_id", help="Mission identifier (e.g. B3.3)")
    mission_block.add_argument(
        "--summary", required=True, help="Short summary of the blocker"
    )
    mission_block.add_argument(
        "--reason", required=True, help="Reason stored in mission notes"
    )
    mission_block.add_argument(
        "--need", action="append", default=[], help="Follow-up need (can be repeated)"
    )
    mission_block.add_argument(
        "--agent", default="codex", help="Agent identifier for session logging"
    )
    mission_block.add_argument("--ts", help="ISO timestamp override (UTC)")
    mission_block.add_argument(
        "--next-hint", help="Optional hint to include in the session log"
    )

    mission_add = mission_sub.add_parser(
        "add", help="Add a mission to the backlog database"
    )
    mission_add.add_argument("mission_id", help="Mission identifier (e.g. B4.1)")
    mission_add.add_argument("name", help="Mission display name")
    mission_add.add_argument("--sprint", required=True, help="Sprint identifier")
    mission_add.add_argument(
        "--status", default="Queued", help="Initial mission status (default: Queued)"
    )
    mission_add.add_argument("--notes", help="Optional mission notes")
    mission_add.add_argument("--description", help="Description stored in metadata")
    mission_add.add_argument(
        "--success",
        action="append",
        default=None,
        help="Success criteria entry (repeatable)",
    )
    mission_add.add_argument(
        "--deliverable",
        action="append",
        default=None,
        help="Deliverable entry (repeatable)",
    )
    mission_add.add_argument(
        "--metadata", help="Raw JSON merged into metadata (object)"
    )

    mission_update = mission_sub.add_parser(
        "update", help="Update mission fields in the backlog"
    )
    mission_update.add_argument("mission_id", help="Mission identifier to update")
    mission_update.add_argument("--name", help="New mission name")
    mission_update.add_argument("--status", help="New mission status")
    mission_update.add_argument("--sprint", help="Move mission to another sprint")
    mission_update.add_argument("--notes", default=None, help="Replace mission notes")
    mission_update.add_argument("--description", help="Override metadata description")
    mission_update.add_argument(
        "--success",
        action="append",
        default=None,
        help="Replace success criteria (repeatable)",
    )
    mission_update.add_argument(
        "--deliverable",
        action="append",
        default=None,
        help="Replace deliverables (repeatable)",
    )
    mission_update.add_argument("--metadata", help="JSON merged into metadata (object)")

    mission_depends = mission_sub.add_parser(
        "depends", help="Add or update mission dependencies"
    )
    mission_depends.add_argument("from_id", help="Mission that blocks another")
    mission_depends.add_argument("to_id", help="Mission that is blocked")
    mission_depends.add_argument(
        "--type",
        dest="dep_type",
        default="Blocks",
        help="Dependency label (default: Blocks)",
    )

    research_parser = subparsers.add_parser("research", help="Research mission helpers")
    research_sub = research_parser.add_subparsers(
        dest="research_command", required=True
    )
    research_export = research_sub.add_parser(
        "export", help="Export a mission's research findings to Markdown"
    )
    research_export.add_argument("mission_id", help="Mission identifier to export")
    research_export.add_argument(
        "--output",
        type=Path,
        help="Destination path (default: <root>/research/<mission-id>.md)",
    )
    research_export.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the destination file if it already exists",
    )
    research_export.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow exporting missions that have not been completed yet",
    )

    db_parser = subparsers.add_parser("db", help="Database inspection and exports")
    db_sub = db_parser.add_subparsers(dest="db_command", required=True)

    db_show = db_sub.add_parser("show", help="Display backlog or current mission state")
    db_show.add_argument(
        "view",
        choices=["backlog", "current"],
        nargs="?",
        default="backlog",
        help="Data to display",
    )

    db_export = db_sub.add_parser(
        "export", help="Export contexts or backlog from the database"
    )
    db_export.add_argument(
        "artifact", choices=["backlog", "contexts"], help="Artifact to export"
    )
    db_export.add_argument(
        "--output",
        type=Path,
        help="Backlog export destination (default: cmos/missions/backlog.yaml)",
    )
    db_export.add_argument(
        "--output-root",
        type=Path,
        help="Root directory for context exports (default: cmos root)",
    )

    db_export_missions = db_sub.add_parser(
        "export-missions", help="Export mission YAML files from database"
    )
    db_export_missions.add_argument(
        "mission_id",
        nargs="?",
        help="Specific mission ID to export (exports all if omitted)",
    )
    db_export_missions.add_argument(
        "--output-dir", type=Path, help="Output directory for mission YAML files"
    )

    context_parser = subparsers.add_parser(
        "context", help="Context management commands"
    )
    context_sub = context_parser.add_subparsers(dest="context_command", required=True)

    context_snapshot = context_sub.add_parser(
        "snapshot", help="Take a snapshot of a context"
    )
    context_snapshot.add_argument(
        "context_id", choices=["project", "master"], help="Context to snapshot"
    )
    context_snapshot.add_argument("--session", help="Session ID for this snapshot")
    context_snapshot.add_argument(
        "--source", help="Source description for this snapshot"
    )

    context_history = context_sub.add_parser(
        "history", help="View snapshot history for a context"
    )
    context_history.add_argument(
        "context_id", choices=["project", "master"], help="Context to view history for"
    )
    context_history.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of snapshots to show (default: 10)",
    )

    context_view = context_sub.add_parser(
        "view", help="Render aggregated context or snapshot views"
    )
    context_view.add_argument(
        "--snapshot",
        type=int,
        help="Snapshot ID to display instead of building a live view",
    )
    context_view.add_argument(
        "--as-of",
        help="ISO timestamp or session ID for historical views",
    )
    context_view.add_argument(
        "--domain",
        help="Project domain filter (requires session metadata domain)",
    )
    context_view.add_argument(
        "--format",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format for aggregated views (default: json)",
    )
    context_view.add_argument(
        "--recent-limit",
        type=int,
        default=10,
        dest="recent_limit",
        help="Number of recent sessions to include (default: 10)",
    )

    decisions_parser = subparsers.add_parser(
        "decisions", help="Query strategic decisions from MASTER_CONTEXT"
    )
    decisions_sub = decisions_parser.add_subparsers(
        dest="decisions_command", required=True
    )

    decisions_list = decisions_sub.add_parser(
        "list", help="List all strategic decisions"
    )
    decisions_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of decisions to show (default: 20)",
    )
    decisions_list.add_argument(
        "--domain", help="Filter by project domain (e.g., 'ai-studio')"
    )

    decisions_search = decisions_sub.add_parser(
        "search", help="Search decisions by keyword"
    )
    decisions_search.add_argument(
        "keyword", help="Keyword to search for in decision text"
    )
    decisions_search.add_argument("--domain", help="Filter by project domain")

    decisions_by_sprint = decisions_sub.add_parser(
        "by-sprint", help="Show decisions linked to a sprint"
    )
    decisions_by_sprint.add_argument(
        "sprint_id", help="Sprint ID (e.g., 'Sprint 03', 'sprint-03')"
    )

    session_parser = subparsers.add_parser(
        "session",
        help="Manage planning/onboarding/review sessions",
        description=(
            "Capture non-build work such as planning, onboarding, reviews, and research. "
            "Each command writes to the session timeline and updates project/master context. "
            "See docs/session-management-guide.md for walkthroughs and templates."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    session_sub = session_parser.add_subparsers(dest="session_command", required=True)

    session_start = session_sub.add_parser(
        "start",
        help="Start a planning/onboarding session",
        description=(
            "Begin a new session for planning, onboarding, review, research, check-ins, or custom work. "
            "Sessions are mutually exclusive—complete or resume an active session before starting another."
        ),
    )
    session_start.add_argument(
        "--type",
        dest="session_type",
        required=True,
        choices=["onboarding", "planning", "review", "research", "check-in", "custom"],
        help="Session type",
    )
    session_start.add_argument(
        "--title", required=True, help="Descriptive session title"
    )
    session_start.add_argument("--sprint", help="Optional sprint identifier")
    session_start.add_argument(
        "--agent", default="assistant", help="Agent identifier for session logging"
    )

    session_capture = session_sub.add_parser(
        "capture",
        help="Capture an insight for the active session",
        description=(
            "Log a decision, learning, constraint, context note, or next-step while a session is active. "
            "Categories must be one of: decision, learning, constraint, context, next-step."
        ),
    )
    session_capture.add_argument(
        "category",
        choices=["decision", "learning", "constraint", "context", "next-step"],
        help="Capture category",
    )
    session_capture.add_argument("content", help="Insight content to record")
    session_capture.add_argument(
        "--context", help="Additional context for this capture"
    )
    session_capture.add_argument(
        "--session", help="Override session ID (default: active session)"
    )
    session_capture.add_argument(
        "--agent", default="assistant", help="Agent identifier for session logging"
    )

    session_complete = session_sub.add_parser(
        "complete",
        help="Complete the active session",
        description=(
            "Close the active session, summarize outcomes, and optionally record next steps that feed "
            "project/master context. All captures are aggregated when you complete the session."
        ),
    )
    session_complete.add_argument("--summary", required=True, help="Session summary")
    session_complete.add_argument(
        "--next-steps",
        action="append",
        default=None,
        help="Next-step entry (repeatable)",
    )
    session_complete.add_argument(
        "--session", help="Override session ID (default: active session)"
    )
    session_complete.add_argument(
        "--agent", default="assistant", help="Agent identifier for session logging"
    )
    session_onboard = session_sub.add_parser(
        "onboard", help="Show a consolidated onboarding report"
    )
    session_list = session_sub.add_parser(
        "list", help="List recent sessions with optional filters"
    )
    session_list.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of sessions to display (default: 10)",
    )
    session_list.add_argument("--type", help="Filter by session type (e.g., planning)")
    session_list.add_argument(
        "--status", choices=["active", "completed"], help="Filter by session status"
    )

    session_show = session_sub.add_parser(
        "show", help="Display detailed information for a session"
    )
    session_show.add_argument(
        "session_id", help="Session identifier (e.g., PS-2024-11-13-001)"
    )

    session_search = session_sub.add_parser("search", help="Search session history")
    session_search.add_argument("query", help="Search term or phrase")
    session_search.add_argument(
        "--category",
        choices=["decision", "learning", "constraint", "context", "next-step"],
        help="Limit results to captures in the specified category",
    )
    session_search.add_argument(
        "--limit", type=int, default=20, help="Maximum results to inspect (default: 20)"
    )

    validate_parser = subparsers.add_parser(
        "validate", help="Project validation commands"
    )
    validate_sub = validate_parser.add_subparsers(
        dest="validate_command", required=True
    )
    validate_sub.add_parser("health", help="Run a database health check")
    validate_sub.add_parser("docs", help="Validate foundational document references")

    return parser


def _handle_mission(env: Environment, args: argparse.Namespace) -> None:
    if args.mission_command == "status":
        _mission_status_cmd(env, args)
    elif args.mission_command == "show":
        _mission_show_cmd(env, args)
    elif args.mission_command == "start":
        _mission_start(env, args)
    elif args.mission_command == "complete":
        _mission_complete(env, args)
    elif args.mission_command == "block":
        _mission_block(env, args)
    elif args.mission_command == "add":
        _mission_add(env, args)
    elif args.mission_command == "update":
        _mission_update(env, args)
    elif args.mission_command == "depends":
        _mission_depends(env, args)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown mission subcommand")


def _handle_research(env: Environment, args: argparse.Namespace) -> None:
    if args.research_command == "export":
        _research_export(env, args)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown research subcommand")


def _handle_db(env: Environment, args: argparse.Namespace) -> None:
    if args.db_command == "show":
        client = _open_client(env)
        try:
            if args.view == "current":
                _show_current(client)
            else:
                backlog = _load_backlog(client)
                _print_backlog(backlog)
        finally:
            client.close()
    elif args.db_command == "export":
        if args.artifact == "contexts":
            _export_contexts(env, args)
        else:
            _export_backlog(env, args.output)
    elif args.db_command == "export-missions":
        if args.mission_id:
            output_path = _export_mission_yaml(env, args.mission_id, args.output_dir)
            print(f"Exported mission {args.mission_id} to {output_path}")
        else:
            count = _export_all_missions(env, args.output_dir)
            print(
                f"Exported {count} mission(s) to {args.output_dir or (env.root / 'missions')}"
            )
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown db subcommand")


def _handle_context(env: Environment, args: argparse.Namespace) -> None:
    if args.context_command == "snapshot":
        _context_snapshot(env, args.context_id, args.session, args.source)
    elif args.context_command == "history":
        _context_history(env, args.context_id, args.limit)
    elif args.context_command == "view":
        if args.snapshot is not None:
            _context_view_snapshot(env, args.snapshot)
        else:
            _context_render_view(env, args)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown context subcommand")


def _handle_decisions(env: Environment, args: argparse.Namespace) -> None:
    if args.decisions_command == "list":
        _decisions_list(env, args.limit, args.domain)
    elif args.decisions_command == "search":
        _decisions_search(env, args.keyword, args.domain)
    elif args.decisions_command == "by-sprint":
        _decisions_by_sprint(env, args.sprint_id)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown decisions subcommand")


def _handle_session(env: Environment, args: argparse.Namespace) -> None:
    if args.session_command == "start":
        _session_start(env, args)
    elif args.session_command == "capture":
        _session_capture(env, args)
    elif args.session_command == "complete":
        _session_complete(env, args)
    elif args.session_command == "onboard":
        _session_onboard(env, args)
    elif args.session_command == "list":
        _session_list(env, args)
    elif args.session_command == "show":
        _session_show(env, args)
    elif args.session_command == "search":
        _session_search(env, args)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown session subcommand")


def _handle_validate(env: Environment, args: argparse.Namespace) -> None:
    if args.validate_command == "health":
        _validate_health(env)
    elif args.validate_command == "docs":
        _validate_foundational_refs(env)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit("Unknown validate subcommand")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = _resolve_environment(args)

    try:
        if args.command == "mission":
            _handle_mission(env, args)
        elif args.command == "research":
            _handle_research(env, args)
        elif args.command == "db":
            _handle_db(env, args)
        elif args.command == "context":
            _handle_context(env, args)
        elif args.command == "decisions":
            _handle_decisions(env, args)
        elif args.command == "session":
            _handle_session(env, args)
        elif args.command == "validate":
            _handle_validate(env, args)
        else:  # pragma: no cover - argparse guards this
            parser.error("Unknown command")
    except SessionError as error:
        _print_session_error(error)
        return 1
    except (MissionRuntimeError, SQLiteClientError) as error:
        _print_generic_error(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
