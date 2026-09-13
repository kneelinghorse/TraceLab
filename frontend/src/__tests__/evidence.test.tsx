import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
const mocks = vi.hoisted(() => ({ list: vi.fn(), projects: vi.fn(), router: { query: {} as Record<string, string> } }));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true }) }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listProjects: mocks.projects } }));
vi.mock("@/lib/api/evidence", () => ({ evidenceApi: { list: mocks.list } }));
import EvidencePage from "@/pages/evidence";
const entry = (id: string) => ({ id, claim: `Claim ${id}`, summary: "Research summary", source_url: "https://example.com/source", source_sighting_count: 2, session_key: "research-session", disposition: "supporting", created_at: "2026-09-12T00:00:00Z" });
beforeEach(() => {
  mocks.router.query = {};
  mocks.projects.mockReset().mockResolvedValue({ data: [{ id: "alpha", name: "Alpha" }, { id: "beta", name: "Beta" }], pagination: { pages: 1 } });
  mocks.list.mockReset().mockImplementation(async (_project, page) => ({ entries: [entry(String(page))], entry_total: 43, page, page_size: 20 }));
});
async function browser() { await act(async () => { render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}><EvidencePage /></SWRConfig>); }); }

describe("the evidence navigation destination", () => {
  it("follows Home's project, mission and session link through pagination", async () => {
    mocks.router.query = { project_id: "alpha", mission_id: "mission-1", session_key: "agent & session" };
    await browser();
    await screen.findByText("Claim 1");
    expect(mocks.projects).toHaveBeenLastCalledWith({ search: undefined, page: 1, pageSize: 20 });
    expect(mocks.list).toHaveBeenLastCalledWith("alpha", 1, { mission_id: "mission-1", session_key: "agent & session" });
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    await screen.findByText("Claim 2");
    expect(mocks.list).toHaveBeenLastCalledWith("alpha", 2, { mission_id: "mission-1", session_key: "agent & session" });
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "beta" } });
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith("beta", 1, { mission_id: undefined, session_key: undefined }));
  });
  it("requires a project and uses the server total while paginating that project", async () => {
    await browser();
    expect(mocks.list).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "alpha" } });
    await screen.findByText("Claim 1");
    expect(screen.getByText("43 evidence entries")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    await screen.findByText("Claim 2");
    expect(mocks.list).toHaveBeenLastCalledWith("alpha", 2, { mission_id: undefined, session_key: undefined });
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "beta" } });
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith("beta", 1, { mission_id: undefined, session_key: undefined }));
    await screen.findByText("Claim 1");
  });
  it("surfaces denied or failed reads instead of reporting an empty ledger", async () => {
    mocks.list.mockRejectedValue(new Error("Access denied"));
    await browser();
    fireEvent.change(screen.getByLabelText("Project", { exact: true }), { target: { value: "alpha" } });
    expect((await screen.findByRole("alert")).textContent).toBe("Access denied");
    expect(screen.queryByText("0 evidence entries")).toBeNull();
  });
});
