"""A stuck test must fail with evidence and cleanup before the runner kills CI."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "scripts/run_pytest.py"
pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("behavior", "expected"), [("success", 0), ("failure", 1), ("hang", 124), ("ignore", 124)]
)
def test_real_pytest_exit_and_diagnostics_survive_tee(tmp_path, behavior, expected):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_case.py").write_text(
        "import os, signal, time\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.fixture\ndef resource():\n"
        "    Path('pid').write_text(str(os.getpid()))\n"
        "    try:\n"
        + {
            "success": "", "failure": "",
            "hang": "        while True: time.sleep(1)\n",
            "ignore": "        signal.signal(signal.SIGINT, signal.SIG_IGN)\n        while True: time.sleep(1)\n",
        }[behavior]
        + "        yield\n"
        "    finally:\n        Path('cleaned').write_text('yes')\n"
        "def test_intent(resource):\n"
        + ("    assert False, 'intentional failure'\n" if behavior == "failure" else "    assert True\n")
    )
    command = [
        sys.executable, str(RUNNER), "--timeout-seconds", "3", "--grace-seconds", "0.5",
        "--", "-c", str(tmp_path / "pytest.ini"), str(tmp_path / "test_case.py"),
        "-o", "faulthandler_timeout=0.2",
    ]
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(  # noqa: S603 - fixed local fixture and quoted arguments
        ["bash", "-c", "set -o pipefail\n" + shlex.join(command) + " 2>&1 | tee result.log"],  # noqa: S607
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert (tmp_path / "result.log").read_text() == result.stdout
    assert "test_case.py::test_intent" in result.stdout
    assert (tmp_path / "cleaned").exists() == (behavior != "ignore")
    if expected == 124:
        assert "Timeout (" in result.stdout
        assert 'in resource' in result.stdout
        assert "Pytest deadline exceeded" in result.stdout
        with pytest.raises(ProcessLookupError):
            os.kill(int((tmp_path / "pid").read_text()), 0)
    elif expected == 1:
        assert "intentional failure" in result.stdout
