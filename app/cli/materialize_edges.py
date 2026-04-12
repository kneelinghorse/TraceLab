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
    parser.add_argument(
        "--skip-topic-similar",
        action="store_true",
        help="Skip topic_similar edge materialization (Qdrant-dependent, expensive)",
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
    print(f"Implicit edges — Inserted: {result.inserted_count}, Updated: {result.updated_count}, Skipped: {result.skipped_count}")

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    # For full runs, also materialize topic_similar edges (requires Qdrant)
    if mode == "full" and not args.skip_topic_similar:
        print("\nMaterializing topic_similar edges (Qdrant embedding similarity)...")
        try:
            ts_result = service.materialize_topic_similarity_edges(
                project_id=args.project,
            )
            print(f"topic_similar — Inserted: {ts_result.inserted_count}, Updated: {ts_result.updated_count}, Skipped: {ts_result.skipped_count}")
            if ts_result.errors:
                print("topic_similar errors:")
                for error in ts_result.errors:
                    print(f"  - {error}")
        except Exception as exc:
            print(f"topic_similar materialization failed (non-fatal): {exc}")

    total = result.total + (ts_result.total if mode == "full" and not args.skip_topic_similar else 0)
    print(f"\nTotal edges processed: {total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
