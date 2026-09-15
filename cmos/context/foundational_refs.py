"""Boundary-aware foundational-reference rules shared by the validator script and the CLI.

Both ``cmos/scripts/validate_foundational_refs.py`` and ``./cmos/cli.py validate docs``
consume these rules. A forbidden path only matches when it stands on its own path
boundary: ``docs/technical_architecture.md`` must not fire inside the legitimate
``cmos/foundational-docs/technical_architecture.md`` (the false positive commit
7ec2c02 worked around by rewording text), while ``cmos/docs/technical_architecture.md``
or ``./docs/roadmap.md`` still fire because ``/`` and ``.`` are not path-name characters.
"""

from __future__ import annotations

import re
from pathlib import Path

FOUNDATIONAL_CHECKS: dict[Path, dict[str, list[str]]] = {
    Path("agents.md"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
    Path("README.md"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
    Path("context/MASTER_CONTEXT.json"): {
        "required": [
            "foundational-docs/roadmap_template.md",
            "foundational-docs/tech_arch_template.md",
        ],
        "forbidden": [
            "docs/roadmap.md",
            "docs/technical_architecture.md",
        ],
    },
}


def forbidden_pattern(needle: str) -> re.Pattern[str]:
    """Match ``needle`` only when neither side continues a path-name (a word character or ``-``)."""
    return re.compile(rf"(?<![\w-]){re.escape(needle)}(?![\w-])")


def contains_forbidden(content: str, forbidden: list[str]) -> bool:
    return any(forbidden_pattern(needle).search(content) for needle in forbidden)


def validate_file(path: Path, required: list[str], forbidden: list[str], label: str | None = None) -> list[str]:
    """Return the validation failures for one file; ``label`` names it in messages (defaults to the path)."""
    name = label or str(path)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"{name}: missing file"]
    errors: list[str] = []
    for needle in required:
        if needle not in content:
            errors.append(f"{name}: missing required reference '{needle}'")
    for needle in forbidden:
        if forbidden_pattern(needle).search(content):
            errors.append(f"{name}: contains forbidden reference '{needle}'")
    return errors
