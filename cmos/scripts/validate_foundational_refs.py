#!/usr/bin/env python3
"""Validate that roadmap and architecture templates are referenced from foundational-docs/.

The rules and the boundary-aware matcher live in cmos/context/foundational_refs.py and
are shared with ``./cmos/cli.py validate docs``. This script stays a manual guard, not a
CI gate.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _find_cmos_root() -> Path:
    """Find cmos/ directory from any working directory."""
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir.parent
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
    raise RuntimeError("Cannot find cmos/ directory. Please run from project root.")


CMOS_ROOT = _find_cmos_root()
if str(CMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(CMOS_ROOT))

from context.foundational_refs import FOUNDATIONAL_CHECKS, validate_file  # noqa: E402

# Kept under the historical name for callers and tests that load this script by path.
CHECKS = FOUNDATIONAL_CHECKS


def main() -> int:
    failures: list[str] = []
    for relative_path, config in CHECKS.items():
        failures.extend(validate_file(CMOS_ROOT / relative_path, config["required"], config["forbidden"]))

    if failures:
        print("Foundational reference validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Foundational reference validation succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
