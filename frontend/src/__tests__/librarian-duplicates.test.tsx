import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { DuplicateReview } from "@/components/librarian/DuplicateReview";
import { duplicateApi, type DuplicateScan } from "@/lib/api/librarian-duplicates";

vi.mock("@/lib/api/librarian-duplicates", () => ({ duplicateApi: { scan: vi.fn(), compare: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={href} {...props}>{children}</a> }));
const result: DuplicateScan = {
  project_id: "project", scanned_at: "2026-09-29T00:00:00Z", method: "fixture",
  candidates: [{ candidate_id: "pair", kind: "probable_overlap", score: 0.92,
    documents: [{ id: "a", name: "Interview A", href: "/documents/a" }, { id: "b", name: "Interview B", href: "/documents/b" }],
    basis: "92% five-word phrase overlap across two distinct passages.",
    evidence: [{ left_excerpt: "First observed finding", right_excerpt: "Edited observed finding" }],
    recommendation: "Compare sources before deciding what to retain.",
  }],
  coverage: { readable_documents: 120, scanned_documents: 100, examined_documents: 90, empty_documents: 8, overlong_documents: 2, exact_only_documents: 4, limited: true, document_limit: 100, character_limit: 20000, candidate_count: 1, candidates_limited: false, pair_limit: 20 },
};
function panel(userId = "alice", projectId = "project") {
  return <DuplicateReview key={`${userId}:${projectId}`} userId={userId} projectId={projectId} projectName="Interviews" />;
}
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(duplicateApi.scan).mockResolvedValue(result);
  vi.mocked(duplicateApi.compare).mockResolvedValue({ candidate: result.candidates[0], documents: result.candidates[0].documents.map(doc => ({ ...doc, content: "Current source text: " + doc.name })) });
});
async function scan() {
  fireEvent.click(screen.getByRole("button", { name: "Find possible duplicates" }));
  await screen.findByRole("region", { name: "Duplicate results" });
}

it("scans only on request, preserves review after navigation, and dismisses without a corpus request", async () => {
  const first = render(panel());
  fireEvent.focus(window); fireEvent(window, new Event("online"));
  expect(duplicateApi.scan).not.toHaveBeenCalled();
  await scan();
  await waitFor(() => expect(screen.getByRole("region", { name: "Duplicate results" })).toHaveFocus());
  fireEvent.click(screen.getByRole("button", { name: "Dismiss pair" }));
  expect(screen.queryByRole("button", { name: "Compare sources" })).toBeNull();
  first.unmount(); render(panel());
  await screen.findByText(/1 pairs reviewed/);
  expect(screen.queryByRole("button", { name: "Compare sources" })).toBeNull();
  expect(duplicateApi.scan).toHaveBeenCalledTimes(1);
  expect(duplicateApi.compare).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Review all results again" }));
  expect(screen.getByRole("button", { name: "Compare sources" })).toBeVisible();
});

it("rechecks sources before displaying full text and returns keyboard focus on close", async () => {
  render(panel()); await scan();
  expect(screen.queryByRole("link", { name: "Interview A" })).toBeNull();
  const compare = screen.getByRole("button", { name: "Compare sources" });
  fireEvent.click(compare);
  expect(await screen.findByRole("region", { name: "Compare documents" })).toHaveFocus();
  expect(duplicateApi.compare).toHaveBeenCalledWith("project", result.candidates[0]);
  expect(screen.getByRole("link", { name: "Interview A" })).toHaveAttribute("href", "/documents/a");
  expect(screen.getByRole("region", { name: "Source text: Interview A" })).toHaveTextContent("Current source text");
  fireEvent.click(screen.getByRole("button", { name: "Close comparison" }));
  expect(compare).toHaveFocus();
});

it("records keep both only in this user's browser review", async () => {
  render(panel()); await scan();
  fireEvent.click(screen.getByRole("button", { name: "Keep both" }));
  expect(screen.getByRole("status")).toHaveTextContent("Neither document was changed");
  await waitFor(() => expect(JSON.parse(localStorage.getItem("tracelab.librarian.duplicates.v1:alice:project") || "{}").reviews).toEqual({ pair: "keep_both" }));
  expect(duplicateApi.compare).not.toHaveBeenCalled();
  expect(duplicateApi.scan).toHaveBeenCalledTimes(1);
});

it("shows stale or revoked comparison failures without revealing cached full text", async () => {
  vi.mocked(duplicateApi.compare).mockRejectedValue(new Error("Sources are no longer available. Scan again."));
  render(panel()); await scan();
  fireEvent.click(screen.getByRole("button", { name: "Compare sources" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("no longer available");
  expect(screen.queryByRole("region", { name: "Compare documents" })).toBeNull();
  expect(duplicateApi.scan).toHaveBeenCalledTimes(1);
});

it("isolates saved results and late replies across account and project changes", async () => {
  const view = render(panel()); await scan();
  view.rerender(panel("bob"));
  expect(screen.queryByRole("region", { name: "Duplicate results" })).toBeNull();
  view.rerender(panel("alice", "other"));
  expect(screen.queryByRole("region", { name: "Duplicate results" })).toBeNull();
  view.rerender(panel());
  await screen.findByRole("region", { name: "Duplicate results" });
  let resolve!: (value: DuplicateScan) => void;
  vi.mocked(duplicateApi.scan).mockReturnValue(new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "Scan again" }));
  view.rerender(panel("bob"));
  await act(async () => { resolve(result); });
  expect(screen.queryByRole("region", { name: "Duplicate results" })).toBeNull();
  expect(localStorage.getItem("tracelab.librarian.duplicates.v1:bob:project")).toBeNull();
});

it("reports limits and zero candidates only within the examined scope", async () => {
  vi.mocked(duplicateApi.scan).mockResolvedValue({ ...result, candidates: [] });
  render(panel()); await scan();
  expect(screen.getByText(/Examined 90 of 120/)).toHaveTextContent("partial scan");
  expect(screen.getByText("No possible duplicates found within the examined scope.")).toBeVisible();
});

it("leaves a failed scan retryable and never automatically retries", async () => {
  vi.mocked(duplicateApi.scan).mockRejectedValue(new Error("The scan could not finish."));
  render(panel());
  fireEvent.click(screen.getByRole("button", { name: "Find possible duplicates" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not finish");
  expect(screen.getByRole("button", { name: "Find possible duplicates" })).toBeEnabled();
  expect(duplicateApi.scan).toHaveBeenCalledTimes(1);
});
