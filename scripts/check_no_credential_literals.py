#!/usr/bin/env python3
# ABOUTME: Rejects tracked, hard-coded credential assignments without printing their values.
# ABOUTME: Accepts runtime references and explicit non-production placeholders.

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_ASSIGNMENT_RE = re.compile(
    r"""
    ^[ \t]*
    (?:(?:[-*+>][ \t]+)|(?:\#[ \t]*))?
    `?
    (?:export[ \t]+)?
    ["']?
    (?P<key>[A-Z][A-Z0-9_]*)
    ["']?
    [ \t]*(?P<separator>[:=])[ \t]*
    (?P<value>.*)
    $
    """,
    re.VERBOSE,
)
_SENSITIVE_KEY_SUFFIXES = (
    "PASSWORD",
    "PASSWORD_HASH",
    "PASSCODE",
    "SECRET",
    "SECRET_KEY",
    "CLIENT_SECRET",
    "WEBHOOK_SECRET",
    "TOKEN",
    "API_KEY",
    "PRIVATE_KEY",
    "SECRET_ACCESS_KEY",
    "SIGNING_KEY",
    "ENCRYPTION_KEY",
)
_COLON_ASSIGNMENT_SUFFIXES = {".json", ".md", ".markdown", ".toml", ".yaml", ".yml"}
_ALLOW_DIRECTIVE_RE = re.compile(r"#\s*secret-scan:\s*allow\s+--\s*\S", re.IGNORECASE)
_SIMPLE_REFERENCE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
_BRACED_REFERENCE_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
_GITHUB_REFERENCE_RE = re.compile(
    r"\$\{\{\s*(?:env|secrets|vars)\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}"
)
_SHELL_DEFAULT_RE = re.compile(
    r"\$\{[A-Za-z_][A-Za-z0-9_]*(?P<operator>:-|-|:\+|\+|:\?|\?)(?P<default>.*)\}"
)
_RUNTIME_LOOKUP_RE = re.compile(
    r"(?:os\.)?(?:getenv|environ(?:\.get)?)[ \t]*(?:\(|\[)", re.IGNORECASE
)
_PLACEHOLDER_RE = re.compile(
    r"(?:"
    r"a-(?:very-)?strong-random-(?:key|password|secret)|"
    r"change-?me|"
    r"generate-(?:with-)?openssl-rand-(?:base64|hex)-[0-9]+|"
    r"replace[-_].*|"
    r"(?:dev|development|dummy|example|fake|placeholder|sample|test|testing|your)"
    r"(?:[-_.].*)?"
    r")",
    re.IGNORECASE,
)
_PROVIDER_PLACEHOLDER_RE = re.compile(
    r"[A-Za-z0-9]+-(?:(?:dummy|example|fake|placeholder|test|your)[-_.].*|\.{3}|…)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    key: str


def _is_sensitive_key(key: str) -> bool:
    return any(key.endswith(suffix) for suffix in _SENSITIVE_KEY_SUFFIXES)


def _allows_colon_assignment(path: Path) -> bool:
    return path.suffix.lower() in _COLON_ASSIGNMENT_SUFFIXES


def _scalar_value(raw_value: str) -> str:
    value = re.split(r"\s+#", raw_value.strip(), maxsplit=1)[0].strip()
    value = value.removesuffix("`").strip()

    if len(value) >= 2 and value[0] in {'"', "'"}:
        closing_index = value.rfind(value[0])
        if closing_index > 0:
            value = value[1:closing_index].strip()

    return value


def _is_safe_shell_default(value: str) -> bool:
    match = _SHELL_DEFAULT_RE.fullmatch(value)
    if match is None:
        return False

    default = match.group("default").strip()
    return not default or _is_safe_value(default)


def _is_safe_value(value: str) -> bool:
    value = value.strip()
    if not value:
        return True

    if (
        _SIMPLE_REFERENCE_RE.fullmatch(value)
        or _BRACED_REFERENCE_RE.fullmatch(value)
        or _GITHUB_REFERENCE_RE.fullmatch(value)
        or _is_safe_shell_default(value)
        or (value.startswith("$(") and value.endswith(")"))
        or _RUNTIME_LOOKUP_RE.match(value)
    ):
        return True

    normalized = value.casefold()
    if normalized in {"none", "null", "postgres", "unset"}:
        return True
    if normalized.startswith("[redacted") and normalized.endswith("]"):
        return True
    if (value.startswith("<") and value.endswith(">")) or value in {"...", "…"}:
        return True
    return bool(_PLACEHOLDER_RE.fullmatch(value) or _PROVIDER_PLACEHOLDER_RE.fullmatch(value))


def find_credential_literals(text: str, path: Path) -> list[Finding]:
    """Return unsafe env/config credential assignments without retaining values."""
    findings: list[Finding] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _ASSIGNMENT_RE.match(line)
        if match is None:
            continue

        key = match.group("key")
        if not _is_sensitive_key(key):
            continue
        if match.group("separator") == ":" and not _allows_colon_assignment(path):
            continue
        if _ALLOW_DIRECTIVE_RE.search(line):
            continue

        value = _scalar_value(match.group("value"))
        if not _is_safe_value(value):
            findings.append(Finding(path=path, line_number=line_number, key=key))

    return findings


def _read_text(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None

    content = path.read_bytes()
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tracked_paths() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git executable not found")
    result = subprocess.run(  # noqa: S603 - fixed executable and arguments
        [git, "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        Path(item.decode("utf-8", errors="surrogateescape"))
        for item in result.stdout.split(b"\0")
        if item
    ]


def scan_paths(paths: Sequence[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in dict.fromkeys(paths):
        text = _read_text(path)
        if text is not None:
            findings.extend(find_credential_literals(text, path))
    return findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reject hard-coded credential literals in text files without displaying values."
    )
    parser.add_argument(
        "--tracked",
        action="store_true",
        help="scan every file tracked by Git instead of explicit paths",
    )
    parser.add_argument("paths", nargs="*", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.tracked and args.paths:
        parser.error("--tracked cannot be combined with explicit paths")

    try:
        paths = _tracked_paths() if args.tracked else args.paths
    except (OSError, subprocess.CalledProcessError):
        print("Credential scan failed: unable to list Git-tracked files.", file=sys.stderr)
        return 2

    findings = scan_paths(paths)
    if not findings:
        return 0

    print("Hard-coded credential literals detected (values withheld):", file=sys.stderr)
    for finding in findings:
        print(
            f"  {finding.path}:{finding.line_number}: {finding.key}",
            file=sys.stderr,
        )
    print(
        "Use a runtime secret reference, an obvious non-production placeholder, or "
        "'# secret-scan: allow -- <reason>' for an intentional fixture.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
