import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { displayClaim } from "@/lib/api/evidence";
import fixtures from "../../../tests/fixtures/evidence_display_claims.json";

describe("readable claims with exact provenance", () => {
  it.each(fixtures.cases)("cleans production claim $id", ({ claim, display }) => {
    expect(displayClaim(claim)).toBe(display);
  });
  it.each([
    "Ordinary sourced sentence.", "  Keep whitespace.\r\nAnd a second line.  ",
    "A | B is a choice, not a table.", "Use `a | b` in a shell.", "| One leading pipe",
  ])("preserves non-table text exactly: %s", claim => {
    expect(displayClaim(claim)).toBe(claim);
  });
  it.each([
    ["| a | b |", "a · b"], ["| a | b", "a · b"], ["a | b |", "a · b"],
    ["| a | --- | b |", "a · b"],
    ["| a | b |\n| :--- | ---: |\n| c | d |", "a · b; c · d"],
    ["Before\n| a | b |\n| c | d |\nAfter", "Before\na · b; c · d\nAfter"],
  ])("keeps cells and rows in reading order: %s", (claim, display) => {
    expect(displayClaim(claim)).toBe(display);
  });
  it("renders the server-generated evidence brief claim as prose, never a table", () => {
    // Produced by _render_markdown and asserted byte-for-byte in its Python test.
    const { container } = render(<MarkdownRenderer content={fixtures.brief.markdown} />);
    expect(container.querySelector("table")).toBeNull();
    expect(screen.getByText(/a · b; c · d/)).toHaveTextContent("Claim: a · b; c · d");
  });
});
