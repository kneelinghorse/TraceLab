"""Aggregate pytest, Playwright, and integration runner telemetry artifacts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-artifact", default="telemetry/events/.artifacts/pytest-latest.json", help="Path to the pytest telemetry JSON artifact")
    parser.add_argument("--playwright-artifact", default="telemetry/events/.artifacts/playwright-latest.json", help="Path to the Playwright telemetry JSON artifact")
    parser.add_argument("--integration-artifact", default="telemetry/events/.artifacts/integration-runner.json", help="Path to write/read the integration runner JSON report")
    parser.add_argument("--output", default="telemetry/events/testing-summary.json", help="Final aggregated telemetry path")
    parser.add_argument("--mirror-output", default="cmos/telemetry/events/testing-summary.json", help="Secondary mirror path for Mission Protocol documentation")
    parser.add_argument("--no-mirror", action="store_true", help="Skip writing the mirrored telemetry artifact")
    parser.add_argument("--manifest", default=None, help="Optional integration test manifest path (defaults to runner builtin)")
    parser.add_argument("--skip-integration", action="store_true", help="Skip running the integration test runner (expects existing artifact)")
    parser.add_argument("--integration-runner", default="cmos/context/integration_test_runner.js", help="Path to the integration runner entrypoint")
    parser.add_argument("--allow-failures", action="store_true", help="Exit successfully even if any suite failed")
    return parser.parse_args()


@dataclass
class AggregatorPaths:
    pytest: Path
    playwright: Path
    integration: Path
    output: Path
    mirror: Path | None


class TelemetryAggregator:
    def __init__(self, args: argparse.Namespace):
        self.root = repo_root()
        self.args = args
        self.paths = AggregatorPaths(
            pytest=self._resolve(args.pytest_artifact),
            playwright=self._resolve(args.playwright_artifact),
            integration=self._resolve(args.integration_artifact),
            output=self._resolve(args.output),
            mirror=None if args.no_mirror or not args.mirror_output else self._resolve(args.mirror_output),
        )

    def run(self) -> Dict[str, Any]:
        if not self.args.skip_integration:
            self._run_integration_runner()

        pytest_data = self._load_json(self.paths.pytest, "pytest")
        playwright_data = self._load_json(self.paths.playwright, "playwright")
        integration_data = self._load_json(self.paths.integration, "integration runner")

        payload = self._build_payload(pytest_data, playwright_data, integration_data)
        self._write_output(payload)
        return payload

    # ---------------------------------------------------------------------
    def _run_integration_runner(self) -> None:
        runner_path = self._resolve(self.args.integration_runner)
        if not runner_path.exists():
            raise FileNotFoundError(f"Integration runner missing at {runner_path}")

        cmd = ["node", str(runner_path.relative_to(self.root))]
        if self.args.manifest:
            cmd.extend(["--manifest", str(self._resolve(self.args.manifest))])
        cmd.extend(["--output", str(self.paths.integration)])

        result = subprocess.run(cmd, cwd=self.root)
        if result.returncode != 0:
            print(
                f"Integration runner exited with code {result.returncode}."
                f" Latest artifact: {self._relative(self.paths.integration)}",
                file=sys.stderr,
            )

    def _load_json(self, path: Path, label: str) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {label} artifact at {path}. Run the corresponding test suite first.")
        return json.loads(path.read_text())

    def _build_payload(self, pytest_data: Dict[str, Any], playwright_data: Dict[str, Any], integration_data: Dict[str, Any]) -> Dict[str, Any]:
        sources = {
            "pytest": pytest_data.get("status", "unknown"),
            "playwright": playwright_data.get("status", "unknown"),
            "integration": integration_data.get("status", "unknown"),
        }
        status = "passed" if all(value == "passed" for value in sources.values()) else "failed"

        summary = {
            "pytest": self._summarize_pytest(pytest_data),
            "playwright": self._summarize_playwright(playwright_data),
            "integration": self._summarize_integration(integration_data),
        }
        summary["aggregate"] = self._aggregate(summary)

        payload = {
            "meta": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "generator": "cmos/scripts/aggregate_test_telemetry.py",
                "status": status,
                "artifacts": {
                    "pytest": self._relative(self.paths.pytest),
                    "playwright": self._relative(self.paths.playwright),
                    "integration": self._relative(self.paths.integration),
                    "output": self._relative(self.paths.output),
                    **({"mirror": self._relative(self.paths.mirror)} if self.paths.mirror else {}),
                },
                "gitSha": self._git_sha(),
            },
            "summary": summary,
            "details": {
                "pytest": pytest_data,
                "playwright": playwright_data,
                "integration": integration_data,
            },
        }

        return payload

    def _summarize_pytest(self, data: Dict[str, Any]) -> Dict[str, Any]:
        summary = data.get("summary", {})
        return {
            "status": data.get("status"),
            "total": summary.get("total", 0),
            "failed": summary.get("failed", 0) + summary.get("error", 0) + summary.get("xpassed", 0),
            "skipped": summary.get("skipped", 0) + summary.get("xfailed", 0),
            "passed": summary.get("passed", 0),
            "artifact": self._relative(self.paths.pytest),
        }

    def _summarize_playwright(self, data: Dict[str, Any]) -> Dict[str, Any]:
        summary = data.get("summary", {})
        return {
            "status": data.get("status"),
            "total": summary.get("total", 0),
            "failed": summary.get("failed", 0),
            "skipped": summary.get("skipped", 0),
            "passed": summary.get("passed", 0),
            "artifact": self._relative(self.paths.playwright),
        }

    def _summarize_integration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        summary = data.get("summary", {})
        return {
            "status": data.get("status"),
            "suites": summary.get("suites", 0),
            "suitesFailed": summary.get("suitesFailed", 0),
            "tests": summary.get("tests", 0),
            "testsFailed": summary.get("testsFailed", 0),
            "artifact": self._relative(self.paths.integration),
        }

    def _aggregate(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        all_green = summary["pytest"]["status"] == summary["playwright"]["status"] == summary["integration"]["status"] == "passed"
        return {
            "status": "passed" if all_green else "failed",
            "tests": summary["pytest"]["total"] + summary["playwright"]["total"] + summary["integration"]["tests"],
            "testsFailed": summary["pytest"]["failed"] + summary["playwright"]["failed"] + summary["integration"]["testsFailed"],
        }

    def _write_output(self, payload: Dict[str, Any]) -> None:
        serialized = json.dumps(payload, indent=2)
        self.paths.output.parent.mkdir(parents=True, exist_ok=True)
        self.paths.output.write_text(serialized + "\n")

        if self.paths.mirror:
            self.paths.mirror.parent.mkdir(parents=True, exist_ok=True)
            self.paths.mirror.write_text(serialized + "\n")

    def _resolve(self, target: str | Path) -> Path:
        path = Path(target)
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    def _relative(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def _git_sha(self) -> str | None:
        try:
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, check=True, text=True)
            return result.stdout.strip()
        except Exception:
            return os.getenv("GITHUB_SHA")


def main() -> int:
    args = parse_args()
    aggregator = TelemetryAggregator(args)
    payload = aggregator.run()
    print(json.dumps(payload["summary"], indent=2))
    status = payload["meta"].get("status")
    if status != "passed" and not args.allow_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
