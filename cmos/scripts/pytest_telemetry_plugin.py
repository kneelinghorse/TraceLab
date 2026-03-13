"""Pytest plugin that records structured telemetry for test runs.

This plugin captures per-test outcomes along with aggregate metadata and
persists them as JSON so the telemetry aggregator can build
``testing-summary.json`` without manual editing.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_OUTPUT = Path("telemetry/events/.artifacts/pytest-latest.json")
_PLUGIN_HANDLE = "pytest-telemetry-plugin"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_disabled(config) -> bool:
    env_flag = os.getenv("PYTEST_DISABLE_TELEMETRY", "").lower() in {"1", "true", "yes"}
    return bool(env_flag or config.getoption("disable_pytest_telemetry"))


def pytest_addoption(parser):
    group = parser.getgroup("telemetry", "TraceLab telemetry options")
    group.addoption(
        "--pytest-telemetry-output",
        action="store",
        dest="pytest_telemetry_output",
        default=None,
        help="Optional path for the pytest telemetry artifact (defaults to telemetry/events/.artifacts/pytest-latest.json)",
    )
    group.addoption(
        "--pytest-telemetry-label",
        action="store",
        dest="pytest_telemetry_label",
        default=None,
        help="Optional label for the telemetry entry (e.g. local-dev, ci)",
    )
    group.addoption(
        "--disable-pytest-telemetry",
        action="store_true",
        dest="disable_pytest_telemetry",
        help="Disable telemetry emission for this pytest invocation",
    )


def pytest_configure(config):
    if _is_disabled(config):
        return

    # Avoid double registration when pytest_configure executes twice.
    if getattr(config, "_pytest_telemetry_plugin", None):
        return

    plugin = PytestTelemetryPlugin(config)
    config.pluginmanager.register(plugin, _PLUGIN_HANDLE)
    config._pytest_telemetry_plugin = plugin


def pytest_unconfigure(config):
    plugin = getattr(config, "_pytest_telemetry_plugin", None)
    if plugin is None:
        return

    config.pluginmanager.unregister(plugin)
    delattr(config, "_pytest_telemetry_plugin")


@dataclass
class PhaseResult:
    phase: str
    outcome: str
    duration: Optional[float]
    longrepr: Optional[str] = None
    wasxfail: Optional[str] = None


@dataclass
class TestRecord:
    nodeid: str
    file: str
    line: int
    name: str
    markers: List[str] = field(default_factory=list)
    phases: List[PhaseResult] = field(default_factory=list)

    def add_phase(self, phase: PhaseResult) -> None:
        self.phases.append(phase)

    def status(self) -> str:
        outcomes = [phase.outcome for phase in self.phases]
        if any(outcome == "failed" for outcome in outcomes):
            return "failed"

        xfail = next((phase.wasxfail for phase in self.phases if phase.wasxfail), None)
        if xfail:
            if any(outcome == "passed" for outcome in outcomes):
                return "xpassed"
            return "xfailed"

        if outcomes and all(outcome == "skipped" for outcome in outcomes):
            return "skipped"

        if not outcomes:
            return "error"

        return "passed"


class PytestTelemetryPlugin:
    def __init__(self, config):
        self.config = config
        self.repo_root = _repo_root()
        self.start_time = datetime.now(timezone.utc)
        self._timer = time.perf_counter()
        self.records: Dict[str, TestRecord] = {}

        output_override = config.getoption("pytest_telemetry_output") or os.getenv(
            "PYTEST_TELEMETRY_OUTPUT"
        )
        self.output_path = self._resolve_path(output_override or DEFAULT_OUTPUT)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.label = config.getoption("pytest_telemetry_label") or os.getenv(
            "PYTEST_TELEMETRY_LABEL"
        )

    # --- Pytest hook implementations -------------------------------------------------
    def pytest_runtest_logreport(
        self, report
    ):  # pragma: no cover - exercised via pytest runtime
        # Skip collection stage noise.
        if report.nodeid.startswith("collect"):
            return

        record = self.records.get(report.nodeid)
        if record is None:
            rel_file = (
                self._relative_path(report.location[0])
                if report.location
                else report.nodeid
            )
            record = TestRecord(
                nodeid=report.nodeid,
                file=rel_file,
                line=report.location[1] if report.location else 0,
                name=report.location[2] if report.location else report.nodeid,
                markers=sorted(k for k, v in report.keywords.items() if v),
            )
            self.records[report.nodeid] = record

        phase = PhaseResult(
            phase=report.when,
            outcome=report.outcome,
            duration=getattr(report, "duration", None),
            longrepr=str(report.longrepr) if report.failed else None,
            wasxfail=getattr(report, "wasxfail", None),
        )
        record.add_phase(phase)

    def pytest_sessionfinish(
        self, session, exitstatus
    ):  # pragma: no cover - exercised via pytest runtime
        payload = self._build_payload(session, exitstatus)
        with self.output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    # ---------------------------------------------------------------------------------
    def _resolve_path(self, target: str | Path) -> Path:
        target_path = Path(target)
        if target_path.is_absolute():
            return target_path
        return self.repo_root / target_path

    def _relative_path(self, target: str) -> str:
        try:
            return str(Path(target).resolve().relative_to(self.repo_root))
        except Exception:
            return target

    def _build_payload(self, session, exitstatus) -> Dict[str, Any]:
        duration = time.perf_counter() - self._timer
        aggregated: Dict[str, int] = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
            "error": 0,
        }
        serialized_tests: List[Dict[str, Any]] = []

        for record in sorted(self.records.values(), key=lambda item: item.nodeid):
            status = record.status()
            aggregated[status] = aggregated.get(status, 0) + 1
            serialized_tests.append(
                {
                    "nodeid": record.nodeid,
                    "name": record.name,
                    "file": record.file,
                    "line": record.line,
                    "markers": record.markers,
                    "status": status,
                    "phases": [
                        {
                            "phase": phase.phase,
                            "outcome": phase.outcome,
                            "duration": phase.duration,
                            **({"longrepr": phase.longrepr} if phase.longrepr else {}),
                            **({"wasxfail": phase.wasxfail} if phase.wasxfail else {}),
                        }
                        for phase in record.phases
                    ],
                }
            )

        total = sum(aggregated.values())
        failures = (
            aggregated.get("failed", 0)
            + aggregated.get("error", 0)
            + aggregated.get("xpassed", 0)
        )
        status = "passed" if failures == 0 else "failed"

        payload: Dict[str, Any] = {
            "tool": "pytest",
            "generatedAt": self.start_time.isoformat(),
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "durationSeconds": round(duration, 4),
            "status": status,
            "summary": {
                "total": total,
                **aggregated,
            },
            "environment": self._environment_block(session, exitstatus),
            "label": self.label,
            "tests": serialized_tests,
            "artifactPath": str(
                self.output_path.relative_to(self.repo_root)
                if self.output_path.is_relative_to(self.repo_root)
                else self.output_path
            ),
        }

        return payload

    def _environment_block(self, session, exitstatus) -> Dict[str, Any]:
        return {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "ci": {
                "provider": os.getenv("GITHUB_ACTIONS") and "github-actions" or None,
                "runId": os.getenv("GITHUB_RUN_ID"),
                "runNumber": os.getenv("GITHUB_RUN_NUMBER"),
            },
            "exitStatus": exitstatus,
            "failed": session.testsfailed if hasattr(session, "testsfailed") else None,
            "gitSha": self._git_sha(),
        }

    def _git_sha(self) -> Optional[str]:
        env_sha = os.getenv("GITHUB_SHA")
        if env_sha:
            return env_sha

        try:
            result = subprocess.run(
                [
                    "git",
                    "rev-parse",
                    "HEAD",
                ],
                capture_output=True,
                check=True,
                text=True,
            )
        except Exception:
            return None

        return result.stdout.strip() or None
