"""Regression tests for automated session context updates."""

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


class SessionRuntimeContextUpdatesTest(unittest.TestCase):
    """Ensure session completion writes aggregated context data."""

    def setUp(self) -> None:
        self.repo_root = CMOS_ROOT
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cmos.sqlite"
        shutil.copy2(self.repo_root / "db" / "cmos.sqlite", self.db_path)
        self.runtime = SessionRuntime(repo_root=self.repo_root, db_path=self.db_path)
        self.runtime.ensure_database()
        self._reset_context_state()

    def tearDown(self) -> None:  # pragma: no cover - cleanup
        self.runtime.close()
        self.temp_dir.cleanup()

    def _reset_context_state(self) -> None:
        client = self.runtime.client
        client.execute("DELETE FROM sessions")
        client.execute("DELETE FROM session_events")
        client.execute(
            "DELETE FROM context_snapshots WHERE context_id IN ('project_context', 'master_context')"
        )
        client.execute(
            "DELETE FROM strategic_decisions WHERE context_id = 'master_context'"
        )
        project_context = {"working_memory": {}}
        master_context = {
            "project_identity": {},
            "decisions_made": [],
            "learnings": [],
            "constraints": [],
            "next_session_context": {},
        }
        client.set_context(
            "project_context",
            project_context,
            source_path="tests/reset",
            snapshot=False,
        )
        client.set_context(
            "master_context",
            master_context,
            source_path="tests/reset",
            snapshot=False,
        )
        client.connection.commit()
        client.close()

    def test_session_completion_appends_master_context_fields(self) -> None:
        session_id = self.runtime.start_session(
            "planning",
            "Automated context validation",
            agent="unittest",
        )
        self.runtime.capture_insight(
            session_id, "decision", "Adopt automated context syncing"
        )
        self.runtime.capture_insight(
            session_id, "learning", "Session flow needs better prompts"
        )
        self.runtime.capture_insight(
            session_id, "constraint", "Deploy updates in under 5 minutes"
        )
        self.runtime.capture_insight(
            session_id, "constraint", "Deploy updates in under 5 minutes"
        )
        self.runtime.capture_insight(
            session_id, "context", "Scoped expected master context structure"
        )
        self.runtime.capture_insight(session_id, "next-step", "Draft CLI delta summary")

        self.runtime.complete_session(
            session_id,
            "Captured required updates",
            next_steps=["Draft CLI delta summary"],
            agent="unittest",
        )

        master = self.runtime.client.get_context("master_context") or {}
        decisions = master.get("decisions_made") or []
        learnings = master.get("learnings") or []
        constraints = master.get("constraints") or []
        recent_sessions = master.get("recent_sessions") or []
        next_resume = master.get("next_session_context", {}).get("when_we_resume") or []

        self.assertTrue(decisions, "Decisions array not updated")
        self.assertIn(session_id, decisions[-1])
        self.assertTrue(learnings, "Learnings array not updated")
        self.assertIn(session_id, learnings[-1])
        self.assertEqual(
            len(constraints), 1, "Constraints should dedupe identical entries"
        )
        self.assertEqual(constraints[0], "Deploy updates in under 5 minutes")
        self.assertTrue(recent_sessions, "Recent sessions missing")
        latest = recent_sessions[-1]
        self.assertEqual(latest["id"], session_id)
        self.assertEqual(latest.get("capture_count"), 6)
        captures = latest.get("captures") or {}
        self.assertEqual(captures.get("constraint"), 2)
        self.assertEqual(captures.get("decision"), 1)
        self.assertIn(session_id, next_resume[-1])

        stored_decision = decisions[-1]
        db_row = self.runtime.client.fetchone(
            "SELECT decision_text FROM strategic_decisions WHERE decision_text = :text",
            {"text": stored_decision},
        )
        self.assertIsNotNone(db_row, "Strategic decisions table missing new entry")

        snapshot = self.runtime.client.fetchone(
            """
            SELECT source, session_id
              FROM context_snapshots
             WHERE context_id = 'master_context'
          ORDER BY id DESC
             LIMIT 1
            """
        )
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.get("session_id"), session_id)
        self.assertEqual(snapshot.get("source"), f"session_complete:{session_id}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
