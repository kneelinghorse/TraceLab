"""The post-deploy wait must fail loudly; a silent pass would defeat its entire purpose.

Its job is to answer "is production actually running this commit?". Every wrong answer it
could give -- a timeout read as success, a stale sha accepted, a Cloudflare 403 mistaken for
"not deployed yet" -- puts an unsmoked deployment behind a green check (CI-6).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wait_for_deploy.py"
LIVE_SHA = "a" * 40
STALE_SHA = "b" * 40


def _serve(routes: dict[str, tuple[int, object]]) -> tuple[HTTPServer, str]:
    """Start a throwaway HTTP server. routes maps path -> (status, json body or None)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's required name
            status, body = routes.get(self.path, (404, None))
            payload = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _run(base: str, sha: str, tmp_path: Path, budget: int = 2):
    out = tmp_path / "summary.json"
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and script path, no user input
        [
            sys.executable, str(SCRIPT), "--sha", sha,
            "--backend-url", f"{base}/health", "--frontend-url", f"{base}/version",
            "--budget-seconds", str(budget), "--interval-seconds", "1",
            "--output", str(out),
        ],
        capture_output=True, text=True, timeout=120,
    )
    return result, json.loads(out.read_text())


@pytest.mark.unit
def test_both_services_serving_the_sha_succeeds(tmp_path):
    server, base = _serve({
        "/health": (200, {"status": "healthy", "commit": LIVE_SHA}),
        "/version": (200, {"commit": LIVE_SHA}),
    })
    try:
        result, summary = _run(base, LIVE_SHA, tmp_path)
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stderr
    assert summary["ok"] is True
    assert set(summary["seconds_to_serve"]) == {"backend", "frontend"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("routes", "reason"),
    [
        pytest.param(
            {"/health": (200, {"commit": STALE_SHA}), "/version": (200, {"commit": LIVE_SHA})},
            "backend still serving the previous deployment",
            id="backend-stale",
        ),
        pytest.param(
            {"/health": (200, {"commit": LIVE_SHA}), "/version": (200, {"commit": STALE_SHA})},
            "frontend assets built from the previous commit",
            id="frontend-stale",
        ),
        pytest.param(
            {"/health": (200, {"commit": LIVE_SHA}), "/version": (403, None)},
            "Cloudflare blocking the poller must not read as deployed",
            id="frontend-forbidden",
        ),
        pytest.param(
            {"/health": (200, {"status": "healthy"}), "/version": (200, {"commit": LIVE_SHA})},
            "a health payload with no commit field proves nothing",
            id="backend-no-marker",
        ),
    ],
)
def test_anything_short_of_both_services_serving_the_sha_fails(routes, reason, tmp_path):
    server, base = _serve(routes)
    try:
        result, summary = _run(base, LIVE_SHA, tmp_path)
    finally:
        server.shutdown()
    assert result.returncode == 1, f"{reason}: expected a loud failure, got {result.returncode}"
    assert summary["ok"] is False
    assert "Production is NOT running the merged commit" in result.stderr
