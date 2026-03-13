#!/usr/bin/env python3
"""Migrate existing JSONL telemetry files to the unified envelope format.

Usage:
    python scripts/migrate_telemetry_format.py              # dry-run (report only)
    python scripts/migrate_telemetry_format.py --apply       # apply migration
    python scripts/migrate_telemetry_format.py --file FILE   # migrate single file

The migration wraps each legacy event in the unified envelope:
    { ts, event_type, source, payload, sprint_id? }

Events already in envelope format are left untouched.
Original files are backed up to *.pre-migration before modification.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))
from app.core.telemetry import TelemetryEnvelope, is_envelope_format  # noqa: E402

# Map file path patterns → (source, event_type) defaults
SOURCE_MAP: dict[str, tuple[str, str]] = {
    "quality-automation": ("quality", "quality.automation.check"),
    "quality-gates": ("quality", "quality.gate.evaluation"),
    "benchmark-history": ("pedr", "pedr.benchmark.comparison"),
    "graph-tuning": ("pedr", "pedr.graph.telemetry"),
    "graph-quality": ("pedr", "pedr.graph.quality_report"),
    "sprint-04-performance": ("tracelab", "cost.monitor.event"),
    "sprint-10-deepsearch": ("tracelab", "deepsearch.ingestion"),
    "sprint-11-pedr-sync": ("pedr", "pedr.sync.event"),
    "sprint-11-preflight": ("pedr", "pedr.preflight.evaluation"),
    "sprint-18-pedr-baseline": ("pedr", "pedr.baseline.capture"),
    "sprint-26-graph": ("pedr", "pedr.graph.telemetry"),
    "database-health": ("cmos", "cmos.database.health"),
    "ingestion-cli": ("tracelab", "ingestion.cli.smoke"),
    "sprint-03": ("tracelab", "tracelab.sprint03.event"),
    "sprint-04-playwright": ("tracelab", "tracelab.playwright.migration"),
    "sprint-04-quality": ("quality", "quality.automation.check"),
    "sprint-04-test": ("quality", "quality.test.coverage"),
    "sprint-05": ("tracelab", "tracelab.sprint05.event"),
    "sprint-06": ("cmos", "cmos.sprint.retrospective"),
    "sprint-07": ("cmos", "cmos.sprint.event"),
    "sprint-08": ("tracelab", "tracelab.sprint08.event"),
    "sprint-09": ("tracelab", "tracelab.sprint09.event"),
    "sprint-10": ("tracelab", "tracelab.sprint10.event"),
    "sprint-12": ("cmos", "cmos.sprint.retrospective"),
    "sprint-13": ("cmos", "cmos.sprint.retrospective"),
    "sprint-15": ("cmos", "cmos.sprint.retrospective"),
    "sprint-16": ("cmos", "cmos.sprint.retrospective"),
    "sprint-17": ("cmos", "cmos.sprint.retrospective"),
    "cache-metrics": ("tracelab", "cache.metrics.snapshot"),
    "auto-linking": ("tracelab", "evidence.auto_linking"),
    "correction-queue": ("tracelab", "correction.queue.event"),
    "webhooks": ("tracelab", "webhook.delivery.event"),
    "sync-events": ("pedr", "pedr.sync.event"),
}


def _detect_sprint_id(filepath: Path) -> str | None:
    """Extract sprint ID from file path if present."""
    match = re.search(r"sprint-(\d+)", filepath.name)
    return f"sprint-{match.group(1)}" if match else None


def _resolve_source_and_type(filepath: Path, event: dict) -> tuple[str, str]:
    """Determine source and event_type for a legacy event."""
    stem = filepath.stem
    for pattern, (source, event_type) in SOURCE_MAP.items():
        if pattern in stem:
            actual_type = (
                event.get("event_type")
                or event.get("event")
                or event.get("type")
                or event.get("check_type")
                or event_type
            )
            return source, actual_type

    if "cmos" in str(filepath):
        return "cmos", event.get("event_type", event.get("event", "cmos.event"))
    return "tracelab", event.get("event_type", event.get("event", "tracelab.event"))


def migrate_line(line: str, filepath: Path) -> str:
    """Migrate a single JSONL line to envelope format."""
    event = json.loads(line)

    if is_envelope_format(event):
        return line

    source, event_type = _resolve_source_and_type(filepath, event)
    sprint_id = _detect_sprint_id(filepath) or event.get("sprint_id")
    ts = event.pop("ts", None)

    # Remove fields that become part of the envelope
    for key in ("event_type", "event", "type"):
        event.pop(key, None)

    envelope = TelemetryEnvelope(
        ts=ts or "1970-01-01T00:00:00Z",
        event_type=event_type,
        source=source,
        payload=event,
        sprint_id=sprint_id,
    )
    return envelope.to_json()


def migrate_file(filepath: Path, *, apply: bool = False) -> dict:
    """Migrate a JSONL file. Returns migration stats."""
    stats = {
        "path": str(filepath),
        "total": 0,
        "already_migrated": 0,
        "migrated": 0,
        "errors": 0,
    }

    lines = []
    with open(filepath, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            stats["total"] += 1
            try:
                event = json.loads(raw)
                if is_envelope_format(event):
                    stats["already_migrated"] += 1
                    lines.append(raw)
                else:
                    migrated = migrate_line(raw, filepath)
                    stats["migrated"] += 1
                    lines.append(migrated)
            except (json.JSONDecodeError, Exception) as exc:
                stats["errors"] += 1
                lines.append(raw)

    if apply and stats["migrated"] > 0:
        backup = filepath.with_suffix(filepath.suffix + ".pre-migration")
        if not backup.exists():
            shutil.copy2(filepath, backup)
        with open(filepath, "w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")

    return stats


def find_jsonl_files() -> list[Path]:
    """Find all telemetry JSONL files in the project."""
    dirs = [
        PROJECT_ROOT / "telemetry" / "events",
        PROJECT_ROOT / "cmos" / "telemetry" / "events",
    ]
    files = []
    for d in dirs:
        if d.exists():
            files.extend(sorted(d.glob("*.jsonl")))
    return files


def main():
    parser = argparse.ArgumentParser(description="Migrate telemetry JSONL files to unified envelope format")
    parser.add_argument("--apply", action="store_true", help="Apply migration (default: dry-run)")
    parser.add_argument("--file", type=Path, help="Migrate a single file")
    args = parser.parse_args()

    files = [args.file] if args.file else find_jsonl_files()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f" Telemetry Format Migration ({mode})")
    print(f"{'='*60}\n")

    total_migrated = 0
    total_already = 0
    total_events = 0

    for filepath in files:
        if not filepath.exists():
            print(f"  SKIP (not found): {filepath}")
            continue

        stats = migrate_file(filepath, apply=args.apply)
        total_events += stats["total"]
        total_migrated += stats["migrated"]
        total_already += stats["already_migrated"]

        status = "OK" if stats["migrated"] > 0 else "SKIP"
        if stats["already_migrated"] == stats["total"]:
            status = "ALREADY"
        print(
            f"  [{status:7s}] {filepath.name:50s}  "
            f"{stats['total']:4d} events  "
            f"({stats['migrated']} to migrate, {stats['already_migrated']} already ok)"
        )

    print(f"\n{'='*60}")
    print(f" Summary: {total_events} events across {len(files)} files")
    print(f"   To migrate:       {total_migrated}")
    print(f"   Already migrated: {total_already}")
    if not args.apply and total_migrated > 0:
        print(f"\n   Run with --apply to apply migration")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
