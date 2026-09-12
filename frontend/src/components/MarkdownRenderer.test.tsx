import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";

describe("accessible research markdown", () => {
  it("announces task status as document content instead of unnamed form controls", () => {
    render(<MarkdownRenderer content={"- [x] Verify the source\n- [ ] Review the contradiction"} />);
    expect(screen.getByRole("img", { name: "Completed", exact: true })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Not completed", exact: true })).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByText("Verify the source")).toBeTruthy();
    expect(screen.getByText("Review the contradiction")).toBeTruthy();
  });
  it("lets keyboard users reach a wide table's scroll region", () => {
    render(<MarkdownRenderer content={"| Claim | Source |\n| --- | --- |\n| Finding | Study |"} />);
    expect(screen.getByRole("region", { name: "Scrollable table" }).getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("table")).toBeTruthy();
  });
});
