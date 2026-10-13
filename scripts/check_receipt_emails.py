#!/usr/bin/env python3
"""Reject personal email addresses in public acceptance receipts, without echoing them."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.check_no_credential_literals import _tracked_paths

# Owner-controlled domains and reserved examples only. Never add participant
# domains here to make a receipt pass: replace the address with a placeholder.
_ALLOWED_DOMAINS = frozenset({
    "deniedart.com", "aquex.ai", "tracelab.aquex.ai", "tracelab.local",
    "example.com", "example.org", "example.net",
})
_EMAIL = re.compile(
    r"(?<![\w@/])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?P<domain>(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63})(?![\w-]|\.[A-Za-z0-9-])"
)


def find_email_lines(text: str) -> list[int]:
    """Return offending line numbers; keep personal identifiers out of diagnostics."""
    return [
        number
        for number, line in enumerate(text.splitlines(), 1)
        if any(
            match['domain'].lower() not in _ALLOWED_DOMAINS
            and not match['domain'].lower().endswith((".test", ".invalid"))
            for match in _EMAIL.finditer(line)
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    if args.tracked and args.paths:
        parser.error("--tracked cannot be combined with explicit paths")
    try:
        paths = [
            p for p in _tracked_paths()
            if p.as_posix().startswith(("cmos/reports/", "telemetry/"))
        ] if args.tracked else args.paths
        failed = False
        for path in paths:
            data = path.read_bytes()
            if b"\0" in data:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for line in find_email_lines(text):
                print(f"{path}:{line}: non-allowlisted email (value withheld)", file=sys.stderr)
                failed = True
        return int(failed)
    except (OSError, subprocess.CalledProcessError):
        print("Receipt email scan failed: unable to read tracked files or requested receipt.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
