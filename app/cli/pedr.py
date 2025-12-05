#!/usr/bin/env python3
"""CLI commands for PEDR delta sync operations.

Usage:
    python -m app.cli.pedr sync [--full|--delta] [--dry-run]
    python -m app.cli.pedr status
    python -m app.cli.pedr parity [--entity-type mission|document]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.pedr import (
    EntityType,
    SyncMode,
    get_delta_sync_service,
)


def cmd_sync(args: argparse.Namespace) -> int:
    """Execute sync to PEDR."""
    mode = SyncMode.FULL if args.full else SyncMode.DELTA
    dry_run = args.dry_run

    print(f"Starting PEDR sync (mode={mode.value}, dry_run={dry_run})")
    print("-" * 50)

    service = get_delta_sync_service(
        telemetry_path=Path("cmos/telemetry/events/sprint-11-pedr-sync.jsonl"),
    )

    # Sync based on entity type filter
    entity_types = []
    if args.entity_type:
        entity_types = [args.entity_type]
    else:
        entity_types = ["mission", "document"]

    exit_code = 0

    for entity_type in entity_types:
        print(f"\nSyncing {entity_type}s...")

        if entity_type == "mission":
            result = service.sync_missions(mode, project_id=args.project, dry_run=dry_run)
        elif entity_type == "document":
            result = service.sync_documents(mode, project_id=args.project, dry_run=dry_run)
        else:
            print(f"  Unknown entity type: {entity_type}")
            continue

        print(f"  Synced: {result.synced_count}")
        print(f"  Failed: {result.failed_count}")
        print(f"  Skipped: {result.skipped_count}")
        print(f"  Duration: {result.duration_ms:.2f}ms")

        if result.last_sync_at:
            print(f"  Last sync: {result.last_sync_at.isoformat()}")

        if result.errors:
            print("  Errors:")
            for error in result.errors[:5]:  # Show first 5 errors
                print(f"    - {error}")
            if len(result.errors) > 5:
                print(f"    ... and {len(result.errors) - 5} more")

        if not result.success:
            exit_code = 1

    print("\n" + "-" * 50)
    print("Sync complete" + (" (dry run)" if dry_run else ""))

    return exit_code


def cmd_status(args: argparse.Namespace) -> int:
    """Show sync status."""
    service = get_delta_sync_service()

    print("PEDR Sync Status")
    print("-" * 50)

    status = service.get_sync_status()

    for entity_type, info in status.items():
        print(f"\n{entity_type}:")
        print(f"  Last sync: {info.get('last_sync_at') or 'Never'}")
        print(f"  Total synced: {info.get('sync_count', 0)}")
        print(f"  Updated: {info.get('updated_at') or 'N/A'}")

        # Show pending count
        try:
            pending = service.get_pending_count(EntityType(entity_type))
            print(f"  Pending: {pending}")
        except ValueError:
            pass

    return 0


def cmd_parity(args: argparse.Namespace) -> int:
    """Check parity between local and PEDR."""
    service = get_delta_sync_service()

    entity_types = [EntityType(args.entity_type)] if args.entity_type else list(EntityType)

    print("PEDR Parity Check")
    print("-" * 50)

    all_in_sync = True

    for entity_type in entity_types:
        if entity_type == EntityType.INSIGHT:
            continue  # Skip insights for now

        result = service.check_parity(entity_type)

        print(f"\n{entity_type.value}:")
        print(f"  Local count: {result.local_count}")
        print(f"  Remote count: {result.remote_count}")
        print(f"  Discrepancy: {result.discrepancy}")
        print(f"  In sync: {'Yes' if result.in_sync else 'No'}")

        if not result.in_sync:
            all_in_sync = False

    print("\n" + "-" * 50)
    if all_in_sync:
        print("All entity types in sync")
    else:
        print("Discrepancies detected - consider running full sync")

    return 0 if all_in_sync else 1


def cmd_pending(args: argparse.Namespace) -> int:
    """Show pending entities for sync."""
    service = get_delta_sync_service()

    print("Pending PEDR Sync")
    print("-" * 50)

    for entity_type in EntityType:
        if entity_type == EntityType.INSIGHT:
            continue

        pending = service.get_pending_count(entity_type)
        print(f"{entity_type.value}: {pending} pending")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PEDR Delta Sync CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync entities to PEDR")
    sync_parser.add_argument(
        "--full",
        action="store_true",
        help="Full sync (all entities)",
    )
    sync_parser.add_argument(
        "--delta",
        action="store_true",
        default=True,
        help="Delta sync (only changed entities, default)",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Transform but don't ingest",
    )
    sync_parser.add_argument(
        "--entity-type",
        choices=["mission", "document"],
        help="Sync only specific entity type",
    )
    sync_parser.add_argument(
        "--project",
        help="Filter by project ID",
    )

    # status command
    subparsers.add_parser("status", help="Show sync status")

    # parity command
    parity_parser = subparsers.add_parser("parity", help="Check parity with PEDR")
    parity_parser.add_argument(
        "--entity-type",
        choices=["mission", "document"],
        help="Check specific entity type",
    )

    # pending command
    subparsers.add_parser("pending", help="Show pending entities")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "sync": cmd_sync,
        "status": cmd_status,
        "parity": cmd_parity,
        "pending": cmd_pending,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
