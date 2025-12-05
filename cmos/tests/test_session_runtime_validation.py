"""Validation and error handling tests for SessionRuntime."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CMOS_ROOT = Path(__file__).resolve().parents[1]
if str(CMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(CMOS_ROOT))

from context.session_runtime import (  # noqa: E402
    ActiveSessionError,
    SessionRuntime,
    ValidationError,
)


class SessionRuntimeValidationTest(unittest.TestCase):
    """Ensure validation errors surface with actionable messaging."""

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
        client.execute("DELETE FROM context_snapshots WHERE context_id IN ('project_context', 'master_context')")
        client.execute("DELETE FROM strategic_decisions WHERE context_id = 'master_context'")
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

    def test_start_session_validates_type(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.start_session("brainstorm", "Invalid type", agent="unittest")
        self.assertIn("session type", str(ctx.exception))

    def test_duplicate_active_session_error_mentions_resolution(self) -> None:
        session_id = self.runtime.start_session("planning", "First", agent="unittest")
        with self.assertRaises(ActiveSessionError) as ctx:
            self.runtime.start_session("planning", "Second", agent="unittest")
        message = str(ctx.exception)
        self.assertIn(session_id, message)
        self.assertIn("session complete", message)

    def test_stale_active_session_detected(self) -> None:
        session_id = self.runtime.start_session("planning", "Aging", agent="unittest")
        client = self.runtime.client
        project_context = client.get_context("project_context") or {}
        working = project_context.setdefault("working_memory", {})
        active = working.get("active_session") or {}
        active["started_at"] = "2023-01-01T00:00:00Z"
        working["active_session"] = active
        client.set_context("project_context", project_context, source_path="tests/reset", snapshot=False)
        client.close()

        with self.assertRaises(ActiveSessionError) as ctx:
            self.runtime.start_session("planning", "New", agent="unittest")
        self.assertIn("idle", str(ctx.exception))
        self.assertIn(session_id, str(ctx.exception))

    def test_capture_validates_category_and_length(self) -> None:
        session_id = self.runtime.start_session("planning", "Validation", agent="unittest")
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.capture_insight(session_id, "idea", "Should fail")
        self.assertIn("Valid options", str(ctx.exception))

        overlong = "x" * 1001
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.capture_insight(session_id, "context", overlong)
        self.assertIn("1000", str(ctx.exception))

    def test_complete_requires_summary(self) -> None:
        session_id = self.runtime.start_session("planning", "Needs summary", agent="unittest")
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.complete_session(session_id, "   ")
        self.assertIn("summary", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
