"""Table layout must not obscure a claim or alter its exact stored provenance."""

import json
from pathlib import Path

import pytest

from app.models.evidence_ledger import LedgerEntry
from app.services.evidence_display import display_claim
from app.services.evidence_ledger import _render_markdown

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures/evidence_display_claims.json").read_text()
)
CASES = FIXTURES["cases"]


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_real_cited_rows_are_readable_without_rewriting_provenance(case):
    assert display_claim(case["claim"]) == case["display"]


@pytest.mark.unit
@pytest.mark.parametrize("claim", [
    "Ordinary sourced sentence.", "  Keep whitespace.\r\nAnd a second line.  ",
    "A | B is a choice, not a table.", "Use `a | b` in a shell.", "| One leading pipe",
])
def test_non_table_claims_are_byte_identical(claim):
    assert display_claim(claim) == claim


@pytest.mark.unit
@pytest.mark.parametrize(("claim", "expected"), [
    ("| a | b |", "a · b"),
    ("| a | b", "a · b"),
    ("a | b |", "a · b"),
    ("| a | --- | b |", "a · b"),
    ("| a | b |\n| :--- | ---: |\n| c | d |", "a · b; c · d"),
    ("Before\n| a | b |\n| c | d |\nAfter", "Before\na · b; c · d\nAfter"),
])
def test_table_cells_and_rows_remain_in_reading_order(claim, expected):
    assert display_claim(claim) == expected


@pytest.mark.unit
def test_evidence_brief_changes_only_the_claim_display():
    raw = FIXTURES["brief"]["claim"]
    entry = LedgerEntry(claim=raw, disposition="supporting", origin="mcp-agent",
                        source_url="https://example.test/source", tags=[])
    markdown = _render_markdown("claim-display", [entry], [])
    # The frontend renders this exact server output with its production renderer.
    assert markdown == FIXTURES["brief"]["markdown"]
    assert "- **Claim:** a · b; c · d\n" in markdown
    assert "|" not in markdown
    assert entry.claim == raw
