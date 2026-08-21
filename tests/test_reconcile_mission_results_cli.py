"""Operator contract for bounded DeepSearch result reconciliation."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.cli import reconcile_mission_results as cli


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_reconcile_cli_emits_counts_and_fails_loud(monkeypatch, capsys):
    """Schedulers get bounded JSON and a nonzero retry/dead-letter signal."""
    session = _Session()
    calls: list[int] = []

    class _Service:
        def reconcile_completed(self, db, *, limit):
            assert db is session
            calls.append(limit)
            return SimpleNamespace(
                scanned=12,
                eligible=3,
                repaired=2,
                failed=1,
                skipped_soft_deleted=6,
            )

    monkeypatch.setattr(cli, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli, "MissionResultMaterializationService", _Service)

    exit_code = cli.main(["--limit", "25"])

    assert exit_code == 1
    assert calls == [25]
    assert session.closed is True
    assert json.loads(capsys.readouterr().out) == {
        "eligible": 3,
        "failed": 1,
        "repaired": 2,
        "scanned": 12,
        "skipped_soft_deleted": 6,
    }


def test_reconcile_cli_tombstone_is_actionable_without_exposing_identifiers(
    monkeypatch,
    capsys,
):
    """Intentional deletion is a distinct owner action, not a retry failure."""
    session = _Session()
    mission = SimpleNamespace(
        mission_id="OPS-TOMBSTONE",
        status="completed",
    )

    class _Service:
        def materialize(self, db, selected_mission):
            assert db is session
            assert selected_mission is mission
            return SimpleNamespace(
                changed=False,
                document_blocked=True,
                errors=[],
            )

        def needs_materialization(self, db, selected_mission):
            assert db is session
            assert selected_mission is mission
            return False

    monkeypatch.setattr(cli, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli, "_mission_by_identifier", lambda db, value: mission)
    monkeypatch.setattr(cli, "MissionResultMaterializationService", _Service)

    exit_code = cli.main(["--mission-id", "OPS-TOMBSTONE"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 3
    assert session.closed is True
    assert payload == {
        "changed": False,
        "disposition": "blocked_soft_deleted",
        "errors": [],
        "mission_id": "OPS-TOMBSTONE",
        "owner_action": "restore_soft_deleted_result_document",
        "pending": False,
    }
    assert "document_id" not in payload


def test_reconcile_cli_genuine_error_takes_priority_over_tombstone_exit(
    monkeypatch,
    capsys,
):
    """A real repair error must still fail even if another artifact is deleted."""
    session = _Session()
    mission = SimpleNamespace(mission_id="OPS-PARTIAL", status="completed")

    class _Service:
        def materialize(self, db, selected_mission):
            return SimpleNamespace(
                changed=False,
                document_blocked=True,
                errors=["missing_project"],
            )

        def needs_materialization(self, db, selected_mission):
            return True

    monkeypatch.setattr(cli, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli, "_mission_by_identifier", lambda db, value: mission)
    monkeypatch.setattr(cli, "MissionResultMaterializationService", _Service)

    assert cli.main(["--mission-id", "OPS-PARTIAL"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == ["missing_project"]
