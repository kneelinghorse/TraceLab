"""Tests for T37.1 Client-Side PG Sync Dedup.

Covers:
- Content hash computation (SHA-256 of canonical JSON)
- Cross-language hash consistency (Python matches cmos-mcp TypeScript)
- Hash-based dedup in _sync_strategic_decisions()
- Migration script correctness
- Duplicate detection across decisions and learnings
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from cmos.context.db_client import SQLiteClient


# ─── Content Hash Tests ──────────────────────────────────────────────────────

class TestContentHash:
    """Content hash computation matches cmos-mcp computeContentHash()."""

    def test_compute_content_hash_consistent(self):
        """Same input produces same hash."""
        hash1 = SQLiteClient._compute_content_hash("Use PostgreSQL", "general")
        hash2 = SQLiteClient._compute_content_hash("Use PostgreSQL", "general")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_compute_content_hash_different_text(self):
        """Different text produces different hash."""
        hash1 = SQLiteClient._compute_content_hash("Use PostgreSQL", "general")
        hash2 = SQLiteClient._compute_content_hash("Use MongoDB", "general")
        assert hash1 != hash2

    def test_compute_content_hash_different_domain(self):
        """Different domain produces different hash."""
        hash1 = SQLiteClient._compute_content_hash("Use PostgreSQL", "general")
        hash2 = SQLiteClient._compute_content_hash("Use PostgreSQL", "tooling")
        assert hash1 != hash2

    def test_compute_content_hash_matches_typescript(self):
        """Hash matches cmos-mcp computeContentHash() implementation.

        TypeScript: JSON.stringify({d: domain, t: text})
        Python: json.dumps({"d": domain, "t": text}, sort_keys=True, separators=(",",":"))

        Both produce: {"d":"general","t":"Use PostgreSQL"}
        """
        text = "Use PostgreSQL"
        domain = "general"
        canonical = json.dumps(
            {"d": domain, "t": text},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        # The canonical form should be: {"d":"general","t":"Use PostgreSQL"}
        assert canonical == '{"d":"general","t":"Use PostgreSQL"}'

        expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        actual_hash = SQLiteClient._compute_content_hash(text, domain)
        assert actual_hash == expected_hash


# ─── Hash-Based Dedup Tests ──────────────────────────────────────────────────

class TestHashBasedDedup:
    """_sync_strategic_decisions() uses content hash for dedup."""

    @pytest.fixture
    def db_client(self, tmp_path: Path) -> SQLiteClient:
        """Create a temporary SQLite database with schema."""
        db_path = tmp_path / "test.sqlite"
        schema_path = Path(__file__).parent.parent / "cmos" / "db" / "schema.sql"
        client = SQLiteClient(db_path, schema_path=schema_path, create_missing=True)
        # Ensure connection is initialized
        _ = client.connection
        # Add content_hash column if not in schema
        try:
            client.execute(
                "ALTER TABLE strategic_decisions ADD COLUMN content_hash TEXT"
            )
        except Exception:
            pass  # Column may already exist from schema
        # Create contexts table entry for master_context
        client.execute(
            "INSERT OR REPLACE INTO contexts (id, source_path, content, updated_at) "
            "VALUES ('master_context', 'test', '{}', '2026-01-01T00:00:00Z')"
        )
        return client

    def test_dedup_by_hash_prevents_duplicates(self, db_client: SQLiteClient):
        """Identical decisions are not inserted twice."""
        master_context: Dict[str, Any] = {
            "decisions_made": [
                "Use PostgreSQL for ACID compliance",
                "Enable WAL mode for concurrent reads",
            ]
        }

        # First sync
        db_client._sync_strategic_decisions(master_context, None, "2026-01-01T00:00:00Z")

        count1 = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        assert count1 and count1["cnt"] == 2

        # Second sync with same decisions
        db_client._sync_strategic_decisions(master_context, None, "2026-01-02T00:00:00Z")

        count2 = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        assert count2 and count2["cnt"] == 2  # No duplicates

    def test_new_decisions_are_added(self, db_client: SQLiteClient):
        """New decisions get inserted alongside existing ones."""
        master_context1: Dict[str, Any] = {
            "decisions_made": ["Decision A"]
        }
        db_client._sync_strategic_decisions(master_context1, None, "2026-01-01T00:00:00Z")

        master_context2: Dict[str, Any] = {
            "decisions_made": ["Decision A", "Decision B"]
        }
        db_client._sync_strategic_decisions(master_context2, None, "2026-01-02T00:00:00Z")

        count = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        assert count and count["cnt"] == 2

    def test_content_hash_stored_on_insert(self, db_client: SQLiteClient):
        """content_hash is computed and stored for new decisions."""
        master_context: Dict[str, Any] = {
            "decisions_made": ["Use PostgreSQL"]
        }
        db_client._sync_strategic_decisions(master_context, None, "2026-01-01T00:00:00Z")

        row = db_client.fetchone(
            "SELECT content_hash FROM strategic_decisions WHERE decision_text = 'Use PostgreSQL'"
        )
        assert row is not None
        assert row["content_hash"] is not None
        assert len(row["content_hash"]) == 64

    def test_domain_decisions_dedup(self, db_client: SQLiteClient):
        """Domain-specific decisions use domain in hash for dedup."""
        master_context: Dict[str, Any] = {
            "decisions_made": ["Use PostgreSQL"],
            "working_memory": {
                "domains": {
                    "tracelab": {
                        "decisions_made": ["Use PostgreSQL"]
                    }
                }
            },
        }

        db_client._sync_strategic_decisions(master_context, None, "2026-01-01T00:00:00Z")

        count = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        # Same text but different domains → 2 distinct decisions
        assert count and count["cnt"] == 2

    def test_rich_decision_entries_dedup(self, db_client: SQLiteClient):
        """Rich dict decisions with evidence dedup correctly."""
        master_context: Dict[str, Any] = {
            "decisions_made": [
                {"text": "Use graph layer", "evidence": [{"type": "doc", "id": "123"}]},
                {"text": "Use graph layer", "evidence": [{"type": "doc", "id": "456"}]},
            ]
        }

        db_client._sync_strategic_decisions(master_context, None, "2026-01-01T00:00:00Z")

        count = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        # Same text + same domain → only 1 inserted (hash dedup)
        assert count and count["cnt"] == 1

    def test_backward_compat_text_dedup(self, db_client: SQLiteClient):
        """Old records without content_hash still dedup by text match."""
        # Insert a record without content_hash (simulating pre-migration data)
        db_client.execute(
            "INSERT INTO strategic_decisions (context_id, decision_text, created_at, project_domain) "
            "VALUES ('master_context', 'Legacy decision', '2025-01-01T00:00:00Z', 'general')"
        )

        master_context: Dict[str, Any] = {
            "decisions_made": ["Legacy decision"]
        }

        db_client._sync_strategic_decisions(master_context, None, "2026-01-01T00:00:00Z")

        count = db_client.fetchone(
            "SELECT COUNT(*) as cnt FROM strategic_decisions"
        )
        assert count and count["cnt"] == 1  # No duplicate


# ─── Migration Script Tests ──────────────────────────────────────────────────

class TestMigrationScript:
    """migrate_content_hash.py computes hashes for existing records."""

    def test_migration_computes_hashes(self, tmp_path: Path):
        """Migration adds content_hash column and computes hashes."""
        from cmos.scripts.migrate_content_hash import migrate, compute_content_hash

        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE strategic_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT DEFAULT 'master_context',
                decision_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                project_domain TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT,
                status TEXT DEFAULT 'active',
                sprint_id TEXT,
                session_id TEXT,
                mission_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO strategic_decisions (decision_text, created_at, project_domain) "
            "VALUES ('Use PostgreSQL', '2026-01-01T00:00:00Z', 'general')"
        )
        conn.execute(
            "INSERT INTO learnings (content, category, created_at) "
            "VALUES ('SQLite is fast', 'technical', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()

        stats = migrate(str(db_path))

        assert stats["decisions_hashed"] == 1
        assert stats["learnings_hashed"] == 1
        assert stats["duplicates_found"] == 0
        assert "strategic_decisions.content_hash" in stats["columns_added"]
        assert "learnings.content_hash" in stats["columns_added"]

        # Verify hashes are stored
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT content_hash FROM strategic_decisions WHERE id = 1"
        ).fetchone()
        assert row["content_hash"] is not None
        assert len(row["content_hash"]) == 64

        expected = compute_content_hash("Use PostgreSQL", "general")
        assert row["content_hash"] == expected
        conn.close()

    def test_migration_detects_duplicates(self, tmp_path: Path):
        """Migration reports duplicate records found by content hash."""
        from cmos.scripts.migrate_content_hash import migrate

        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE strategic_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT DEFAULT 'master_context',
                decision_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                project_domain TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT,
                status TEXT DEFAULT 'active',
                sprint_id TEXT,
                session_id TEXT,
                mission_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        # Insert duplicates
        conn.execute(
            "INSERT INTO strategic_decisions (decision_text, created_at, project_domain) "
            "VALUES ('Use PostgreSQL', '2026-01-01T00:00:00Z', 'general')"
        )
        conn.execute(
            "INSERT INTO strategic_decisions (decision_text, created_at, project_domain) "
            "VALUES ('Use PostgreSQL', '2026-01-02T00:00:00Z', 'general')"
        )
        conn.commit()
        conn.close()

        stats = migrate(str(db_path))

        assert stats["decisions_hashed"] == 2
        assert stats["duplicates_found"] == 1

    def test_migration_idempotent(self, tmp_path: Path):
        """Running migration twice doesn't re-hash or break."""
        from cmos.scripts.migrate_content_hash import migrate

        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE strategic_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT DEFAULT 'master_context',
                decision_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                project_domain TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT,
                status TEXT DEFAULT 'active',
                sprint_id TEXT,
                session_id TEXT,
                mission_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO strategic_decisions (decision_text, created_at, project_domain) "
            "VALUES ('Decision A', '2026-01-01T00:00:00Z', 'general')"
        )
        conn.commit()
        conn.close()

        stats1 = migrate(str(db_path))
        assert stats1["decisions_hashed"] == 1

        stats2 = migrate(str(db_path))
        assert stats2["decisions_hashed"] == 0  # Already hashed
        assert "strategic_decisions.content_hash" not in stats2["columns_added"]  # Column exists

    def test_hash_cross_language_consistency(self):
        """Python hash matches expected canonical JSON format for TypeScript compat."""
        from cmos.scripts.migrate_content_hash import compute_content_hash

        # The canonical form is JSON.stringify({d: domain, t: text}) in TS
        # which produces: {"d":"general","t":"Use PostgreSQL"}
        text = "Use PostgreSQL"
        domain = "general"
        canonical = '{"d":"general","t":"Use PostgreSQL"}'
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        actual = compute_content_hash(text, domain)
        assert actual == expected

        # Also verify the SQLiteClient static method
        actual2 = SQLiteClient._compute_content_hash(text, domain)
        assert actual2 == expected
