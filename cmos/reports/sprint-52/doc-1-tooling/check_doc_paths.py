#!/usr/bin/env python3
"""Repository path check for the DOC-1 documentation set.

Every path-like token in the given Markdown files is resolved against the
repository. A token resolves when it exists relative to the document's own
directory, the repository root, or one of a short list of conventional base
directories (so ``index.tsx`` inside a routes table resolves under
``frontend/src/pages``). Glob tokens resolve when they match at least one
file. ``git show <sha>:<path>`` references are checked against git history.
Directory-tree diagrams (``├── name``) are walked by indentation and every
entry is resolved as a full path. Tokens without a slash count only when they
are marked as code (backticks) or used as a Markdown link target.
Placeholders are accepted only through the allowlist, which carries a reason
per entry. The exit status is 1 when any unresolved path remains.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXTENSIONS = (
    ".md", ".py", ".ts", ".tsx", ".mjs", ".js", ".json", ".yml", ".yaml",
    ".toml", ".txt", ".sh", ".ini", ".css", ".cfg", ".lock", ".tgz", ".sql",
    ".html", ".example",
)
TOP_LEVEL = {
    ".github", ".devcontainer", "alembic", "app", "cmos", "docs", "frontend",
    "packages", "scripts", "tests", "deploy", "config", "data",
}
BASES = (
    "", "cmos", "docs", "frontend", "frontend/src", "frontend/src/pages",
    "frontend/src/components", "frontend/src/lib", "frontend/src/lib/api",
    "frontend/src/contexts", "frontend/scripts", "app", "cmos/docs", "cmos/context",
    "cmos/scripts", ".github/workflows", "packages/tracelab-mcp", "scripts", "tests",
)
TOKEN = re.compile(r"[A-Za-z0-9_@$./*:\[\]{}<>~-]+")
BACKTICK = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\]\(([^)\s]+)\)")
GIT_SHOW = re.compile(r"git show ([0-9a-f]{7,40}):([^\s`'\")]+)")
GIT_SHA_PREFIX = re.compile(r"^[0-9a-f]{7,40}:")
LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)$")
TREE_LINE = re.compile(r"^(?P<indent>(?:[│ ]   )*)[├└]── (?P<name>\S+)")
STRIP_TRAILING = ".,;:)('\"`"
STRIP_LEADING = "('\"`"


def normalize(raw: str) -> str:
    """Strip surrounding punctuation, bold markers and line suffixes."""
    token = raw.rstrip(STRIP_TRAILING).lstrip(STRIP_LEADING)
    token = re.sub(r"^\*\*|\*\*$", "", token)
    if token.startswith("[") and "]" not in token:
        token = token[1:]
    if token.endswith("]") and "[" not in token:
        token = token[:-1]
    return LINE_SUFFIX.sub("", token)


def is_path(token: str, *, explicit: bool) -> bool:
    """Decide whether a normalized token is a repository path."""
    if not token or token.startswith(("http", "@", "/", "<", "{", "$", "~", "#")):
        return False
    if "://" in token or "{" in token or "<" in token or ":" in token or GIT_SHA_PREFIX.match(token):
        return False
    if "/" in token:
        first = token.split("/", 1)[0]
        return token.endswith(EXTENSIONS) or token.endswith("/") or first in TOP_LEVEL or first in {".", ".."}
    return explicit and token.endswith(EXTENSIONS) and len(token) > len(Path(token).suffix)


def extract(line: str) -> list[tuple[str, bool]]:
    """Return (token, explicit) pairs found on one prose line."""
    found: list[tuple[str, bool]] = []
    for match in BACKTICK.finditer(line):
        span = match.group(1).strip()
        if " " in span:
            found.extend((token, True) for token in TOKEN.findall(span))
        else:
            found.append((span, True))
    outside = BACKTICK.sub(" ", line)
    found.extend((match.group(1), True) for match in LINK.finditer(outside))
    outside = LINK.sub(" ", outside)
    found.extend((token, False) for token in TOKEN.findall(outside))
    return found


def tree_entry(line: str, stack: list[str], repo_name: str) -> str | None:
    """Return the full path of a directory-tree diagram line, or None."""
    stripped = line.strip()
    if stripped == f"{repo_name}/":
        stack.clear()
        return "."
    match = TREE_LINE.match(line)
    if match is None:
        return None
    depth = len(match.group("indent")) // 4
    name = match.group("name")
    del stack[depth:]
    stack.append(name.rstrip("/"))
    return "/".join(stack) + ("/" if name.endswith("/") else "")


def resolves(repo: Path, doc_dir: Path, token: str) -> str | None:
    """Return the base that resolves the token, or None."""
    bases: list[Path] = [doc_dir, *(repo / base for base in BASES)]
    for base in bases:
        if "*" in token:
            pattern = token if "/" in token else f"**/{token}"
            try:
                matched = any(True for _ in base.glob(pattern))
            except ValueError:
                matched = False
            if matched:
                return str(base.relative_to(repo)) or "."
        elif (base / token).exists():
            return str(base.relative_to(repo)) or "."
    return None


def git_object_exists(repo: Path, sha: str, path: str) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    result = subprocess.run(  # noqa: S603
        [git, "-C", str(repo), "cat-file", "-e", f"{sha}:{path}"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def check_document(repo: Path, doc: Path, allow: dict[str, str]) -> dict:
    text = doc.read_text()
    doc_dir = doc.parent
    seen: dict[str, dict] = {}
    tree_stack: list[str] = []

    def record(token: str, line_no: int, *, tree: bool = False) -> None:
        if token in seen:
            return
        if token in allow:
            seen[token] = {"line": line_no, "status": "allowlisted", "base": None, "reason": allow[token]}
            return
        base = "." if tree and (repo / token).exists() else (None if tree else resolves(repo, doc_dir, token))
        seen[token] = {"line": line_no, "status": "resolved" if base is not None else "unresolved", "base": base}

    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in GIT_SHOW.finditer(line):
            sha, path = match.group(1), match.group(2).rstrip(STRIP_TRAILING)
            key = f"{sha}:{path}"
            if key not in seen:
                ok = git_object_exists(repo, sha, path)
                seen[key] = {"line": line_no, "status": "git" if ok else "unresolved", "base": None}
        entry = tree_entry(line, tree_stack, repo.name)
        if entry is not None:
            if entry != ".":
                record(entry, line_no, tree=True)
            continue
        for raw, explicit in extract(line):
            token = normalize(raw)
            if is_path(token, explicit=explicit):
                record(token, line_no)
    counts = {"resolved": 0, "git": 0, "allowlisted": 0, "unresolved": 0}
    for entry in seen.values():
        counts[entry["status"]] += 1
    return {"document": str(doc.relative_to(repo)), "counts": counts, "tokens": seen}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("documents", nargs="+", help="Markdown files, relative to the repository root")
    parser.add_argument("--repo", default=None, help="Repository root (default: git toplevel)")
    parser.add_argument("--allow", default=None, help="JSON file mapping placeholder tokens to reasons")
    parser.add_argument("--json", dest="json_out", default=None, help="Write the full report to this file")
    parser.add_argument("--verbose", action="store_true", help="List every token, not only the unresolved ones")
    args = parser.parse_args()

    if args.repo:
        repo = Path(args.repo).resolve()
    else:
        git = shutil.which("git")
        if git is None:
            print("git is not available; pass --repo", file=sys.stderr)
            return 2
        top = subprocess.run([git, "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)  # noqa: S603
        repo = Path(top.stdout.strip())
    allow: dict[str, str] = {}
    if args.allow:
        allow = json.loads(Path(args.allow).read_text())

    reports = [check_document(repo, repo / doc, allow) for doc in args.documents]
    unresolved_total = 0
    for report in reports:
        counts = report["counts"]
        print(f"{report['document']}: {counts['resolved']} resolved, {counts['git']} git, "
              f"{counts['allowlisted']} allowlisted, {counts['unresolved']} unresolved")
        for token, entry in sorted(report["tokens"].items(), key=lambda item: item[1]["line"]):
            if entry["status"] == "unresolved":
                print(f"  UNRESOLVED line {entry['line']}: {token}")
            elif args.verbose:
                where = entry.get("base") or entry.get("reason") or entry["status"]
                print(f"  {entry['status']:<11} line {entry['line']}: {token} [{where}]")
        unresolved_total += counts["unresolved"]
    if args.json_out:
        report_out = {"repository_root": str(repo), "allowlist": allow, "documents": reports}
        Path(args.json_out).write_text(json.dumps(report_out, indent=2) + "\n")
    print(f"TOTAL unresolved: {unresolved_total}")
    return 1 if unresolved_total else 0


if __name__ == "__main__":
    sys.exit(main())
