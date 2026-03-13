#!/usr/bin/env python3
"""Migrate content_hash columns for strategic_decisions and learnings tables.

Adds content_hash column (if missing) and computes SHA-256 hashes for all
existing records. This enables client-side dedup before pushing to PG mirror.

Hash function matches cmos-mcp's computeContentHash():
  SHA-256(JSON.stringify({"d": domain, "t": text}))

Usage:
  python cmos/scripts/migrate_content_hash.py [--db-path cmos/db/cmos.sqlite] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def compute_content_hash(text: str, domain: str) -> str:
    """Compute SHA-256 content hash matching cmos-mcp computeContentHash()."""
    canonical = json.dumps({"d": domain, "t": text}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    return column in columns


def migrate(db_path: str, dry_run: bool = False) -> dict:
    """Run the content_hash migration. Returns stats."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    stats = {"columns_added": [], "decisions_hashed": 0, "learnings_hashed": 0, "duplicates_found": 0}

    try:
        # 1. Add content_hash column to strategic_decisions if missing
        if not has_column(conn, "strategic_decisions", "content_hash"):
            if not dry_run:
                conn.execute("ALTER TABLE strategic_decisions ADD COLUMN content_hash TEXT")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_strategic_decisions_hash "
                    "ON strategic_decisions (content_hash)"
                )
            stats["columns_added"].append("strategic_decisions.content_hash")
            print(f"{'[DRY RUN] Would add' if dry_run else 'Added'} content_hash to strategic_decisions")
        else:
            print("strategic_decisions.content_hash already exists")

        # 2. Add content_hash column to learnings if missing
        if not has_column(conn, "learnings", "content_hash"):
            if not dry_run:
                conn.execute("ALTER TABLE learnings ADD COLUMN content_hash TEXT")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_learnings_hash ON learnings (content_hash)"
                )
            stats["columns_added"].append("learnings.content_hash")
            print(f"{'[DRY RUN] Would add' if dry_run else 'Added'} content_hash to learnings")
        else:
            print("learnings.content_hash already exists")

        # 3. Compute hashes for decisions without content_hash
        has_hash_col = has_column(conn, "strategic_decisions", "content_hash")
        if has_hash_col:
            cursor = conn.execute(
                "SELECT id, decision_text, project_domain FROM strategic_decisions WHERE content_hash IS NULL"
            )
        else:
            cursor = conn.execute(
                "SELECT id, decision_text, project_domain FROM strategic_decisions"
            )
        decisions = cursor.fetchall()
        seen_hashes: set[str] = set()

        # First collect existing hashes (only if column exists)
        if has_hash_col:
            existing = conn.execute(
                "SELECT content_hash FROM strategic_decisions WHERE content_hash IS NOT NULL"
            ).fetchall()
            for row in existing:
                seen_hashes.add(row["content_hash"])

        for row in decisions:
            domain = row["project_domain"] or "general"
            content_hash = compute_content_hash(row["decision_text"], domain)

            if content_hash in seen_hashes:
                stats["duplicates_found"] += 1
                print(f"  Duplicate decision id={row['id']}: hash {content_hash[:12]}... already exists")

            seen_hashes.add(content_hash)

            if not dry_run:
                conn.execute(
                    "UPDATE strategic_decisions SET content_hash = ? WHERE id = ?",
                    (content_hash, row["id"]),
                )
            stats["decisions_hashed"] += 1

        print(f"{'[DRY RUN] Would hash' if dry_run else 'Hashed'} {stats['decisions_hashed']} decisions")

        # 4. Compute hashes for learnings without content_hash
        has_learning_hash_col = has_column(conn, "learnings", "content_hash")
        if has_learning_hash_col:
            cursor = conn.execute(
                "SELECT id, content, category FROM learnings WHERE content_hash IS NULL"
            )
        else:
            cursor = conn.execute(
                "SELECT id, content, category FROM learnings"
            )
        learnings = cursor.fetchall()
        seen_learning_hashes: set[str] = set()

        if has_learning_hash_col:
            existing_learnings = conn.execute(
                "SELECT content_hash FROM learnings WHERE content_hash IS NOT NULL"
            ).fetchall()
            for row in existing_learnings:
                seen_learning_hashes.add(row["content_hash"])

        for row in learnings:
            category = row["category"] or ""
            content_hash = compute_content_hash(row["content"], category)

            if content_hash in seen_learning_hashes:
                stats["duplicates_found"] += 1
                print(f"  Duplicate learning id={row['id']}: hash {content_hash[:12]}... already exists")

            seen_learning_hashes.add(content_hash)

            if not dry_run:
                conn.execute(
                    "UPDATE learnings SET content_hash = ? WHERE id = ?",
                    (content_hash, row["id"]),
                )
            stats["learnings_hashed"] += 1

        print(f"{'[DRY RUN] Would hash' if dry_run else 'Hashed'} {stats['learnings_hashed']} learnings")

        if not dry_run:
            conn.commit()

        if stats["duplicates_found"] > 0:
            print(f"\nWarning: {stats['duplicates_found']} duplicate(s) detected by content hash")

        print(f"\nMigration {'preview' if dry_run else 'complete'}: "
              f"{stats['decisions_hashed']} decisions, "
              f"{stats['learnings_hashed']} learnings, "
              f"{stats['duplicates_found']} duplicates found")

    finally:
        conn.close()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate content_hash columns for dedup")
    parser.add_argument(
        "--db-path",
        default="cmos/db/cmos.sqlite",
        help="Path to CMOS SQLite database (default: cmos/db/cmos.sqlite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return 1

    migrate(str(db_path), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
