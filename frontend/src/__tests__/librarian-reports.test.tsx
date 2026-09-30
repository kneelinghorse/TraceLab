import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ReportDraft } from "@/components/librarian/ReportDraft";
import { collectionsApi } from "@/lib/api/collections";
import { librarianReportsApi, type ReportInputs, type ReportPreview } from "@/lib/api/librarian-reports";

vi.mock("@/lib/api/librarian-reports", () => ({ librarianReportsApi: { sources: vi.fn(), draft: vi.fn(), accept: vi.fn() } }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: { list: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={href} {...props}>{children}</a> }));
const sources: ReportInputs = {
  project_id: "project", collection_id: null, collection_name: null, source_token: "signed-inputs",
  members: [1, 3].map(marker => ({ marker, chunk_id: `chunk-${marker}`, document_name: `Interview ${marker}`, characters: 100, text: `Source ${marker} describes navigation feedback.`, href: `/documents/doc-${marker}?chunk=chunk-${marker}&index=0` })),
  coverage: { readable_chunks: 102, eligible_chunks: 101, excluded_chunks: 1, other_project_chunks: 2, listed_chunks: 2, limited: true, candidate_limit: 100, chunk_limit: 12, character_limit: 24000 },
};
const proposal: ReportPreview = {
  project_id: "project", report_id: "report", title: "Feedback", prompt: "Summarise feedback", format: "summary", content: "Navigation feedback [1] [3].",
  proposal_token: "signed-preview", model: "fixture", generated_at: "2026-09-30T00:00:00Z", input_chunk_ids: ["chunk-1", "chunk-3"], input_characters: 200,
  citations: sources.members.map(member => ({ marker: member.marker, available: true, chunk_id: member.chunk_id, href: member.href })),
};
const saved = { report_id: "report", title: "Feedback", href: "/reports/report" };
const panel = (user = "alice", project = "project") => <ReportDraft key={`${user}:${project}`} userId={user} projectId={project} projectName="Onboarding" />;
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(librarianReportsApi.sources).mockResolvedValue(sources);
  vi.mocked(librarianReportsApi.draft).mockResolvedValue(proposal);
  vi.mocked(librarianReportsApi.accept).mockResolvedValue(saved);
});
async function inputs() {
  fireEvent.change(screen.getByLabelText("Report title"), { target: { value: "Feedback" } });
  fireEvent.change(screen.getByLabelText("What should the report explain?"), { target: { value: "Summarise feedback" } });
  fireEvent.click(screen.getByRole("button", { name: "Load excerpts for review" }));
  await screen.findByRole("region", { name: "Review report inputs" });
  for (const marker of [1, 3]) fireEvent.click(screen.getByRole("checkbox", { name: `Use report excerpt ${marker}` }));
  fireEvent.click(screen.getByRole("checkbox", { name: "I reviewed the selected excerpts from Onboarding." }));
}
async function draft() {
  await inputs();
  fireEvent.click(screen.getByRole("button", { name: "Draft cited report" }));
  await screen.findByRole("region", { name: "Review report draft" });
}

it("requires explicit source review, discloses scope/caps, and performs no work on mount", async () => {
  render(panel());
  expect(librarianReportsApi.sources).not.toHaveBeenCalled();
  expect(librarianReportsApi.draft).not.toHaveBeenCalled();
  await inputs();
  expect(screen.getByText(/2 readable excerpts from other projects excluded/)).toHaveTextContent("Only the first 100");
  expect(screen.getByRole("link", { name: "Open input excerpt [3]" })).toHaveAttribute("href", sources.members[1].href);
  const review = screen.getByRole("checkbox", { name: "I reviewed the selected excerpts from Onboarding." });
  fireEvent.click(review);
  expect(screen.getByRole("button", { name: "Draft cited report" })).toBeDisabled();
  expect(librarianReportsApi.draft).not.toHaveBeenCalled();
});

it("saves only the signed reviewed preview and does not generate a second time", async () => {
  render(panel()); await draft();
  await waitFor(() => expect(screen.getByRole("region", { name: "Review report draft" })).toHaveFocus());
  expect(librarianReportsApi.accept).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Save reviewed report" }));
  expect(await screen.findByRole("link", { name: "Feedback" })).toHaveAttribute("href", "/reports/report");
  expect(librarianReportsApi.accept).toHaveBeenCalledExactlyOnceWith("project", "signed-preview");
  expect(librarianReportsApi.draft).toHaveBeenCalledTimes(1);
  expect(librarianReportsApi.draft).toHaveBeenCalledWith(expect.objectContaining({ reviewed_sources: true, source_token: "signed-inputs", chunk_ids: ["chunk-1", "chunk-3"] }));
});

it("requires regeneration after editing inputs and dismisses without saving", async () => {
  render(panel()); await draft();
  fireEvent.change(screen.getByLabelText("Report title"), { target: { value: "Changed title" } });
  expect(screen.getByRole("button", { name: "Save reviewed report" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss report draft" }));
  expect(screen.queryByRole("region", { name: "Review report draft" })).toBeNull();
  expect(librarianReportsApi.accept).not.toHaveBeenCalled();
  expect(librarianReportsApi.draft).toHaveBeenCalledTimes(1);
});

it("retains exact preview through navigation and a failed-save retry", async () => {
  vi.mocked(librarianReportsApi.accept).mockRejectedValueOnce(new Error("Connection interrupted")).mockResolvedValue(saved);
  const view = render(panel()); await draft();
  fireEvent.click(screen.getByRole("button", { name: "Save reviewed report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection interrupted");
  view.unmount(); render(panel());
  const preview = await screen.findByRole("region", { name: "Review report draft" });
  expect(within(preview).getByText("Navigation feedback [1] [3].")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Save reviewed report" }));
  await screen.findByRole("link", { name: "Feedback" });
  expect(vi.mocked(librarianReportsApi.accept).mock.calls).toEqual([["project", "signed-preview"], ["project", "signed-preview"]]);
  expect(librarianReportsApi.draft).toHaveBeenCalledTimes(1);
});

it("isolates account/project keys and ignores late previews after switching", async () => {
  const view = render(panel()); await draft();
  view.rerender(panel("bob"));
  expect(screen.queryByRole("region", { name: "Review report draft" })).toBeNull();
  view.rerender(panel("alice", "other"));
  expect(screen.queryByRole("region", { name: "Review report draft" })).toBeNull();
  view.rerender(panel());
  await screen.findByRole("region", { name: "Review report draft" });
  let resolve!: (value: ReportPreview) => void;
  vi.mocked(librarianReportsApi.draft).mockReturnValue(new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "Draft report again" }));
  view.rerender(panel("bob"));
  await act(async () => { resolve(proposal); });
  expect(screen.queryByRole("region", { name: "Review report draft" })).toBeNull();
  expect(JSON.parse(localStorage.getItem("tracelab.librarian.reports.v1:bob:project") || "{}").preview).toBeNull();
});

it("blocks over-budget selection and duplicate save presses", async () => {
  const view = render(panel()); await draft();
  let resolve!: (value: typeof saved) => void;
  vi.mocked(librarianReportsApi.accept).mockReturnValue(new Promise(done => { resolve = done; }));
  const save = screen.getByRole("button", { name: "Save reviewed report" });
  fireEvent.click(save); fireEvent.click(save);
  expect(librarianReportsApi.accept).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(saved); });
  view.unmount(); localStorage.clear();
  vi.mocked(librarianReportsApi.sources).mockResolvedValue({ ...sources, coverage: { ...sources.coverage, chunk_limit: 1 } });
  render(panel()); await inputs();
  expect(screen.getByRole("button", { name: "Draft cited report" })).toBeDisabled();
});

it("loads paged readable collections only on request and clears stale source selection", async () => {
  vi.mocked(collectionsApi.list).mockResolvedValue({ data: [{ id: "collection", name: "Reviewed group", description: "", created_at: "", updated_at: "", item_count: 2 }], total: 21 });
  render(panel()); await inputs();
  fireEvent.click(screen.getByRole("button", { name: "Browse collections" }));
  await screen.findByRole("option", { name: "Reviewed group" });
  expect(collectionsApi.list).toHaveBeenCalledWith({ project_id: "project", page: 1, page_size: 20 });
  fireEvent.change(screen.getByLabelText("Report source set"), { target: { value: "collection" } });
  expect(screen.queryByRole("region", { name: "Review report inputs" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Load excerpts for review" }));
  await screen.findByRole("region", { name: "Review report inputs" });
  expect(librarianReportsApi.sources).toHaveBeenLastCalledWith("project", "collection");
});

it("recovers from corrupt local state and refuses missing source context", async () => {
  localStorage.setItem("tracelab.librarian.reports.v1:alice:project", "{}");
  vi.mocked(librarianReportsApi.sources).mockResolvedValue({ ...sources, members: [] });
  render(panel());
  fireEvent.click(screen.getByRole("button", { name: "Load excerpts for review" }));
  await screen.findByText(/No eligible excerpts/);
  expect(screen.getByRole("button", { name: "Draft cited report" })).toBeDisabled();
  expect(librarianReportsApi.draft).not.toHaveBeenCalled();
});
