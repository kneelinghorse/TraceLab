"""Run pytest with a POSIX process deadline, stack evidence and cleanup grace."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from contextlib import suppress


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=2100)
    parser.add_argument("--grace-seconds", type=float, default=20)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.grace_seconds <= 0:
        parser.error("Deadlines must be positive")
    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    # Verbose node IDs identify the active test even if it never returns. Keep
    # pytest's existing 120-second all-thread dump, including during fixtures.
    command = [sys.executable, "-m", "pytest", "-vv", "-o", "faulthandler_timeout=120", *pytest_args]
    process = subprocess.Popen(  # noqa: S603 - fixed pytest executable, forwarded CLI arguments
        command, env={**os.environ, "PYTHONUNBUFFERED": "1"}, start_new_session=True,
    )
    try:
        try:
            code = process.wait(timeout=args.timeout_seconds)
            return 128 - code if code < 0 else code
        except subprocess.TimeoutExpired:
            print("Pytest deadline exceeded; interrupting for cleanup", file=sys.stderr, flush=True)
            code = 124
        except KeyboardInterrupt:
            code = 130
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=args.grace_seconds)
        except subprocess.TimeoutExpired:
            print("Pytest cleanup grace expired; killing test process group", file=sys.stderr, flush=True)
        return code
    finally:
        # Also reap descendants that ignored the interrupt after pytest exited.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
