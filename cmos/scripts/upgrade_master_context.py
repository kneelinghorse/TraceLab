#!/usr/bin/env python3
"""Convert the legacy TraceLab MASTER_CONTEXT.json into the v2 structure.

The legacy file used a project/working_memory layout that predates the starter.
This script reshapes the payload so the new runtime (session/context helpers)
can rely on the normalized sections that ship with the starter seed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _timestamp() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clean_list(values: Optional[Iterable[Any]]) -> List[Any]:
    if not values:
        return []
    return [value for value in values if value is not None]


def _normalize_decisions(
    decisions: Iterable[Any],
    *,
    source: str,
    default_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for entry in decisions or []:
        if isinstance(entry, dict):
            record = dict(entry)
            record.setdefault("source", source)
            if default_date and not record.get("date"):
                record["date"] = default_date
            normalized.append(record)
        else:
            normalized.append(
                {
                    "decision": str(entry),
                    "source": source,
                    "date": default_date,
                }
            )
    return normalized


def convert(payload: Dict[str, Any]) -> Dict[str, Any]:
    project = payload.get("project") or {}
    working = payload.get("working_memory") or {}
    domain = (working.get("domains") or {}).get("main") or {}
    planning = payload.get("planning") or {}
    technical = payload.get("technical_context") or {}
    sprint_tracking = payload.get("sprint_tracking") or {}

    session_history = working.get("session_history") or []
    session_summaries = planning.get("session_summaries") or []

    decision_entries: List[Dict[str, Any]] = []
    decision_entries.extend(
        _normalize_decisions(
            domain.get("decisions_made") or [], source="working_memory"
        )
    )
    for summary in session_summaries:
        decision_entries.extend(
            _normalize_decisions(
                summary.get("decisions_made") or [],
                source=f"{summary.get('focus') or 'session'} ({summary.get('session_date')})",
                default_date=summary.get("session_date"),
            )
        )

    constraints = _clean_list(domain.get("constraints"))
    quality_standards = {
        "ai_instructions": payload.get("ai_instructions") or {},
        "context_health": payload.get("context_health") or {},
        "testing_protocols": technical.get("integration_testing") or {},
        "sprint_evaluation": domain.get("sprint_evaluation") or {},
    }

    roadmap = {
        "status": {
            "sprint_01": planning.get("sprint_01_status"),
            "sprint_02": planning.get("sprint_02_status"),
            "sprint_03": planning.get("sprint_03_status"),
            "sprint_04": planning.get("sprint_04_status"),
            "sprint_05": planning.get("sprint_05_status"),
        },
        "current_focus": planning.get("current_sprint"),
        "next_checkpoint": planning.get("next_checkpoint"),
        "research_completed": planning.get("sprint_02_research_completed"),
        "queued_build_missions": planning.get("sprint_02_build_missions"),
        "success_criteria": planning.get("sprint_02_success_criteria"),
        "session_summaries": session_summaries,
        "research_links": planning.get("research_to_build_links"),
        "sprint_close_process": planning.get("sprint_close_process"),
        "important_for_review": planning.get("important_for_sprint_02_review"),
        "sprint_focus": planning.get("sprint_05_focus"),
        "sprint_reports": {
            "sprint_01": domain.get("sprint_evaluation", {}).get("sprint_01_report"),
            "sprint_02": domain.get("sprint_evaluation", {}).get("sprint_02_report"),
        },
        "tracking": sprint_tracking,
    }

    operational_memory = {
        "session_history": session_history,
        "blocked_missions": working.get("blocked_missions"),
        "active_mission": working.get("active_mission"),
        "last_completed_mission": working.get("last_completed_mission"),
        "last_blocked_mission": working.get("last_blocked_mission"),
        "next_session_context": payload.get("next_session_context"),
    }

    project_identity = {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "status": project.get("status"),
        "start_date": project.get("start_date"),
        "deployment": project.get("deployment"),
        "session_metrics": {
            "count": working.get("session_count"),
            "last_session": working.get("last_session"),
            "active_domain": working.get("active_domain"),
        },
        "achievements": domain.get("achievements"),
        "files_created": domain.get("files_created"),
        "planning_overview": {
            "current_sprint": planning.get("current_sprint"),
            "session_summaries": session_summaries,
        },
    }

    technical_foundation = {
        "critical_facts": domain.get("critical_facts"),
        "system_components": technical.get("system_components"),
        "dependencies": technical.get("dependencies"),
        "integration_points": technical.get("integration_points"),
        "enhanced_features": technical.get("enhanced_features"),
        "integration_testing": technical.get("integration_testing"),
        "research_findings": technical.get("research_findings"),
    }

    metadata = dict(payload.get("metadata") or {})
    metadata["upgraded_at"] = _timestamp()
    metadata["upgraded_with"] = "upgrade_master_context.py"

    return {
        "project_identity": project_identity,
        "technical_foundation": technical_foundation,
        "decisions_made": decision_entries,
        "constraints": constraints,
        "quality_standards": quality_standards,
        "roadmap": roadmap,
        "operational_memory": operational_memory,
        "metadata": metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade TraceLab master context.")
    parser.add_argument(
        "--context",
        type=Path,
        default=Path("cmos.TraceLab/context/MASTER_CONTEXT.json"),
        help="Path to MASTER_CONTEXT.json to upgrade.",
    )
    args = parser.parse_args()

    path = args.context.resolve()
    if not path.exists():
        raise SystemExit(f"Context file not found: {path}")

    original = json.loads(path.read_text(encoding="utf-8") or "{}")
    upgraded = convert(original)

    backup_path = path.with_suffix(
        path.suffix + f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    backup_path.write_text(
        json.dumps(original, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    path.write_text(
        json.dumps(upgraded, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Backup written to {backup_path}")
    print(f"Upgraded context written to {path}")


if __name__ == "__main__":
    main()
