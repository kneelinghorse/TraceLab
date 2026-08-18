"""Unit tests for the tracked credential-literal guard.

The guard exists because entropy-based scanners missed a real password recorded
in a tracked mission file. These tests pin detection by assignment semantics,
including low-entropy values, while keeping diagnostics value-safe.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.check_no_credential_literals import find_credential_literals, main

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("path", "line"),
    [
        (Path("mission.md"), "- AUTH_PASSWORD=summer"),
        (Path("config.yaml"), "OPENAI_API_KEY: sk-prodlive-1234567890"),
        (Path("settings.json"), '"SECRET_KEY": "literal with spaces"'),
        (Path("service.env"), "AUTH_PASSWORD_HASH=$2b$12$not-a-real-hash"),
        (Path("compose.yaml"), "AUTH_PASSWORD=${AUTH_PASSWORD:-winter}"),
    ],
)
def test_rejects_credential_literals_regardless_of_entropy(path: Path, line: str) -> None:
    findings = find_credential_literals(line, path)

    assert len(findings) == 1
    assert findings[0].line_number == 1


@pytest.mark.parametrize(
    "line",
    [
        "AUTH_PASSWORD=",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=$AUTH_PASSWORD",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=${AUTH_PASSWORD}",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=${AUTH_PASSWORD:-changeme}",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=${{ secrets.AUTH_PASSWORD }}",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=<set-in-secret-manager>",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=[REDACTED -- credential rotated]",  # secret-scan: allow -- parser fixture
        "AUTH_PASSWORD=change-me",  # secret-scan: allow -- parser fixture
        "OPENAI_API_KEY=sk-your_openai_api_key_here",  # secret-scan: allow -- parser fixture
        'QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")',  # secret-scan: allow -- parser fixture
    ],
)
def test_accepts_runtime_references_and_obvious_placeholders(line: str) -> None:
    assert find_credential_literals(line, Path("instructions.md")) == []


def test_fixture_exemption_requires_a_reason() -> None:
    without_reason = "AUTH_PASSWORD=summer # secret-scan: allow"
    with_reason = "AUTH_PASSWORD=summer # secret-scan: allow -- synthetic CLI fixture"

    assert len(find_credential_literals(without_reason, Path("fixture.env"))) == 1
    assert find_credential_literals(with_reason, Path("fixture.env")) == []


def test_ignores_non_credentials_and_python_type_documentation() -> None:
    text = "\n".join(
        [
            "ACCESS_TOKEN_EXPIRE_MINUTES=15",
            "MAX_TOKENS=100",
            "TRACELAB_TOKEN: Bearer access token for authentication",
            'current_password = "form state, not a credential"',
        ]
    )

    assert find_credential_literals(text, Path("example.py")) == []


def test_cli_diagnostic_never_prints_the_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_value = "value-that-must-not-appear"
    candidate = tmp_path / "candidate.env"
    candidate.write_text(f"AUTH_PASSWORD={fake_value}\n")

    assert main([str(candidate)]) == 1

    stderr = capsys.readouterr().err
    assert "AUTH_PASSWORD" in stderr
    assert str(candidate) in stderr
    assert fake_value not in stderr


def test_tracked_mode_ignores_untracked_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True)  # noqa: S603
    tracked = tmp_path / "tracked.env"
    tracked.write_text("AUTH_PASSWORD=$AUTH_PASSWORD\n")
    subprocess.run(  # noqa: S603
        [git, "-C", str(tmp_path), "add", tracked.name],
        check=True,
    )
    (tmp_path / "untracked.env").write_text("AUTH_PASSWORD=untracked-literal\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--tracked"]) == 0

    tracked.write_text("AUTH_PASSWORD=now-a-tracked-literal\n")
    assert main(["--tracked"]) == 1
