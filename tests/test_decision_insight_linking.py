"""Tests for T35.3 Decision–Insight Linking.

Covers:
- SessionCapture evidence field (storage and serialization)
- Evidence validation (type/id normalization, invalid entry rejection)
- Decision sync with evidence to strategic_decisions table
- Rich decision entries in master context (dict with evidence vs plain string)
- Retroactive evidence linking
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from cmos.context.session_runtime import SessionCapture, SessionRuntime

# -------------------------------------------------------------------------
# SessionCapture evidence tests
# -------------------------------------------------------------------------


class TestSessionCaptureEvidence:
    """SessionCapture dataclass supports evidence and mission_id fields."""

    def test_capture_without_evidence(self):
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="Use graph layer for retrieval",
        )
        d = cap.to_dict()
        assert "evidence" not in d
        assert "mission_id" not in d

    def test_capture_with_evidence(self):
        evidence = [{"type": "insight", "id": "abc-123"}]
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="Link decisions to insights",
            evidence=evidence,
            mission_id="T35.3",
        )
        d = cap.to_dict()
        assert d["evidence"] == evidence
        assert d["mission_id"] == "T35.3"

    def test_capture_with_multiple_evidence_refs(self):
        evidence = [
            {"type": "insight", "id": "abc-123"},
            {"type": "document", "id": "doc-456"},
            {"type": "chunk", "id": "chunk-789"},
        ]
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="Multi-source decision",
            evidence=evidence,
        )
        d = cap.to_dict()
        assert len(d["evidence"]) == 3
        assert d["evidence"][1]["type"] == "document"

    def test_capture_none_evidence_omitted(self):
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="No evidence",
            evidence=None,
        )
        d = cap.to_dict()
        assert "evidence" not in d

    def test_capture_empty_evidence_omitted(self):
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="Empty evidence",
            evidence=[],
        )
        d = cap.to_dict()
        assert "evidence" not in d

    def test_capture_serializes_to_json(self):
        evidence = [{"type": "insight", "id": "abc-123"}]
        cap = SessionCapture(
            timestamp="2026-03-12T12:00:00Z",
            category="decision",
            content="Test",
            evidence=evidence,
            mission_id="T35.3",
        )
        serialized = json.dumps(cap.to_dict())
        parsed = json.loads(serialized)
        assert parsed["evidence"][0]["type"] == "insight"
        assert parsed["mission_id"] == "T35.3"


# -------------------------------------------------------------------------
# Evidence validation tests
# -------------------------------------------------------------------------


class TestEvidenceValidation:
    """SessionRuntime._validate_evidence filters invalid entries."""

    def test_valid_evidence(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "insight", "id": "abc-123"},
            ]
        )
        assert result == [{"type": "insight", "id": "abc-123"}]

    def test_strips_whitespace(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "  insight  ", "id": "  abc-123  "},
            ]
        )
        assert result == [{"type": "insight", "id": "abc-123"}]

    def test_rejects_missing_type(self):
        result = SessionRuntime._validate_evidence(
            [
                {"id": "abc-123"},
            ]
        )
        assert result is None

    def test_rejects_missing_id(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "insight"},
            ]
        )
        assert result is None

    def test_rejects_empty_strings(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "", "id": "abc-123"},
            ]
        )
        assert result is None

    def test_rejects_non_dict_entries(self):
        result = SessionRuntime._validate_evidence(
            [
                "not a dict",
                42,
                None,
            ]
        )
        assert result is None

    def test_mixed_valid_and_invalid(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "insight", "id": "valid-1"},
                {"type": "", "id": "invalid"},
                "not-a-dict",
                {"type": "document", "id": "valid-2"},
            ]
        )
        assert len(result) == 2
        assert result[0]["id"] == "valid-1"
        assert result[1]["id"] == "valid-2"

    def test_all_invalid_returns_none(self):
        result = SessionRuntime._validate_evidence(
            [
                {"type": "", "id": ""},
                {"invalid": "keys"},
            ]
        )
        assert result is None


# -------------------------------------------------------------------------
# Master context decision enrichment tests
# -------------------------------------------------------------------------


class TestDecisionEnrichmentInMasterContext:
    """_apply_captures_to_master stores rich decision dicts when evidence is present."""

    @pytest.fixture()
    def runtime(self):
        rt = SessionRuntime.__new__(SessionRuntime)
        rt.CAPTURE_CATEGORIES = {
            "decision",
            "learning",
            "constraint",
            "context",
            "next-step",
        }
        return rt

    def test_plain_decision_stays_string(self, runtime):
        master = {}
        captures = [{"category": "decision", "content": "Use PEDR for search"}]
        runtime._apply_captures_to_master(master, captures, "PS-2026-03-12-001")
        decisions = master["decisions_made"]
        assert len(decisions) == 1
        assert isinstance(decisions[0], str)
        assert "Use PEDR for search" in decisions[0]

    def test_decision_with_evidence_becomes_dict(self, runtime):
        master = {}
        captures = [
            {
                "category": "decision",
                "content": "Link insights to decisions",
                "evidence": [{"type": "insight", "id": "ins-001"}],
                "mission_id": "T35.3",
            }
        ]
        runtime._apply_captures_to_master(master, captures, "PS-2026-03-12-001")
        decisions = master["decisions_made"]
        assert len(decisions) == 1
        assert isinstance(decisions[0], dict)
        assert decisions[0]["evidence"] == [{"type": "insight", "id": "ins-001"}]
        assert decisions[0]["mission_id"] == "T35.3"
        assert "Link insights" in decisions[0]["text"]

    def test_decision_with_mission_id_only_becomes_dict(self, runtime):
        master = {}
        captures = [
            {
                "category": "decision",
                "content": "Disable graph layer",
                "mission_id": "T35.1",
            }
        ]
        runtime._apply_captures_to_master(master, captures, "PS-2026-03-12-001")
        decisions = master["decisions_made"]
        assert isinstance(decisions[0], dict)
        assert decisions[0]["mission_id"] == "T35.1"
        assert "evidence" not in decisions[0]

    def test_mixed_plain_and_enriched_decisions(self, runtime):
        master = {}
        captures = [
            {"category": "decision", "content": "Plain decision"},
            {
                "category": "decision",
                "content": "Enriched",
                "evidence": [{"type": "doc", "id": "d1"}],
            },
        ]
        runtime._apply_captures_to_master(master, captures, "PS-2026-03-12-001")
        decisions = master["decisions_made"]
        assert len(decisions) == 2
        assert isinstance(decisions[0], str)
        assert isinstance(decisions[1], dict)


# -------------------------------------------------------------------------
# Strategic decisions sync tests (db_client)
# -------------------------------------------------------------------------


class TestStrategicDecisionsSyncWithEvidence:
    """_sync_strategic_decisions handles both string and dict decision entries."""

    @pytest.fixture()
    def cmos_db(self, tmp_path):
        db_path = tmp_path / "test_cmos.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE contexts (
                id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE context_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT NOT NULL,
                session_id TEXT,
                source TEXT,
                content_hash TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE strategic_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT NOT NULL DEFAULT 'master_context',
                decision_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sprint_id TEXT,
                snapshot_id INTEGER,
                project_domain TEXT,
                mission_id TEXT,
                category TEXT,
                superseded_by INTEGER,
                status TEXT DEFAULT 'active',
                evidence TEXT,
                content_hash TEXT
            )
        """)
        conn.commit()
        conn.close()
        return db_path

    @pytest.fixture()
    def db_client(self, cmos_db):
        from cmos.context.db_client import SQLiteClient

        client = SQLiteClient(cmos_db, create_missing=False)
        yield client
        client.close()

    def test_sync_plain_string_decision(self, db_client):
        master = {"decisions_made": ["Use PEDR for all searches"]}
        db_client._sync_strategic_decisions(
            master, snapshot_id=1, timestamp="2026-03-12T12:00:00Z"
        )

        rows = db_client.fetchall("SELECT * FROM strategic_decisions")
        assert len(rows) == 1
        assert rows[0]["decision_text"] == "Use PEDR for all searches"
        assert rows[0]["evidence"] is None
        assert rows[0]["mission_id"] is None

    def test_sync_rich_decision_with_evidence(self, db_client):
        master = {
            "decisions_made": [
                {
                    "text": "Link insights to decisions (from PS-2026-03-12-001)",
                    "evidence": [{"type": "insight", "id": "ins-001"}],
                    "mission_id": "T35.3",
                }
            ]
        }
        db_client._sync_strategic_decisions(
            master, snapshot_id=2, timestamp="2026-03-12T12:00:00Z"
        )

        rows = db_client.fetchall("SELECT * FROM strategic_decisions")
        assert len(rows) == 1
        assert "Link insights" in rows[0]["decision_text"]
        assert rows[0]["mission_id"] == "T35.3"
        evidence = json.loads(rows[0]["evidence"])
        assert len(evidence) == 1
        assert evidence[0]["type"] == "insight"

    def test_sync_mixed_decisions(self, db_client):
        master = {
            "decisions_made": [
                "Plain decision text",
                {
                    "text": "Rich decision",
                    "evidence": [{"type": "doc", "id": "d1"}],
                    "mission_id": "T35.3",
                },
            ]
        }
        db_client._sync_strategic_decisions(
            master, snapshot_id=3, timestamp="2026-03-12T12:00:00Z"
        )

        rows = db_client.fetchall("SELECT * FROM strategic_decisions ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["evidence"] is None
        assert rows[1]["evidence"] is not None

    def test_sync_dedup_prevents_double_insert(self, db_client):
        master = {"decisions_made": ["Same decision"]}
        db_client._sync_strategic_decisions(
            master, snapshot_id=1, timestamp="2026-03-12T12:00:00Z"
        )
        db_client._sync_strategic_decisions(
            master, snapshot_id=2, timestamp="2026-03-12T13:00:00Z"
        )

        rows = db_client.fetchall("SELECT * FROM strategic_decisions")
        assert len(rows) == 1

    def test_parse_decision_entry_string(self):
        from cmos.context.db_client import SQLiteClient

        result = SQLiteClient._parse_decision_entry("Simple decision")
        assert result["decision_text"] == "Simple decision"
        assert result["evidence"] is None

    def test_parse_decision_entry_dict(self):
        from cmos.context.db_client import SQLiteClient

        result = SQLiteClient._parse_decision_entry(
            {
                "text": "Rich decision",
                "evidence": [{"type": "insight", "id": "i1"}],
                "mission_id": "T35.3",
            }
        )
        assert result["decision_text"] == "Rich decision"
        assert result["mission_id"] == "T35.3"
        evidence = json.loads(result["evidence"])
        assert evidence[0]["type"] == "insight"

    def test_parse_decision_entry_empty_text(self):
        from cmos.context.db_client import SQLiteClient

        result = SQLiteClient._parse_decision_entry({"text": ""})
        assert result is None

    def test_parse_decision_entry_non_string_non_dict(self):
        from cmos.context.db_client import SQLiteClient

        result = SQLiteClient._parse_decision_entry(42)
        assert result is None


# -------------------------------------------------------------------------
# Retroactive linking test (proof of concept)
# -------------------------------------------------------------------------


class TestRetroactiveLinking:
    """Demonstrate retroactive evidence linking on an existing decision."""

    @pytest.fixture()
    def cmos_db(self, tmp_path):
        db_path = tmp_path / "retro_cmos.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE strategic_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id TEXT NOT NULL DEFAULT 'master_context',
                decision_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sprint_id TEXT,
                snapshot_id INTEGER,
                project_domain TEXT,
                mission_id TEXT,
                category TEXT,
                superseded_by INTEGER,
                status TEXT DEFAULT 'active',
                evidence TEXT
            )
        """)
        conn.execute(
            "INSERT INTO strategic_decisions (decision_text, created_at, project_domain) "
            "VALUES ('Keep graph disabled until edge population pipeline is built', "
            "'2026-03-12T12:00:00Z', 'general')"
        )
        conn.commit()
        conn.close()
        return db_path

    def test_retroactive_evidence_add(self, cmos_db):
        """An existing decision without evidence gets evidence added."""
        conn = sqlite3.connect(str(cmos_db))
        conn.row_factory = sqlite3.Row

        row = dict(
            conn.execute("SELECT * FROM strategic_decisions WHERE id = 1").fetchone()
        )
        assert row["evidence"] is None

        evidence = [
            {"type": "search_result", "id": "graph-quality-report-2026-03-12"},
            {
                "type": "document",
                "id": "cmos/telemetry/events/graph-quality-report.json",
            },
        ]
        conn.execute(
            "UPDATE strategic_decisions SET evidence = ?, mission_id = ? WHERE id = ?",
            (json.dumps(evidence), "T35.1", 1),
        )
        conn.commit()

        updated = dict(
            conn.execute("SELECT * FROM strategic_decisions WHERE id = 1").fetchone()
        )
        assert updated["mission_id"] == "T35.1"
        parsed = json.loads(updated["evidence"])
        assert len(parsed) == 2
        assert parsed[0]["type"] == "search_result"
        conn.close()
