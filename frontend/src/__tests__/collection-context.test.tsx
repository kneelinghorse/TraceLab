import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
const mocks = vi.hoisted(() => ({ documents: vi.fn(), remove: vi.fn(), update: vi.fn(), evidence: vi.fn(), reports: vi.fn(), getReport: vi.fn(), get: vi.fn(), router: { isReady: true, query: { id: "collection" }, push: vi.fn() } }));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "author" } }) }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: { documents: mocks.documents, removeDocument: mocks.remove, get: mocks.get, update: mocks.update } }));
vi.mock("@/lib/api/reports", () => ({ reportsApi: { list: mocks.reports, get: mocks.getReport } }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: vi.fn().mockResolvedValue([{ id: "project", name: "Research" }]) } }));
vi.mock("@/lib/api/evidence", async original => ({ ...await original<typeof import("@/lib/api/evidence")>(), evidenceApi: { list: mocks.evidence } }));
import CollectionPage from "@/pages/collections/[id]";
import ReportsPage from "@/pages/reports";
import ReportPage from "@/pages/reports/[id]";
import { ReportCitations } from "@/components/evidence/ReportCitations";
const collection = { id: "collection", name: "Context space", instructions: "Keep competing claims", description: "Sources", items: [], item_count: 0, created_at: "2026-09-13T00:00:00Z" };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockResolvedValue(collection);
  mocks.documents.mockImplementation((_id, page) => Promise.resolve({ total: 121, page, page_size: 20, items: [{ id: `doc-${page}`, project_id: "project", name: `Source page ${page}`, file_type: "txt" }] }));
  mocks.evidence.mockResolvedValue({ entries: [], entry_total: 0, page_size: 20, page: 1 });
  mocks.reports.mockResolvedValue({ items: [], total: 481, page: 1, page_size: 20 });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
async function browser(component: ReactNode) { await act(async () => { render(<SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>{component}</SWRConfig>); }); }
it("edits instructions and links to reviewed authoring without creating a mission", async () => {
  await browser(<CollectionPage />);
  expect(await screen.findByText("Keep competing claims")).toBeVisible();
  expect(screen.getByRole("link", { name: "Seed mission" })).toHaveAttribute("href", "/missions/new?collection=collection");
  fireEvent.click(screen.getByRole("button", { name: "Edit", exact: true }));
  fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Compare primary evidence" } });
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("collection", expect.objectContaining({ instructions: "Compare primary evidence" })));
});
it("pages the full document context and removes only after explicit confirmation", async () => {
  await browser(<CollectionPage />);
  expect(await screen.findByText("Documents (121)")).toBeVisible();
  const pages = within(screen.getByRole("navigation", { name: "Collection document pages" }));
  fireEvent.click(pages.getByRole("button", { name: "Next" }));
  expect(await screen.findByRole("link", { name: "Source page 2" })).toHaveAttribute("href", "/documents/doc-2");
  expect(mocks.documents).toHaveBeenLastCalledWith("collection", 2);
  fireEvent.click(screen.getByRole("button", { name: "Remove Source page 2 from collection" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
  expect(mocks.remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Remove Source page 2 from collection" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue" }));
  await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("collection", "doc-2"));
});
it("presents citation links from every authorized page without synthesizing raw source destinations", async () => {
  mocks.evidence.mockImplementation((_project, page) => Promise.resolve({ entries: [{ id: `entry-${page}`, claim: `Accessible claim ${page}`, source_url: "https://example.test/source", disposition: "supporting", session_key: "run", project_id: "project", created_at: "2026-09-13" }], entry_total: 21, page, page_size: 20 }));
  await browser(<ReportCitations projectId="project" reportId="report" />);
  expect(await screen.findByRole("link", { name: "Accessible claim 1" })).toHaveAttribute("href", "/evidence/entry-1");
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByRole("link", { name: "Accessible claim 2" })).toHaveAttribute("href", "/evidence/entry-2");
  expect(mocks.evidence).toHaveBeenLastCalledWith("project", 2, { report_id: "report" });
});
it("never renders a raw ledger source id as an authorized evidence link", async () => {
  mocks.getReport.mockResolvedValue({ id: "report", project_id: "project", title: "Findings", updated_at: "2026-09-13T00:00:00Z", content: "Result", status: "final", created_at: "2026-09-13T00:00:00Z", citations: [], tokens_used: 0, chunk_count: 0, sources: [{ id: "source", source_type: "ledger_entry", source_id: "inaccessible-entry", added_at: "2026-09-13T00:00:00Z" }] });
  await browser(<ReportPage />);
  expect(await screen.findByText("No accessible evidence is linked to this report.")).toBeVisible();
  expect(document.querySelector('a[href="/evidence/inaccessible-entry"]')).toBeNull();
});
it("preserves the report total and resets paging when filters change", async () => {
  await browser(<ReportsPage />);
  expect(await screen.findByText("481 reports")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(mocks.reports).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  fireEvent.click(screen.getByRole("button", { name: "Final", exact: true }));
  await waitFor(() => expect(mocks.reports).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, status: "final" })));
  fireEvent.change(screen.getByLabelText("Project"), { target: { value: "project" } });
  await waitFor(() => expect(mocks.reports).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, status: "final", project_id: "project" })));
});
