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
            return SimpleNamespace(scanned=12, eligible=3, repaired=2, failed=1)

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
    }
