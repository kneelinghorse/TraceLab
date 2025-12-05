"""Tests for context view aggregation helpers."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CMOS_ROOT = Path(__file__).resolve().parents[1]
if str(CMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(CMOS_ROOT))

from context.session_runtime import SessionRuntime
from context.view_helpers import (
    ContextViewError,
    export_context,
    get_context_at_point,
    get_domain_view,
    get_master_context_view,
)
from context.db_client import SQLiteClient


class ContextViewHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = CMOS_ROOT
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cmos.sqlite"
        shutil.copy2(self.repo_root / "db" / "cmos.sqlite", self.db_path)
        self.runtime = SessionRuntime(repo_root=self.repo_root, db_path=self.db_path)
        self.runtime.ensure_database()
        self.client = SQLiteClient(self.db_path, schema_path=self.repo_root / "db" / "schema.sql")
        self._reset_context_state()
        self.session_alpha = self._seed_session(
            domain="alpha",
            decisions=["Adopt alpha strategy"],
            learnings=["Alpha interviews revealed scope"],
            constraints=["Alpha must stay lean"],
            next_steps=["Alpha follow-up"],
        )
        self.session_beta = self._seed_session(
            domain="beta",
            decisions=["Use beta rollout"],
            learnings=["Beta experiment succeeded"],
            constraints=["Beta budget limited"],
        )

    def tearDown(self) -> None:  # pragma: no cover - cleanup
        self.runtime.close()
        self.client.close()
        self.temp_dir.cleanup()

    def _reset_context_state(self) -> None:
        conn = self.client.connection
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM session_events")
        conn.execute("DELETE FROM context_snapshots")
        conn.execute("DELETE FROM strategic_decisions")
        project_context = {"working_memory": {}}
        master_context = {"project_identity": {"name": "CMOS"}}
        self.client.set_context("project_context", project_context, source_path="tests/reset", snapshot=False)
        self.client.set_context("master_context", master_context, source_path="tests/reset", snapshot=False)

    def _seed_session(
        self,
        *,
        domain: str,
        decisions: list[str],
        learnings: list[str],
        constraints: list[str],
        next_steps: list[str] | None = None,
    ) -> str:
        session_id = self.runtime.start_session(
            "planning",
            f"Session-{domain}",
            agent="unittest",
            metadata={"domain": domain},
        )
        for text in decisions:
            self.runtime.capture_insight(session_id, "decision", text)
        for text in learnings:
            self.runtime.capture_insight(session_id, "learning", text)
        for text in constraints:
            self.runtime.capture_insight(session_id, "constraint", text)
        if next_steps:
            for text in next_steps:
                self.runtime.capture_insight(session_id, "next-step", text)
        self.runtime.complete_session(
            session_id,
            f"Wrapped {domain}",
            next_steps=next_steps,
            agent="unittest",
        )
        return session_id

    # ------------------------------------------------------------------ tests

    def test_master_context_view_reports_aggregates(self) -> None:
        view = get_master_context_view(self.client, recent_limit=5)
        self.assertEqual(view["project_identity"]["session_count"], 2)
        self.assertEqual(view["aggregated_insights"]["total_decisions"], 2)
        self.assertEqual(len(view["recent_sessions"]), 2)
        self.assertTrue(any("alpha" in entry.lower() for entry in view["decisions_made"]))
        self.assertTrue(view["pending_next_steps"], "Next steps should be present")

    def test_domain_view_filters_sessions(self) -> None:
        view = get_domain_view(self.client, "alpha", recent_limit=5)
        self.assertEqual(view["project_identity"]["session_count"], 1)
        self.assertEqual(len(view["recent_sessions"]), 1)
        self.assertTrue(all("alpha" in sess.get("id", "").lower() or sess.get("domain") == "alpha" for sess in view["recent_sessions"]))

    def test_context_at_point_limits_history(self) -> None:
        view = get_context_at_point(self.client, as_of=self.session_alpha, recent_limit=5)
        self.assertEqual(view["project_identity"]["session_count"], 1)
        self.assertEqual(view["aggregated_insights"]["total_decisions"], 1)

    def test_export_context_markdown(self) -> None:
        view = get_master_context_view(self.client, recent_limit=2)
        output = export_context(view, "markdown")
        self.assertIn("Context View", output)
        self.assertIn("Recent Sessions", output)

    def test_missing_as_of_raises(self) -> None:
        with self.assertRaises(ContextViewError):
            get_context_at_point(self.client, as_of="", recent_limit=2)
