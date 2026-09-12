"""Reject formatting-only claims that remove application logic (RECOVER-2)."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess

FORMAT_CLAIM = re.compile(
    r"\bformat(?:ting)?[ -]+only\b|\bonly[ -]+format(?:ting)?\b"
    r"|\bformat(?:ting)?[ -]+baseline\b|^style(?:\([^\n)]*\))?:"
    r"|^chore\(format(?:ting)?\):|\bno (?:logic|behavior(?:al)?) changes\b",
    re.IGNORECASE | re.MULTILINE,
)


def git(*args: str) -> str:
    return subprocess.check_output(  # noqa: S603,S607 - fixed executable, argument array
        ["git", *args],  # noqa: S607 - controlled Git executable
        text=True,
    )


def check_range(base: str, head: str) -> list[str]:
    """Inspect each commit, including bad intermediate commits hidden by a later fix."""
    violations = []
    for commit in git("rev-list", "--reverse", f"{base}..{head}").splitlines():
        message = git("show", "-s", "--format=%B", commit)
        if not FORMAT_CLAIM.search(message):
            continue
        parents = git("rev-list", "--parents", "-n", "1", commit).split()
        if len(parents) < 2:
            continue  # A root commit cannot delete prior application logic.
        parent = parents[1]
        stats = git(
            "diff", "-w", "--ignore-blank-lines", "--numstat", "-z", "--no-renames", parent, commit, "--", "app/"
        )
        for row in stats.split("\0"):
            if not row:
                continue
            added, removed, path = row.split("\t", 2)
            if not removed.isdigit() or int(removed) <= int(added):
                continue
            before = git("show", f"{parent}:{path}")
            exists = bool(git("ls-tree", "--name-only", commit, "--", path).strip())
            after = git("show", f"{commit}:{path}") if exists else ""
            if path.endswith(".py"):
                try:
                    if ast.dump(ast.parse(before)) == ast.dump(ast.parse(after)):
                        continue  # Line wrapping/comments can change numstat, not logic.
                except SyntaxError:
                    pass  # Do not certify an unparseable edit as formatting-only.
            violations.append(
                f"{commit[:12]} {path}: +{added}/-{removed} with changed logic; "
                "restore the code or describe the behavioral change in the commit message"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("head")
    args = parser.parse_args()
    violations = check_range(args.base, args.head)
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
