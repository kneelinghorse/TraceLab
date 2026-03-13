#!/usr/bin/env python3
"""Validate all telemetry JSONL files conform to the unified envelope schema.

Usage:
    python scripts/validate_telemetry_format.py
    python scripts/validate_telemetry_format.py --strict    # fail on any violation
    python scripts/validate_telemetry_format.py --file FILE # validate single file

Exit code 0 if all files pass, 1 if any violations found (strict mode).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.telemetry import validate_jsonl_file  # noqa: E402


def find_jsonl_files() -> list[Path]:
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
    parser = argparse.ArgumentParser(description="Validate telemetry JSONL envelope conformance")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any violation")
    parser.add_argument("--file", type=Path, help="Validate a single file")
    args = parser.parse_args()

    files = [args.file] if args.file else find_jsonl_files()

    print(f"\n{'='*70}")
    print(f" Telemetry Envelope Conformance Report")
    print(f"{'='*70}\n")

    total_files = 0
    total_events = 0
    total_conforming = 0
    total_violations = 0

    for filepath in files:
        result = validate_jsonl_file(filepath)
        if not result.get("exists"):
            print(f"  [MISSING] {filepath}")
            continue

        total_files += 1
        total_events += result["total"]
        total_conforming += result["conforming"]
        total_violations += result["violations"]

        rate = result["conformance_rate"]
        if rate == 1.0:
            status = "PASS"
        elif rate >= 0.5:
            status = "PARTIAL"
        else:
            status = "FAIL"

        print(
            f"  [{status:7s}] {filepath.name:50s}  "
            f"{result['conforming']:4d}/{result['total']:4d} "
            f"({rate:.0%})"
        )
        if result["first_violations"]:
            for v in result["first_violations"][:2]:
                print(f"            Line {v['line']}: {v['error']} {v.get('missing', '')}")

    overall_rate = total_conforming / total_events if total_events else 1.0
    print(f"\n{'='*70}")
    print(f" Summary: {total_files} files, {total_events} events")
    print(f"   Conforming: {total_conforming} ({overall_rate:.1%})")
    print(f"   Violations: {total_violations}")
    print(f"{'='*70}\n")

    if args.strict and total_violations > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
