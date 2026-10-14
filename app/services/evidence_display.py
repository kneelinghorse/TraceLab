"""Readable evidence labels; the ledger's exact cited spans stay untouched."""

import re


def display_claim(claim: str) -> str:
    """Join consecutive table rows, preserving surrounding non-table text."""
    lines: list[str] = []
    rows: list[str] = []
    for line in claim.split("\n"):
        stripped = line.strip()
        cells = stripped.removeprefix("|").removesuffix("|").split("|")
        # Cited spans often end before the final pipe. A single leading pipe
        # without another cell is prose, not enough evidence of a table row.
        if (stripped.startswith("|") or stripped.endswith("|")) and len(cells) > 1:
            cells = [cell.strip() for cell in cells]
            rendered = " · ".join(cell for cell in cells if cell and not re.fullmatch(r":?-{3,}:?", cell))
            if rendered:
                rows.append(rendered)
        else:
            if rows:
                lines.append("; ".join(rows))
                rows = []
            lines.append(line)
    if rows:
        lines.append("; ".join(rows))
    return "\n".join(lines)
