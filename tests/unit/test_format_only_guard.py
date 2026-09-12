"""Guard real Git history against stale checkout deletions mislabeled formatting."""

import subprocess

import pytest

from scripts.check_format_only_changes import check_range

pytestmark = pytest.mark.unit


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.check_output(  # noqa: S603,S607 - isolated fixture repository
            ["git", *args],  # noqa: S607 - controlled Git executable
            text=True,
        ).strip()

    git("init", "-q")
    git("config", "user.email", "recovery@example.invalid")
    git("config", "user.name", "Recovery test")
    (tmp_path / "app").mkdir()
    path = tmp_path / "app" / "sample.py"
    path.write_text("def run():\n    check_access()\n    record_event()\n    return 42\n")
    git("add", ".")
    git("commit", "-qm", "Initial behavior")
    base = git("rev-parse", "HEAD")

    def commit(content, message):
        if content is None:
            path.unlink()
        else:
            path.write_text(content)
        git("add", "-A")
        git("commit", "-qm", message)
        return git("rev-parse", "HEAD")

    return base, commit


@pytest.mark.parametrize(
    "message",
    ["ruff formatting baseline", "Formatting-only cleanup", "style: run formatter", "chore(format): normalize"],
)
def test_format_claim_cannot_hide_removed_checks(history, message):
    base, commit = history
    head = commit("def run():\n    return 42\n", message)
    assert len(check_range(base, head)) == 1


def test_real_formatting_and_comments_are_allowed(history):
    base, commit = history
    head = commit("def run():\n    check_access(); record_event(); return 42\n", "Formatting only")
    assert check_range(base, head) == []


def test_explicit_behavior_change_is_not_a_format_claim(history):
    base, commit = history
    head = commit("def run():\n    return 42\n", "Remove obsolete event and access checks")
    assert check_range(base, head) == []


def test_deleted_file_and_intermediate_commit_are_checked(history):
    base, commit = history
    deleted = commit(None, "Formatting-only cleanup")
    head = commit("def run():\n    check_access()\n    record_event()\n    return 42\n", "Restore missing code")
    violations = check_range(base, head)
    assert len(violations) == 1
    assert deleted[:12] in violations[0]
