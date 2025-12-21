#!/usr/bin/env python3
"""CLI for materializing graph edges.

Usage:
    python -m app.cli.materialize_edges [--full|--incremental]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.pedr.edge_materialization import EdgeMaterializationService


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Materialize graph edges from implicit relationships",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Materialize all implicit edges (default)",
    )
    mode_group.add_argument(
        "--incremental",
        action="store_true",
        help="Materialize edges for recently updated entities",
    )
    parser.add_argument(
        "--project",
        help="Optional project UUID to scope materialization",
    )

    args = parser.parse_args()

    mode = "incremental" if args.incremental else "full"

    print(f"Materializing implicit edges (mode={mode})")
    if args.project:
        print(f"Project filter: {args.project}")

    service = EdgeMaterializationService()
    result = service.materialize_implicit_edges(
        mode=mode,
        project_id=args.project,
    )

    print("-" * 50)
    print(f"Inserted: {result.inserted_count}")
    print(f"Updated: {result.updated_count}")
    print(f"Skipped: {result.skipped_count}")
    print(f"Total: {result.total}")

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
