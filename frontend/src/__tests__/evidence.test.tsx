import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
const mocks = vi.hoisted(() => ({ list: vi.fn(), search: vi.fn(), get: vi.fn(), promote: vi.fn(), projects: vi.fn(), router: { query: {} as Record<string, string> } }));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "reader" } }) }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listProjects: mocks.projects } }));
vi.mock("@/lib/api/evidence", async importOriginal => ({ ...await importOriginal<typeof import("@/lib/api/evidence")>(), evidenceApi: mocks }));
import EvidencePage from "@/pages/evidence";
import EvidenceDetailPage from "@/pages/evidence/[id]";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
const entry = (id: string) => ({ id, project_id: "alpha", mission_id: null, claim: `Claim ${id}`, summary: "Research summary", snippet: "Verbatim source passage", query: "original research", tags: ["ux"], source_url: "https://example.com/source", source_id: "source-1", source_sighting_count: 43, session_key: "research-session", origin: "mcp-agent", disposition: "supporting", created_at: "2026-09-12T00:00:00Z" });
beforeEach(() => {
  mocks.router.query = {};
  mocks.projects.mockReset().mockResolvedValue({ data: [{ id: "alpha", name: "Alpha" }, { id: "beta", name: "Beta" }], pagination: { pages: 1 } });
  mocks.list.mockReset().mockImplementation(async (_project, page) => ({ entries: [entry(String(page))], notes: [{ id: "note", note_key: "next-query", content: "Read the original source" }], entry_total: 43, note_total: 1, page, page_size: 20 }));
  mocks.search.mockReset().mockResolvedValue({ entries: [entry("search")], notes: [], entry_total: 44, note_total: 0, page: 1, page_size: 20 });
  mocks.get.mockReset().mockResolvedValue({ entry: entry("detail"), links: [{ kind: "report", id: "report", title: "Research output", href: "/reports/report", relationship: "Recorded source" }] });
  mocks.promote.mockReset();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
async function browser(component: ReactNode = <EvidencePage />) { await act(async () => { render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{component}</SWRConfig>); }); }

describe("the evidence browser", () => {
  it("preserves Home's mission and session scope through pagination, then clears it when switching projects", async () => {
    mocks.router.query = { project_id: "alpha", mission_id: "mission-1", session_key: "agent & session" };
    await browser();
    await screen.findByText("Claim 1");
    expect(mocks.projects).toHaveBeenCalledWith({ search: undefined, page: 1, pageSize: 20 });
    expect(mocks.list).toHaveBeenCalledWith("alpha", 1, { mission_id: "mission-1", session_key: "agent & session" });
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    await screen.findByText("Claim 2");
    expect(mocks.list).toHaveBeenCalledWith("alpha", 2, { mission_id: "mission-1", session_key: "agent & session" });
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "beta" } });
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("beta", 1, {}));
    expect(screen.queryByRole("region", { name: "Session working notes" })).toBeNull();
  });
  it("requires a project and uses the server total while paging", async () => {
    await browser(); expect(mocks.list).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "alpha" } });
    expect(await screen.findByText("43 evidence entries")).toBeVisible();
    expect(screen.getByRole("link", { name: "Claim 1" })).toHaveAttribute("href", "/evidence/1");
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    await screen.findByText("Claim 2");
    expect(mocks.list).toHaveBeenCalledWith("alpha", 2, {});
  });
  it("submits search with all filters and counts results independently of the visible page", async () => {
    mocks.router.query = { project_id: "alpha" };
    await browser();
    fireEvent.change(screen.getByLabelText("Search evidence"), { target: { value: "passkeys" } });
    fireEvent.change(screen.getByLabelText("Disposition"), { target: { value: "supporting" } });
    fireEvent.change(screen.getByLabelText("Tag"), { target: { value: "ux" } });
    fireEvent.change(screen.getByLabelText("From date (UTC)"), { target: { value: "2026-09-12" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(await screen.findByText("44 evidence entries")).toBeVisible();
    expect(mocks.search).toHaveBeenCalledWith("alpha", "passkeys", 1, { disposition: "supporting", tag: "ux", created_from: "2026-09-12" });
    fireEvent.click(screen.getByLabelText("Group this page by source"));
    expect(screen.getByText(/1 on this page/)).toBeVisible();
  });
  it("surfaces failed reads and retries without calling them empty", async () => {
    mocks.list.mockRejectedValueOnce(new Error("Access denied"));
    mocks.router.query = { project_id: "alpha" };
    await browser();
    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.queryByText("0 evidence entries")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry", exact: true }));
    expect(await screen.findByText("43 evidence entries")).toBeVisible();
  });
  it("opens entry provenance and uses accessible source-history totals", async () => {
    mocks.router.query = { id: "detail" };
    await browser(<EvidenceDetailPage />);
    expect(await screen.findByRole("heading", { level: 1, name: "Claim detail" })).toBeVisible();
    expect(screen.getByText("Verbatim source passage")).toBeVisible();
    expect(screen.getByRole("link", { name: "Research output" })).toHaveAttribute("href", "/reports/report");
    expect(await screen.findByText("43 accessible sightings")).toBeVisible();
    expect(mocks.list).toHaveBeenCalledWith("alpha", 1, { source_id: "source-1" });
    fireEvent.click(screen.getByRole("button", { name: "Next sightings" }));
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("alpha", 2, { source_id: "source-1" }));
  });
  it("requires an explicit confirmation before promoting the entire session and permits retry", async () => {
    mocks.router.query = { project_id: "alpha", session_key: "research-session" };
    mocks.promote.mockRejectedValueOnce(new Error("Permission denied"));
    await browser();
    expect(await screen.findByText("next-query")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Promote session" }));
    let dialog = screen.getByRole("dialog", { name: "Promote evidence session" });
    expect(mocks.promote).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocks.promote).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Promote session" }));
    dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create artifact" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Permission denied");
    mocks.promote.mockResolvedValueOnce({ report_id: "new", document_id: null, title: "New evidence report", entry_count: 43, note_count: 1 });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create artifact" }));
    expect(await screen.findByRole("link", { name: "New evidence report" })).toHaveAttribute("href", "/reports/new");
    expect(mocks.promote).toHaveBeenCalledWith({ project_id: "alpha", session_key: "research-session", target: "report", title: undefined });
  });
  it("gives report and document pages the same one-click evidence destination", async () => {
    await browser(<EvidencePanel projectId="alpha" filters={{ report_id: "report-1" }} />);
    expect(await screen.findByRole("link", { name: "Browse evidence (43)" })).toHaveAttribute("href", "/evidence?project_id=alpha&report_id=report-1");
    expect(mocks.list).toHaveBeenCalledWith("alpha", 1, { report_id: "report-1" });
  });
});
