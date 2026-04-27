"""Helpers for normalizing mission titles across execution paths.

VENDORED from DeepSearch.alpha — see cmos/contracts/deepsearch-compiler-vendor.md
for the pinned commit and resync ritual (T41.1, sprint-41). Do not hand-edit.
"""

from __future__ import annotations


def normalize_mission_title(title: str | None, mission_id: str | None) -> str:
    """Strip a duplicated mission-id prefix from a human title when present."""

    raw_title = str(title or "").strip()
    if not raw_title:
        return str(mission_id or "").strip()

    raw_mission_id = str(mission_id or "").strip()
    if not raw_mission_id:
        return raw_title

    if not raw_title.casefold().startswith(raw_mission_id.casefold()):
        return raw_title

    remainder = raw_title[len(raw_mission_id):].lstrip()
    if not remainder:
        return raw_title

    if remainder[0] not in {"-", ":", "|", "–", "—"}:
        return raw_title

    normalized = remainder[1:].strip()
    return normalized or raw_title

